"""Map free-form context labels to the benchmark vocabulary (paper §5.2).

Context sensing is outside the benchmark. A sensing module (activity recognition, a
vision-language model, ...) may output labels such as "making pasta" or "home
kitchen"; `ContextNormalizer` maps each to the most similar task or environment label
in the dataset by cosine similarity of all-MiniLM-L6-v2 sentence embeddings, so the
result can be fed to any method. Requires the [embed] extra.

    norm = ContextNormalizer(load_minexrpp())
    norm.task("making pasta").label          # e.g. "Cooking"
    norm.context("P04", "making pasta", "home kitchen")
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from contextxr.data.schema import Context, Dataset

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def humanize(label: str) -> str:
    """'CookingWithFriends' -> 'cooking with friends'; 'coffee_shop' -> 'coffee shop'."""
    text = re.sub(r"[_\-]+", " ", str(label))
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class LabelMatch:
    query: str
    label: str  # benchmark label (raw spelling used in the dataset)
    similarity: float
    alternatives: List[Tuple[str, float]] = field(default_factory=list)


class ContextNormalizer:
    """Nearest-label mapping for tasks and environments; users pass through unchanged.

    Labels that differ only in spelling or case (e.g. "CoffeeShop" / "coffeeshop") are
    grouped; a match returns the group's most frequent spelling. `min_similarity`
    rejects weak matches (the query is then returned unchanged with `similarity` < threshold).
    """

    def __init__(self, dataset: Dataset, *, model: str = DEFAULT_MODEL, min_similarity: float = 0.0,
                 top_alternatives: int = 3, device: Optional[str] = None):
        self.model_id = model
        self.min_similarity = float(min_similarity)
        self.top_alternatives = int(top_alternatives)
        self.device = device
        self._model = None
        self._vocab: Dict[str, List[str]] = {
            "task": self._canonical([s.context.task for s in dataset]),
            "environment": self._canonical([s.context.environment for s in dataset]),
        }
        self._matrix: Dict[str, object] = {}

    @staticmethod
    def _canonical(labels: Sequence[str]) -> List[str]:
        groups: Dict[str, Counter] = {}
        for label in labels:
            groups.setdefault(re.sub(r"[^a-z0-9]", "", label.lower()), Counter())[label] += 1
        return sorted(c.most_common(1)[0][0] for c in groups.values())

    def vocabulary(self, kind: str) -> List[str]:
        return list(self._vocab[kind])

    def _encode(self, texts: Sequence[str]):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover
                raise ImportError("ContextNormalizer needs the [embed] extra: pip install 'contextxr[embed]'") from exc
            self._model = SentenceTransformer(self.model_id, device=self.device)
        return self._model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)

    def _prefix(self, kind: str, text: str) -> str:
        return f"{'Task' if kind == 'task' else 'Environment'}: {humanize(text)}"

    def match(self, kind: str, query: str) -> LabelMatch:
        if kind not in self._vocab:
            raise ValueError("kind must be 'task' or 'environment'")
        if kind not in self._matrix:
            self._matrix[kind] = self._encode([self._prefix(kind, v) for v in self._vocab[kind]])
        q = self._encode([self._prefix(kind, query)])[0]
        sims = self._matrix[kind] @ q
        order = sorted(range(len(sims)), key=lambda i: (-float(sims[i]), self._vocab[kind][i]))
        ranked = [(self._vocab[kind][i], float(sims[i])) for i in order]
        best_label, best_sim = ranked[0]
        label = best_label if best_sim >= self.min_similarity else query
        return LabelMatch(query, label, best_sim, ranked[1 : 1 + self.top_alternatives])

    def task(self, query: str) -> LabelMatch:
        return self.match("task", query)

    def environment(self, query: str) -> LabelMatch:
        return self.match("environment", query)

    def context(self, user: str, task: str, environment: str) -> Context:
        return Context(user=user, task=self.task(task).label, environment=self.environment(environment).label)
