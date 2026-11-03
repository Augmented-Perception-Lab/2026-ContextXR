"""Experiment 2: initial facet suggestion (paper §4.2).

When a user enters context q = (u, t, e), the method suggests k facets before any
interaction. Each scenario is scored against its full target set Y_q with the
navigation & search cost (all targets reached from one suggestion list) and top-k
retrieval metrics. Methods are fit per cross-validation fold on training scenarios.
A scenario for which the method cannot produce suggestions (e.g. few-shot prompting
without matching examples, or a failed LLM response) is not evaluated, and the
manual baseline is averaged over the same scenarios.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional

from contextxr.data.schema import Dataset
from contextxr.methods.base import SuggestionUnavailable, Suggester
from contextxr.metrics.cost_model import CostModel
from contextxr.metrics.nav_search_cost import VISIBLE_LIMIT, score_episode
from contextxr.metrics.retrieval import top_k_metrics
from contextxr.tasks.common import iter_folds, summarize

METRICS = ("recall", "f1", "hit", "precision", "mrr")


class InitialFacetTask:
    name = "initial"

    def __init__(self, k: int = 10, visible_limit: int = VISIBLE_LIMIT):
        self.k = k
        self.visible_limit = visible_limit

    def protocol(self) -> Dict:
        return {"task": self.name, "k": self.k, "visible_limit": self.visible_limit}

    def evaluate(
        self,
        method: Suggester,
        dataset: Dataset,
        cost_model: CostModel,
        folds: Optional[Mapping[str, int]] = None,
    ) -> List[Dict]:
        catalog = dataset.catalog
        records: List[Dict] = []
        for fold, scenarios in iter_folds(method, dataset, folds):
            for scenario in scenarios:
                targets = sorted(scenario.target_ids)
                record: Dict = {
                    "scenario_id": scenario.scenario_id,
                    "fold": fold,
                    "context": {
                        "user": scenario.context.user,
                        "task": scenario.context.task,
                        "environment": scenario.context.environment,
                    },
                    "targets": targets,
                }
                try:
                    suggestions = list(method.suggest(scenario.context, catalog, None, self.k))
                except SuggestionUnavailable as exc:
                    record.update(evaluated=False, skip_reason=exc.reason, skip_detail=exc.detail)
                    records.append(record)
                    continue
                episode = score_episode(targets, suggestions, catalog, cost_model, visible_limit=self.visible_limit)
                record.update(
                    evaluated=True,
                    suggestions=suggestions,
                    cost={"manual": episode.manual_cost, "suggest": episode.suggest_cost, **episode.terms()},
                    hsm=episode.to_dict(),
                    retrieval=top_k_metrics(suggestions, targets, self.k),
                )
                records.append(record)
        records.sort(key=lambda r: r["scenario_id"])
        return records

    def summarize(self, records: List[Dict]) -> Dict:
        return summarize(records, METRICS)
