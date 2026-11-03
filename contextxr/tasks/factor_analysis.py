"""Experiment 1: context factor analysis (paper §4.1, Fig. 4).

For each facet, compares how often it appears in *both* scenarios of a pair that
shares the user (or task, or environment) with how often it appears in both
scenarios of an arbitrary pair:

    lift_d(f) = P(f in both | pair shares dimension d) / P(f in both | any pair)

A facet is present in a scenario if some placed element resolves to it. Facets
placed in fewer than `min_occurrences` scenarios are skipped. The dominant factor
is the dimension with the highest lift; "mixed" if the top lift is less than
`dominance_ratio` times the second; "none" if no lift exceeds 1.

Task labels are merged with an alias table and environment spellings are
normalized before comparing contexts (configs/factor_analysis.yaml).
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Union

from contextxr import BENCHMARK_VERSION
from contextxr.data.schema import Dataset

DIMENSIONS = ("user", "task", "environment")
CATEGORY_NAMES = {"user": "user", "task": "task", "environment": "environment", "mixed": "mixed", "no_enrichment": "none"}
PathLike = Union[str, Path]


@dataclass
class FacetLift:
    facet_id: str
    label: str
    occurrences: int
    lift_user: float
    lift_task: float
    lift_environment: float
    top_dimension: str
    dominance_ratio: float
    dominant: str  # user | task | environment | mixed | none


def _compact(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def default_config_path() -> Path:
    from contextxr.paths import configs_dir

    return configs_dir() / "factor_analysis.yaml"


def load_config(path: Optional[PathLike] = None) -> Dict:
    path = Path(path) if path else default_config_path()
    if not path.exists():
        return {}
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


class ContextFactorAnalysis:
    name = "factors"

    def __init__(
        self,
        *,
        task_aliases: Optional[Mapping[str, str]] = None,
        environment_aliases: Optional[Mapping[str, str]] = None,
        min_occurrences: int = 2,
        dominance_ratio: float = 1.2,
    ):
        self.task_aliases = {_compact(k): v for k, v in (task_aliases or {}).items() if _compact(k) and v}
        for target in list(self.task_aliases.values()):
            self.task_aliases.setdefault(_compact(target), target)
        self.environment_aliases = {str(k).lower().replace(" ", ""): v for k, v in (environment_aliases or {}).items()}
        self.min_occurrences = max(2, int(min_occurrences))
        self.dominance_ratio = float(dominance_ratio)

    @classmethod
    def from_config(cls, path: Optional[PathLike] = None) -> "ContextFactorAnalysis":
        cfg = load_config(path)
        return cls(
            task_aliases=cfg.get("task_aliases"),
            environment_aliases=cfg.get("environment_aliases"),
            min_occurrences=cfg.get("min_occurrences", 2),
            dominance_ratio=cfg.get("dominance_ratio", 1.2),
        )

    def protocol(self) -> Dict:
        return {
            "task": self.name,
            "min_occurrences": self.min_occurrences,
            "dominance_ratio": self.dominance_ratio,
            "task_alias_rules": len(self.task_aliases),
            "environment_aliases": dict(self.environment_aliases),
        }

    def _task(self, value: str) -> str:
        return self.task_aliases.get(_compact(value), value)

    def _environment(self, value: str) -> str:
        return self.environment_aliases.get(value.lower().replace(" ", ""), value)

    def run(self, dataset: Dataset) -> List[FacetLift]:
        scenarios = sorted(dataset, key=lambda s: s.scenario_id)
        keys = [(s.context.user, self._task(s.context.task), self._environment(s.context.environment)) for s in scenarios]
        facets = [{w.facet_id for w in s.widgets if w.facet_id} for s in scenarios]
        pairs = list(combinations(range(len(scenarios)), 2))
        same = {d: [(i, j) for i, j in pairs if keys[i][k] == keys[j][k]] for k, d in enumerate(DIMENSIONS)}

        present: Dict[str, set] = defaultdict(set)
        for index, fs in enumerate(facets):
            for f in fs:
                present[f].add(index)

        out: List[FacetLift] = []
        for facet_id, idx in sorted(present.items()):
            n = len(idx)
            if n < self.min_occurrences:
                continue
            baseline = math.comb(n, 2) / len(pairs)
            lifts = {}
            for d in DIMENSIONS:
                both = sum(1 for i, j in same[d] if i in idx and j in idx)
                rate = both / len(same[d]) if same[d] else 0.0
                lifts[d] = rate / baseline if baseline > 0 else 0.0
            ranked = sorted(lifts.items(), key=lambda kv: (-kv[1], kv[0]))
            (top, top_lift), (_, second) = ranked[0], ranked[1]
            ratio = top_lift / second if second > 0 else (math.inf if top_lift > 0 else 1.0)
            if top_lift <= 1.0:
                dominant = "none"
            elif ratio < self.dominance_ratio:
                dominant = "mixed"
            else:
                dominant = top
            facet = dataset.catalog.facets.get(facet_id)
            label = f"{dataset.catalog.apps[facet.app_id].name}: {facet.name}" if facet else facet_id
            out.append(FacetLift(facet_id, label, n, lifts["user"], lifts["task"], lifts["environment"], top, ratio, dominant))
        return out

    @staticmethod
    def counts(lifts: Sequence[FacetLift]) -> Dict[str, int]:
        c = Counter(f.dominant for f in lifts)
        return {k: c.get(k, 0) for k in ("user", "task", "environment", "mixed", "none")}

    def to_jsonl(self, lifts: Sequence[FacetLift], path: PathLike, dataset: Dataset) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as h:
            h.write(json.dumps({"type": "run", "format": "contextxr.results", "format_version": "1.0",
                                "benchmark_version": BENCHMARK_VERSION, "dataset": {"name": dataset.name, "version": dataset.version},
                                "protocol": self.protocol()}) + "\n")
            for f in lifts:
                h.write(json.dumps({"type": "facet", "benchmark_version": BENCHMARK_VERSION, **asdict(f)},
                                   default=lambda x: None if x == math.inf else x) + "\n")
            h.write(json.dumps({"type": "summary", "benchmark_version": BENCHMARK_VERSION, "n_facets": len(lifts),
                                "dominant_counts": self.counts(lifts)}) + "\n")
        return path
