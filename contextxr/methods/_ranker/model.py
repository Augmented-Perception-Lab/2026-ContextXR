"""Count-based and embedding-aware facet ranking.

Ported from the paper's research code (context_facet_ranker); logic unchanged.
"""

from __future__ import annotations

import pickle
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import numpy as np

from .embeddings import EmbeddingConfig, EmbeddingManager
from .loader import EventDataset, FacetEvent
from .normalization import normalize_label


CONTEXT_MODES: Tuple[str, ...] = ("T", "E", "U", "TE", "TU", "EU", "TEU")

_MODE_FIELDS: Dict[str, Tuple[str, ...]] = {
    "T": ("task",),
    "E": ("environment",),
    "U": ("user",),
    "TE": ("task", "environment"),
    "TU": ("task", "user"),
    "EU": ("environment", "user"),
    "TEU": ("task", "environment", "user"),
}


@dataclass
class ScoreWeights:
    w_global: float = 0.0
    wT_exact: float = 1.0
    wE_exact: float = 1.0
    wU_exact: float = 1.0
    wT_soft: float = 0.7
    wE_soft: float = 0.7
    wU_soft: float = 0.0
    wTE: float = 0.6
    wTU: float = 0.6
    wEU: float = 0.6
    wTEU: float = 0.25
    wCap: float = 0.1
    wPriorSchema: float = 2.0


@dataclass
class RankerConfig:
    smoothing_alpha: float = 0.5
    task_soft_top_k: int = 3
    environment_soft_top_k: int = 3
    user_soft_top_k: int = 5
    task_soft_min_similarity: float = 0.15
    environment_soft_min_similarity: float = 0.15
    user_soft_min_similarity: float = 0.05
    min_exact_support_for_soft: int = 3
    seen_label_soft_scale: float = 0.2
    enable_user_soft: bool = False
    capability_bonus_top_n: int = 5
    prior_same_app_bonus: float = 0.2
    prior_capability_overlap_weight: float = 0.35
    allow_all_facets_if_small: bool = True
    all_facets_threshold: int = 500
    fallback_global_candidate_count: int = 50
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    default_weights: ScoreWeights = field(default_factory=ScoreWeights)


@dataclass(frozen=True)
class RankerQuery:
    task: str = ""
    environment: str = ""
    user: str = ""
    mode: str = "TEU"


@dataclass
class CountTables:
    facet_global: Counter = field(default_factory=Counter)
    task_facet: Counter = field(default_factory=Counter)
    environment_facet: Counter = field(default_factory=Counter)
    user_facet: Counter = field(default_factory=Counter)
    task_environment_facet: Counter = field(default_factory=Counter)
    task_user_facet: Counter = field(default_factory=Counter)
    environment_user_facet: Counter = field(default_factory=Counter)
    task_environment_user_facet: Counter = field(default_factory=Counter)
    task_total: Counter = field(default_factory=Counter)
    environment_total: Counter = field(default_factory=Counter)
    user_total: Counter = field(default_factory=Counter)
    task_environment_total: Counter = field(default_factory=Counter)
    task_user_total: Counter = field(default_factory=Counter)
    environment_user_total: Counter = field(default_factory=Counter)
    task_environment_user_total: Counter = field(default_factory=Counter)
    global_total: float = 0.0


@dataclass(frozen=True)
class NeighborMatch:
    key: str
    label: str
    similarity: float
    support: int


BASELINE_PRESETS: Dict[str, str] = {
    "global_popularity": "Global popularity only.",
    "flat_exact": "Only direct exact context tuple counts for each mode.",
    "exact_structured": "Weighted exact unary and pairwise/triple components.",
    "exact_embeddings": "Exact structured scoring plus task/environment soft transfer.",
    "exact_embeddings_capability": "Exact + embeddings + low-weight capability propagation.",
    "exact_embeddings_prior_schema": "Exact + embeddings + active-prior schema steering.",
}


class ContextFacetRanker:
    def __init__(
        self,
        dataset: Optional[EventDataset] = None,
        *,
        config: Optional[RankerConfig] = None,
    ) -> None:
        self.config = config or RankerConfig()
        self.dataset: Optional[EventDataset] = None
        self.counts = CountTables()
        self.embeddings = EmbeddingManager(self.config.embedding)
        self.facets_by_task: Dict[str, Set[str]] = defaultdict(set)
        self.facets_by_environment: Dict[str, Set[str]] = defaultdict(set)
        self.facets_by_user: Dict[str, Set[str]] = defaultdict(set)
        self.apps_by_task: Dict[str, Set[str]] = defaultdict(set)
        self.apps_by_environment: Dict[str, Set[str]] = defaultdict(set)
        self.apps_by_user: Dict[str, Set[str]] = defaultdict(set)
        self.facets_by_app: Dict[str, Set[str]] = defaultdict(set)
        self.app_by_facet: Dict[str, str] = {}
        self.capabilities_by_facet: Dict[str, Set[str]] = defaultdict(set)
        self.facets_by_capability: Dict[str, Set[str]] = defaultdict(set)
        self.linked_facets_by_facet: Dict[str, Set[str]] = defaultdict(set)
        self.user_vectors: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.user_norms: Dict[str, float] = {}
        if dataset is not None:
            self.fit(dataset)

    def fit(self, dataset: EventDataset) -> "ContextFacetRanker":
        self.dataset = dataset
        self._build_counts(dataset.events)
        self._build_adjacency(dataset)
        self.embeddings.fit(dataset)
        if self.config.enable_user_soft:
            self._build_user_similarity()
        return self

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            pickle.dump(self, handle)

    @classmethod
    def load(cls, path: str | Path) -> "ContextFacetRanker":
        with Path(path).open("rb") as handle:
            return pickle.load(handle)

    @property
    def all_facets(self) -> List[str]:
        if self.dataset is None:
            return []
        return list(self.dataset.schema.facets.keys())

    def _build_counts(self, events: Sequence[FacetEvent]) -> None:
        counts = CountTables()
        for event in events:
            facet = event.facet
            if not facet:
                continue
            counts.facet_global[facet] += 1.0
            counts.global_total += 1.0

            if event.task:
                counts.task_facet[(event.task, facet)] += 1.0
                counts.task_total[event.task] += 1.0
                self.facets_by_task[event.task].add(facet)
            if event.environment:
                counts.environment_facet[(event.environment, facet)] += 1.0
                counts.environment_total[event.environment] += 1.0
                self.facets_by_environment[event.environment].add(facet)
            if event.user:
                counts.user_facet[(event.user, facet)] += 1.0
                counts.user_total[event.user] += 1.0
                self.facets_by_user[event.user].add(facet)
                self.user_vectors[event.user][facet] = self.user_vectors[event.user].get(facet, 0.0) + 1.0

            if event.task and event.environment:
                key = (event.task, event.environment)
                counts.task_environment_facet[(event.task, event.environment, facet)] += 1.0
                counts.task_environment_total[key] += 1.0
            if event.task and event.user:
                key = (event.task, event.user)
                counts.task_user_facet[(event.task, event.user, facet)] += 1.0
                counts.task_user_total[key] += 1.0
            if event.environment and event.user:
                key = (event.environment, event.user)
                counts.environment_user_facet[(event.environment, event.user, facet)] += 1.0
                counts.environment_user_total[key] += 1.0
            if event.task and event.environment and event.user:
                key = (event.task, event.environment, event.user)
                counts.task_environment_user_facet[
                    (event.task, event.environment, event.user, facet)
                ] += 1.0
                counts.task_environment_user_total[key] += 1.0

            if event.app:
                if event.task:
                    self.apps_by_task[event.task].add(event.app)
                if event.environment:
                    self.apps_by_environment[event.environment].add(event.app)
                if event.user:
                    self.apps_by_user[event.user].add(event.app)
                self.facets_by_app[event.app].add(facet)
            for capability in event.capabilities:
                self.capabilities_by_facet[facet].add(capability)
                self.facets_by_capability[capability].add(facet)

        self.counts = counts

    def _build_adjacency(self, dataset: EventDataset) -> None:
        rel = dataset.schema.relation_adjacency
        for facet_key, record in dataset.schema.facets.items():
            app_id = normalize_label(record.properties.get("app_id", ""))
            if not app_id:
                continue
            self.app_by_facet[facet_key] = app_id
            self.facets_by_app[app_id].add(facet_key)
        for app, facets in rel.get("app_offers_facet", {}).items():
            self.facets_by_app[app].update(facets)
            for facet in facets:
                self.app_by_facet[facet] = app
        for facet, capabilities in rel.get("facet_composed_of_capability", {}).items():
            self.capabilities_by_facet[facet].update(capabilities)
            for capability in capabilities:
                self.facets_by_capability[capability].add(facet)
        for facet, linked_facets in rel.get("facet_links_to_facet", {}).items():
            self.linked_facets_by_facet[facet].update(linked_facets)
            for linked_facet in linked_facets:
                self.linked_facets_by_facet[linked_facet].add(facet)

    def _build_user_similarity(self) -> None:
        self.user_norms = {}
        for user_key, facet_counts in self.user_vectors.items():
            norm = float(np.sqrt(sum(value * value for value in facet_counts.values())))
            self.user_norms[user_key] = norm

    def _facet_count(self) -> int:
        return max(1, len(self.all_facets))

    def _conditional_probability(
        self,
        counter: Counter,
        total_counter: Counter,
        context_key: Any,
        facet_key: str,
    ) -> float:
        alpha = float(self.config.smoothing_alpha)
        total = float(total_counter.get(context_key, 0.0))
        if isinstance(context_key, tuple):
            lookup_key = (*context_key, facet_key)
        else:
            lookup_key = (context_key, facet_key)
        numerator = float(counter.get(lookup_key, 0.0)) + alpha
        denominator = total + (alpha * self._facet_count())
        return numerator / denominator if denominator > 0 else 0.0

    def _global_probability(self, facet_key: str) -> float:
        alpha = float(self.config.smoothing_alpha)
        numerator = float(self.counts.facet_global.get(facet_key, 0.0)) + alpha
        denominator = float(self.counts.global_total) + (alpha * self._facet_count())
        return numerator / denominator if denominator > 0 else 0.0

    def _support_for_label(self, field_name: str, key: str) -> int:
        if field_name == "task":
            return int(self.counts.task_total.get(key, 0))
        if field_name == "environment":
            return int(self.counts.environment_total.get(key, 0))
        if field_name == "user":
            return int(self.counts.user_total.get(key, 0))
        return 0

    def _soft_gate(self, field_name: str, key: str) -> float:
        support = self._support_for_label(field_name, key) if key else 0
        if support <= 0:
            return 1.0
        if support < int(self.config.min_exact_support_for_soft):
            return 1.0
        return float(self.config.seen_label_soft_scale)

    def _nearest_tasks(self, raw_label: str, exact_key: str) -> List[NeighborMatch]:
        neighbors = self.embeddings.nearest(
            "task",
            raw_label,
            top_k=self.config.task_soft_top_k,
            min_similarity=self.config.task_soft_min_similarity,
            exclude_keys={exact_key} if exact_key else set(),
        )
        return [
            NeighborMatch(
                key=key,
                label=self.dataset.schema.tasks[key].label if self.dataset else key,
                similarity=similarity,
                support=self._support_for_label("task", key),
            )
            for key, similarity in neighbors
        ]

    def _nearest_environments(self, raw_label: str, exact_key: str) -> List[NeighborMatch]:
        neighbors = self.embeddings.nearest(
            "environment",
            raw_label,
            top_k=self.config.environment_soft_top_k,
            min_similarity=self.config.environment_soft_min_similarity,
            exclude_keys={exact_key} if exact_key else set(),
        )
        return [
            NeighborMatch(
                key=key,
                label=self.dataset.schema.environments[key].label if self.dataset else key,
                similarity=similarity,
                support=self._support_for_label("environment", key),
            )
            for key, similarity in neighbors
        ]

    def _nearest_users(self, user_key: str) -> List[NeighborMatch]:
        if not self.config.enable_user_soft or user_key not in self.user_vectors:
            return []
        target = self.user_vectors[user_key]
        target_norm = self.user_norms.get(user_key, 0.0)
        if target_norm <= 0.0:
            return []
        neighbors: List[NeighborMatch] = []
        for other_key, other_vector in self.user_vectors.items():
            if other_key == user_key:
                continue
            other_norm = self.user_norms.get(other_key, 0.0)
            if other_norm <= 0.0:
                continue
            common = set(target).intersection(other_vector)
            dot = sum(target[facet] * other_vector[facet] for facet in common)
            similarity = dot / (target_norm * other_norm)
            if similarity < self.config.user_soft_min_similarity:
                continue
            neighbors.append(
                NeighborMatch(
                    key=other_key,
                    label=self.dataset.schema.users[other_key].label if self.dataset else other_key,
                    similarity=float(similarity),
                    support=self._support_for_label("user", other_key),
                )
            )
        neighbors.sort(key=lambda item: (-item.similarity, item.key))
        return neighbors[: self.config.user_soft_top_k]

    def _resolve_query(self, query: RankerQuery) -> Dict[str, str]:
        if self.dataset is None:
            raise RuntimeError("Ranker has not been fit.")
        return {
            "task": normalize_label(query.task),
            "environment": normalize_label(query.environment),
            "user": normalize_label(query.user),
        }

    def _candidate_facets(
        self,
        query: RankerQuery,
        *,
        resolved: Mapping[str, str],
        task_neighbors: Sequence[NeighborMatch],
        environment_neighbors: Sequence[NeighborMatch],
    ) -> Set[str]:
        candidates: Set[str] = set()
        fields = _MODE_FIELDS[query.mode]

        if "task" in fields and resolved["task"]:
            candidates.update(self.facets_by_task.get(resolved["task"], set()))
            for app in self.apps_by_task.get(resolved["task"], set()):
                candidates.update(self.facets_by_app.get(app, set()))
        if "environment" in fields and resolved["environment"]:
            candidates.update(self.facets_by_environment.get(resolved["environment"], set()))
            for app in self.apps_by_environment.get(resolved["environment"], set()):
                candidates.update(self.facets_by_app.get(app, set()))
        if "user" in fields and resolved["user"]:
            candidates.update(self.facets_by_user.get(resolved["user"], set()))
            for app in self.apps_by_user.get(resolved["user"], set()):
                candidates.update(self.facets_by_app.get(app, set()))

        for neighbor in task_neighbors:
            candidates.update(self.facets_by_task.get(neighbor.key, set()))
            for app in self.apps_by_task.get(neighbor.key, set()):
                candidates.update(self.facets_by_app.get(app, set()))
        for neighbor in environment_neighbors:
            candidates.update(self.facets_by_environment.get(neighbor.key, set()))
            for app in self.apps_by_environment.get(neighbor.key, set()):
                candidates.update(self.facets_by_app.get(app, set()))

        if candidates:
            capability_expansion = set()
            for facet in candidates:
                for capability in self.capabilities_by_facet.get(facet, set()):
                    capability_expansion.update(self.facets_by_capability.get(capability, set()))
            candidates.update(capability_expansion)

        if (
            self.config.allow_all_facets_if_small
            and len(self.all_facets) <= int(self.config.all_facets_threshold)
        ):
            candidates.update(self.all_facets)

        if not candidates:
            global_candidates = [
                facet
                for facet, _ in self.counts.facet_global.most_common(self.config.fallback_global_candidate_count)
            ]
            candidates.update(global_candidates or self.all_facets)
        return candidates

    def _task_soft_score(
        self,
        facet_key: str,
        *,
        raw_task: str,
        exact_task: str,
        neighbors: Sequence[NeighborMatch],
    ) -> float:
        if not raw_task or not neighbors:
            return 0.0
        gate = self._soft_gate("task", exact_task)
        numer = 0.0
        denom = 0.0
        for neighbor in neighbors:
            numer += neighbor.similarity * self._conditional_probability(
                self.counts.task_facet,
                self.counts.task_total,
                neighbor.key,
                facet_key,
            )
            denom += neighbor.similarity
        return gate * (numer / denom if denom > 0 else 0.0)

    def _environment_soft_score(
        self,
        facet_key: str,
        *,
        raw_environment: str,
        exact_environment: str,
        neighbors: Sequence[NeighborMatch],
    ) -> float:
        if not raw_environment or not neighbors:
            return 0.0
        gate = self._soft_gate("environment", exact_environment)
        numer = 0.0
        denom = 0.0
        for neighbor in neighbors:
            numer += neighbor.similarity * self._conditional_probability(
                self.counts.environment_facet,
                self.counts.environment_total,
                neighbor.key,
                facet_key,
            )
            denom += neighbor.similarity
        return gate * (numer / denom if denom > 0 else 0.0)

    def _user_soft_score(self, facet_key: str, *, user_key: str, neighbors: Sequence[NeighborMatch]) -> float:
        if not neighbors or not user_key:
            return 0.0
        gate = self._soft_gate("user", user_key)
        numer = 0.0
        denom = 0.0
        for neighbor in neighbors:
            numer += neighbor.similarity * self._conditional_probability(
                self.counts.user_facet,
                self.counts.user_total,
                neighbor.key,
                facet_key,
            )
            denom += neighbor.similarity
        return gate * (numer / denom if denom > 0 else 0.0)

    def _component_signals(
        self,
        facet_key: str,
        *,
        query: RankerQuery,
        resolved: Mapping[str, str],
        task_neighbors: Sequence[NeighborMatch],
        environment_neighbors: Sequence[NeighborMatch],
        user_neighbors: Sequence[NeighborMatch],
    ) -> Dict[str, float]:
        task_key = resolved["task"]
        environment_key = resolved["environment"]
        user_key = resolved["user"]
        signals = {
            "global_popularity": self._global_probability(facet_key),
            "task_exact": self._conditional_probability(
                self.counts.task_facet,
                self.counts.task_total,
                task_key,
                facet_key,
            )
            if task_key
            else 0.0,
            "environment_exact": self._conditional_probability(
                self.counts.environment_facet,
                self.counts.environment_total,
                environment_key,
                facet_key,
            )
            if environment_key
            else 0.0,
            "user_exact": self._conditional_probability(
                self.counts.user_facet,
                self.counts.user_total,
                user_key,
                facet_key,
            )
            if user_key
            else 0.0,
            "task_soft": self._task_soft_score(
                facet_key,
                raw_task=query.task,
                exact_task=task_key,
                neighbors=task_neighbors,
            ),
            "environment_soft": self._environment_soft_score(
                facet_key,
                raw_environment=query.environment,
                exact_environment=environment_key,
                neighbors=environment_neighbors,
            ),
            "user_soft": self._user_soft_score(
                facet_key,
                user_key=user_key,
                neighbors=user_neighbors,
            ),
            "task_environment": self._conditional_probability(
                self.counts.task_environment_facet,
                self.counts.task_environment_total,
                (task_key, environment_key),
                facet_key,
            )
            if task_key and environment_key
            else 0.0,
            "task_user": self._conditional_probability(
                self.counts.task_user_facet,
                self.counts.task_user_total,
                (task_key, user_key),
                facet_key,
            )
            if task_key and user_key
            else 0.0,
            "environment_user": self._conditional_probability(
                self.counts.environment_user_facet,
                self.counts.environment_user_total,
                (environment_key, user_key),
                facet_key,
            )
            if environment_key and user_key
            else 0.0,
            "task_environment_user": self._conditional_probability(
                self.counts.task_environment_user_facet,
                self.counts.task_environment_user_total,
                (task_key, environment_key, user_key),
                facet_key,
            )
            if task_key and environment_key and user_key
            else 0.0,
            "capability_similarity": 0.0,
        }
        return signals

    def _weights_for_variant(self, variant: str) -> ScoreWeights:
        base = self.config.default_weights
        if variant == "global_popularity":
            return ScoreWeights(w_global=1.0, wT_exact=0.0, wE_exact=0.0, wU_exact=0.0, wT_soft=0.0, wE_soft=0.0, wU_soft=0.0, wTE=0.0, wTU=0.0, wEU=0.0, wTEU=0.0, wCap=0.0, wPriorSchema=0.0)
        if variant == "flat_exact":
            return ScoreWeights(w_global=0.0, wT_exact=1.0, wE_exact=1.0, wU_exact=1.0, wT_soft=0.0, wE_soft=0.0, wU_soft=0.0, wTE=1.0, wTU=1.0, wEU=1.0, wTEU=1.0, wCap=0.0, wPriorSchema=0.0)
        if variant == "exact_structured":
            return ScoreWeights(
                w_global=0.0,
                wT_exact=base.wT_exact,
                wE_exact=base.wE_exact,
                wU_exact=base.wU_exact,
                wT_soft=0.0,
                wE_soft=0.0,
                wU_soft=0.0,
                wTE=base.wTE,
                wTU=base.wTU,
                wEU=base.wEU,
                wTEU=base.wTEU,
                wCap=0.0,
                wPriorSchema=0.0,
            )
        if variant == "exact_embeddings":
            return ScoreWeights(
                w_global=0.0,
                wT_exact=base.wT_exact,
                wE_exact=base.wE_exact,
                wU_exact=base.wU_exact,
                wT_soft=base.wT_soft,
                wE_soft=base.wE_soft,
                wU_soft=base.wU_soft if self.config.enable_user_soft else 0.0,
                wTE=base.wTE,
                wTU=base.wTU,
                wEU=base.wEU,
                wTEU=base.wTEU,
                wCap=0.0,
                wPriorSchema=0.0,
            )
        if variant == "exact_embeddings_capability":
            return ScoreWeights(
                w_global=0.0,
                wT_exact=base.wT_exact,
                wE_exact=base.wE_exact,
                wU_exact=base.wU_exact,
                wT_soft=base.wT_soft,
                wE_soft=base.wE_soft,
                wU_soft=base.wU_soft if self.config.enable_user_soft else 0.0,
                wTE=base.wTE,
                wTU=base.wTU,
                wEU=base.wEU,
                wTEU=base.wTEU,
                wCap=base.wCap,
                wPriorSchema=0.0,
            )
        if variant == "exact_embeddings_prior_schema":
            return ScoreWeights(
                w_global=0.0,
                wT_exact=base.wT_exact,
                wE_exact=base.wE_exact,
                wU_exact=base.wU_exact,
                wT_soft=base.wT_soft,
                wE_soft=base.wE_soft,
                wU_soft=base.wU_soft if self.config.enable_user_soft else 0.0,
                wTE=base.wTE,
                wTU=base.wTU,
                wEU=base.wEU,
                wTEU=base.wTEU,
                wCap=0.0,
                wPriorSchema=base.wPriorSchema,
            )
        raise KeyError(f"Unknown variant: {variant}")

    def _active_component_weights(self, mode: str, variant: str, weights: ScoreWeights) -> Dict[str, float]:
        if variant == "global_popularity":
            return {"global_popularity": weights.w_global}
        if variant == "flat_exact":
            component = {
                "T": "task_exact",
                "E": "environment_exact",
                "U": "user_exact",
                "TE": "task_environment",
                "TU": "task_user",
                "EU": "environment_user",
                "TEU": "task_environment_user",
            }[mode]
            return {component: 1.0}

        active: Dict[str, float] = {}
        if "T" in mode:
            active["task_exact"] = weights.wT_exact
        if "E" in mode:
            active["environment_exact"] = weights.wE_exact
        if "U" in mode:
            active["user_exact"] = weights.wU_exact

        if variant in {"exact_embeddings", "exact_embeddings_capability", "exact_embeddings_prior_schema"}:
            if "T" in mode:
                active["task_soft"] = weights.wT_soft
            if "E" in mode:
                active["environment_soft"] = weights.wE_soft
            if "U" in mode and weights.wU_soft > 0.0:
                active["user_soft"] = weights.wU_soft

        if mode == "TE":
            active["task_environment"] = weights.wTE
        elif mode == "TU":
            active["task_user"] = weights.wTU
        elif mode == "EU":
            active["environment_user"] = weights.wEU
        elif mode == "TEU":
            active["task_environment"] = weights.wTE
            active["task_user"] = weights.wTU
            active["environment_user"] = weights.wEU
            active["task_environment_user"] = weights.wTEU

        if variant == "exact_embeddings_capability":
            active["capability_similarity"] = weights.wCap
        if variant == "exact_embeddings_prior_schema":
            active["prior_schema"] = weights.wPriorSchema

        return {name: weight for name, weight in active.items() if weight > 0.0}

    def _variant_uses_prior_schema(self, variant: str) -> bool:
        return variant == "exact_embeddings_prior_schema"

    def _prior_related_candidates(self, prior_facet_ids: Sequence[str]) -> Set[str]:
        related: Set[str] = set()
        for prior_facet_id in prior_facet_ids:
            prior_key = str(prior_facet_id or "").strip()
            if not prior_key:
                continue
            related.update(self.linked_facets_by_facet.get(prior_key, set()))
            app_id = self.app_by_facet.get(prior_key, "")
            if app_id:
                related.update(self.facets_by_app.get(app_id, set()))
            for capability in self.capabilities_by_facet.get(prior_key, set()):
                related.update(self.facets_by_capability.get(capability, set()))
        return related

    def _prior_schema_score(
        self,
        facet_key: str,
        *,
        prior_facet_ids: Sequence[str],
    ) -> float:
        if not prior_facet_ids:
            return 0.0
        target_caps = self.capabilities_by_facet.get(facet_key, set())
        target_app = self.app_by_facet.get(facet_key, "")
        best = 0.0
        for prior_facet_id in prior_facet_ids:
            prior_key = str(prior_facet_id or "").strip()
            if not prior_key or prior_key == facet_key:
                continue
            score = 0.0
            if facet_key in self.linked_facets_by_facet.get(prior_key, set()):
                score = 1.0
            prior_caps = self.capabilities_by_facet.get(prior_key, set())
            if prior_caps and target_caps:
                union = target_caps | prior_caps
                if union:
                    overlap = len(target_caps & prior_caps) / len(union)
                    score = max(
                        score,
                        float(self.config.prior_capability_overlap_weight) * float(overlap),
                    )
            if target_app and target_app == self.app_by_facet.get(prior_key, ""):
                score = max(score, float(self.config.prior_same_app_bonus))
            if score > best:
                best = score
                if best >= 1.0:
                    break
        return best

    def _capability_similarity_bonus(
        self,
        facet_key: str,
        *,
        base_scores: Mapping[str, float],
    ) -> float:
        target_caps = self.capabilities_by_facet.get(facet_key, set())
        if not target_caps:
            return 0.0
        ranked_facets = sorted(base_scores.items(), key=lambda item: (-item[1], item[0]))
        numer = 0.0
        denom = 0.0
        used = 0
        for other_facet, other_score in ranked_facets:
            if other_facet == facet_key or other_score <= 0.0:
                continue
            other_caps = self.capabilities_by_facet.get(other_facet, set())
            if not other_caps:
                continue
            union = target_caps | other_caps
            if not union:
                continue
            overlap = len(target_caps & other_caps) / len(union)
            if overlap <= 0.0:
                continue
            numer += float(other_score) * overlap
            denom += overlap
            used += 1
            if used >= self.config.capability_bonus_top_n:
                break
        return numer / denom if denom > 0 else 0.0

    def rank(
        self,
        *,
        task: str = "",
        environment: str = "",
        user: str = "",
        mode: str = "TEU",
        top_k: int = 10,
        variant: str = "exact_embeddings",
        prior_facet_ids: Optional[Sequence[str]] = None,
        exclude_facet_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        if self.dataset is None:
            raise RuntimeError("Ranker must be fit before ranking.")
        if mode not in CONTEXT_MODES:
            raise ValueError(f"Unsupported mode: {mode}")
        if variant not in BASELINE_PRESETS:
            raise ValueError(f"Unsupported variant: {variant}")

        query = RankerQuery(task=task, environment=environment, user=user, mode=mode)
        resolved = self._resolve_query(query)
        excluded_facet_ids = {
            str(facet_id).strip()
            for facet_id in (exclude_facet_ids or [])
            if str(facet_id).strip()
        }
        active_prior_facet_ids = [
            str(facet_id).strip()
            for facet_id in (prior_facet_ids or [])
            if str(facet_id).strip()
        ]
        task_neighbors = self._nearest_tasks(query.task, resolved["task"]) if "task" in _MODE_FIELDS[mode] else []
        environment_neighbors = (
            self._nearest_environments(query.environment, resolved["environment"])
            if "environment" in _MODE_FIELDS[mode]
            else []
        )
        user_neighbors = (
            self._nearest_users(resolved["user"])
            if "user" in _MODE_FIELDS[mode] and resolved["user"]
            else []
        )
        candidates = self._candidate_facets(
            query,
            resolved=resolved,
            task_neighbors=task_neighbors,
            environment_neighbors=environment_neighbors,
        )
        if self._variant_uses_prior_schema(variant) and active_prior_facet_ids:
            candidates.update(self._prior_related_candidates(active_prior_facet_ids))
        if excluded_facet_ids:
            candidates.difference_update(excluded_facet_ids)
        if not candidates:
            fallback_candidates = [
                facet
                for facet, _ in self.counts.facet_global.most_common(self.config.fallback_global_candidate_count)
                if facet not in excluded_facet_ids
            ]
            if fallback_candidates:
                candidates.update(fallback_candidates)
            else:
                candidates.update(
                    facet for facet in self.all_facets if facet not in excluded_facet_ids
                )
        weights = self._weights_for_variant(variant)
        active_component_weights = self._active_component_weights(mode, variant, weights)
        normalizer = sum(active_component_weights.values()) or 1.0

        raw_signals: Dict[str, Dict[str, float]] = {}
        base_scores: Dict[str, float] = {}
        for facet_key in candidates:
            signals = self._component_signals(
                facet_key,
                query=query,
                resolved=resolved,
                task_neighbors=task_neighbors,
                environment_neighbors=environment_neighbors,
                user_neighbors=user_neighbors,
            )
            raw_signals[facet_key] = signals
            base_scores[facet_key] = sum(
                signals[component] * weight
                for component, weight in active_component_weights.items()
                if component not in {"capability_similarity", "prior_schema"}
            ) / normalizer

        if "capability_similarity" in active_component_weights:
            for facet_key in candidates:
                raw_signals[facet_key]["capability_similarity"] = self._capability_similarity_bonus(
                    facet_key,
                    base_scores=base_scores,
                )
        if "prior_schema" in active_component_weights:
            for facet_key in candidates:
                raw_signals[facet_key]["prior_schema"] = self._prior_schema_score(
                    facet_key,
                    prior_facet_ids=active_prior_facet_ids,
                )

        scored_results: List[Dict[str, Any]] = []
        for facet_key in candidates:
            contributions = {
                component: (raw_signals[facet_key][component] * weight) / normalizer
                for component, weight in active_component_weights.items()
            }
            total_score = float(sum(contributions.values()))
            tie_break = self._global_probability(facet_key)
            facet_record = self.dataset.schema.facets.get(facet_key)
            app_id = str(facet_record.properties.get("app_id", "")) if facet_record else ""
            app_record = self.dataset.schema.apps.get(app_id) if app_id else None
            scored_results.append(
                {
                    "facet": facet_record.label if facet_record else facet_key,
                    "facet_id": facet_key,
                    "app": app_record.label if app_record else app_id,
                    "app_id": app_id,
                    "score": round(total_score, 6),
                    "tie_break_global": round(tie_break, 6),
                    "components": {
                        name: round(value, 6)
                        for name, value in sorted(contributions.items())
                    },
                }
            )

        scored_results.sort(
            key=lambda row: (-float(row["score"]), -float(row["tie_break_global"]), str(row["facet_id"]))
        )
        trimmed = scored_results[:top_k]
        for rank, row in enumerate(trimmed, start=1):
            row["rank"] = rank
            row.pop("tie_break_global", None)

        return {
            "query_mode": mode,
            "variant": variant,
            "input": {
                "task": task,
                "environment": environment,
                "user": user,
                "prior_facet_ids": list(active_prior_facet_ids),
            },
            "resolved_input": resolved,
            "excluded_facet_ids": sorted(excluded_facet_ids),
            "neighbors": {
                "task": [asdict(item) for item in task_neighbors],
                "environment": [asdict(item) for item in environment_neighbors],
                "user": [asdict(item) for item in user_neighbors],
            },
            "candidate_count": len(candidates),
            "results": trimmed,
        }
