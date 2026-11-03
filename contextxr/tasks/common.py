"""Shared helpers for benchmark tasks."""

from __future__ import annotations

from statistics import mean
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from contextxr.data.schema import Dataset, Scenario
from contextxr.methods.base import Suggester


class PlacedFacet(str):
    """A facet id in a next-facet history, carrying the participant's relevance tier.

    Behaves exactly like the facet id string; methods that want the tier (the paper's
    LLM prompt lists it) can read `.tier`.
    """

    tier: str

    def __new__(cls, facet_id: str, tier: str = ""):
        obj = super().__new__(cls, facet_id)
        obj.tier = tier
        return obj


def iter_folds(
    method: Suggester, dataset: Dataset, folds: Optional[Mapping[str, int]]
) -> Iterator[Tuple[Optional[int], List[Scenario]]]:
    """Yield (fold, test scenarios) after fitting `method` on the other folds.

    Without folds the method is fit once on the whole dataset.
    """
    if not folds:
        method.fit(dataset)
        yield None, list(dataset)
        return
    missing = [sid for sid in dataset.scenarios if sid not in folds]
    if missing:
        raise ValueError(f"{len(missing)} scenario(s) have no fold assignment, e.g. {missing[:3]}")
    for fold in sorted(set(folds[sid] for sid in dataset.scenarios)):
        test_ids = [sid for sid in dataset.scenarios if folds[sid] == fold]
        train_ids = [sid for sid in dataset.scenarios if folds[sid] != fold]
        method.fit(dataset.subset(train_ids))
        yield fold, [dataset.scenarios[sid] for sid in test_ids]


def mean_or_none(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    return mean(vals) if vals else None


def summarize(records: Sequence[Dict], metric_keys: Sequence[str]) -> Dict:
    """Aggregate over evaluated scenarios: mean costs, cost reduction, mean retrieval metrics."""
    evaluated = [r for r in records if r.get("evaluated")]
    manual = mean_or_none(r["cost"]["manual"] for r in evaluated)
    suggest = mean_or_none(r["cost"]["suggest"] for r in evaluated)
    out: Dict = {
        "n_scenarios": len(records),
        "n_evaluated": len(evaluated),
        "manual_cost": manual,
        "suggest_cost": suggest,
        "cost_reduction_pct": (100.0 * (suggest - manual) / manual) if manual and suggest is not None else None,
    }
    for key in metric_keys:
        out[key] = mean_or_none(r["retrieval"].get(key) if r.get("retrieval") else None for r in evaluated)
    skipped: Dict[str, int] = {}
    for r in records:
        if not r.get("evaluated"):
            skipped[r.get("skip_reason") or "unknown"] = skipped.get(r.get("skip_reason") or "unknown", 0) + 1
    out["skipped"] = skipped
    return out
