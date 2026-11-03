"""Supplementary retrieval metrics (paper §3.4.2): Recall@K, F1@K, Hit@K (+ Precision@K, MRR@K)."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Sequence

from contextxr.metrics.nav_search_cost import visible_suggestions


def top_k_metrics(suggestions: Sequence[str], targets: Iterable[str], k: int = 10) -> Optional[Dict[str, float]]:
    """Metrics of the top-k de-duplicated suggestions against a target set.

    Precision@K divides by K. Returns None when there are no targets.
    Used for initial facet suggestion.
    """
    gold = {t for t in targets if t}
    if not gold:
        return None
    ranked = visible_suggestions(suggestions, k)
    hits = sum(1 for f in ranked if f in gold)
    precision = hits / float(max(1, k))
    recall = hits / float(len(gold))
    f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
    mrr = next((1.0 / i for i, f in enumerate(ranked, start=1) if f in gold), 0.0)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "hit": 1.0 if hits else 0.0,
        "mrr": mrr,
    }


def set_metrics(predicted: Iterable[str], targets: Iterable[str], *, digits: Optional[int] = 4) -> Dict[str, float]:
    """Set-based precision/recall/F1/hit of a suggestion set (precision divides by |predicted|).

    Used per step in next facet suggestion against the targets not yet placed. Values are
    rounded to `digits` (4 in the paper's pipeline) before any averaging.
    """
    pred, gold = set(predicted), set(targets)
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    if digits is not None:
        p, r, f1 = round(p, digits), round(r, digits), round(f1, digits)
    return {"precision": p, "recall": r, "f1": f1, "hit": 1.0 if tp > 0 else 0.0}
