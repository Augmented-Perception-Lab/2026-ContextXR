"""Experiment 3: next facet suggestion (paper §4.3).

Each scenario's targets are revealed one at a time in a fixed order
(configs/splits/next_order_seed42.json). At step t the method sees the context and the
t facets already placed (`history`) and suggests k facets; the step's target is the
(t+1)-th facet. Each step is costed on its own (`score_step`); a scenario's cost is
the sum over its steps, and retrieval metrics are averaged over the scenario's queried
steps (against the targets not yet placed) before averaging over scenarios, so long
scenarios do not dominate.

Protocol options (defaults reproduce the paper):

* ``unmatched`` — what happens when the method cannot suggest at a step
  (`SuggestionUnavailable`): ``"manual_proxy"`` (paper) scores the step at manual
  cost. If the method had nothing to go on (``no_matching_examples``, e.g. few-shot
  prompting without matching examples) its suggestions count as empty (retrieval
  metrics 0); if the method failed (e.g. an unparseable LLM response) the step is left
  out of the retrieval averages. ``"exclude"`` drops scenarios with any such step.
* ``app_scan_scope`` — ``"widget_apps"`` (paper) charges c_app_scan only for targets
  whose app the participant placed an element of; otherwise locating the app costs 0
  (this affects one MineXR++ target). ``"all"`` always charges it, as in initial
  facet suggestion.
* ``final_step_query`` — whether the method is also queried once every target is
  placed (no target remains, so the step costs 0 but enters the retrieval averages):
  ``"never"`` (default; the paper's popularity and relational runs) or
  ``"if_uncovered_capabilities"`` (the paper's LLM runs: queried when some exposed
  capability belongs to no single facet).
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Set

from contextxr.data.loader import load_next_orders
from contextxr.data.schema import Dataset, FacetCatalog, Scenario
from contextxr.methods.base import SuggestionUnavailable, Suggester
from contextxr.metrics.cost_model import CostModel
from contextxr.metrics.nav_search_cost import VISIBLE_LIMIT, score_step, visible_suggestions
from contextxr.metrics.retrieval import set_metrics
from contextxr.tasks.common import PlacedFacet, iter_folds, mean_or_none, summarize

METRICS = ("recall", "f1", "hit", "precision")
# SuggestionUnavailable reasons scored as an empty suggestion list; other reasons are method failures.
EMPTY_PREDICTION_REASONS = frozenset({"no_matching_examples"})
UNMATCHED = ("manual_proxy", "exclude")
APP_SCAN_SCOPES = ("widget_apps", "all")
FINAL_STEP_QUERY = ("never", "if_uncovered_capabilities")


def has_unattributed_capabilities(scenario: Scenario, catalog: FacetCatalog) -> bool:
    """True if some capability the scenario exposes belongs to zero or several facets."""
    merged: Dict[str, str] = {}
    for widget in scenario.widgets:
        merged.update(widget.capability_tiers)
    return any(len(catalog.facets_with_capability(cap)) != 1 for cap in merged)


class NextFacetTask:
    name = "next"

    def __init__(
        self,
        k: int = 10,
        *,
        orders: Optional[Mapping[str, List[str]]] = None,
        unmatched: str = "manual_proxy",
        app_scan_scope: str = "widget_apps",
        final_step_query: str = "never",
        visible_limit: int = VISIBLE_LIMIT,
    ):
        if unmatched not in UNMATCHED:
            raise ValueError(f"unmatched must be one of {UNMATCHED}")
        if app_scan_scope not in APP_SCAN_SCOPES:
            raise ValueError(f"app_scan_scope must be one of {APP_SCAN_SCOPES}")
        if final_step_query not in FINAL_STEP_QUERY:
            raise ValueError(f"final_step_query must be one of {FINAL_STEP_QUERY}")
        self.k = k
        self._orders = dict(orders) if orders is not None else None
        self.unmatched = unmatched
        self.app_scan_scope = app_scan_scope
        self.final_step_query = final_step_query
        self.visible_limit = visible_limit

    def protocol(self) -> Dict:
        return {
            "task": self.name,
            "k": self.k,
            "visible_limit": self.visible_limit,
            "unmatched": self.unmatched,
            "app_scan_scope": self.app_scan_scope,
            "final_step_query": self.final_step_query,
            "orders": "custom" if self._orders is not None else "configs/splits/next_order_seed42.json",
        }

    def orders(self, dataset: Dataset) -> Dict[str, List[str]]:
        if self._orders is not None:
            return self._orders
        try:
            orders = load_next_orders()
        except FileNotFoundError:
            orders = {}
        if set(orders) >= set(dataset.scenarios) and all(
            sorted(orders[s]) == sorted(dataset.scenarios[s].target_ids) for s in dataset.scenarios
        ):
            return orders
        # Not MineXR++: fall back to placing targets in sorted order (deterministic).
        return {sid: sorted(s.target_ids) for sid, s in dataset.scenarios.items()}

    def evaluate(
        self,
        method: Suggester,
        dataset: Dataset,
        cost_model: CostModel,
        folds: Optional[Mapping[str, int]] = None,
    ) -> List[Dict]:
        catalog = dataset.catalog
        orders = self.orders(dataset)
        records: List[Dict] = []
        for fold, scenarios in iter_folds(method, dataset, folds):
            for scenario in scenarios:
                records.append(self._evaluate_scenario(method, scenario, catalog, cost_model, orders[scenario.scenario_id], fold))
        records.sort(key=lambda r: r["scenario_id"])
        return records

    def _evaluate_scenario(self, method, scenario, catalog, cost_model, order, fold) -> Dict:
        tiers = scenario.target_tiers
        widget_apps: Optional[Set[str]] = None
        if self.app_scan_scope == "widget_apps":
            widget_apps = {w.app_id for w in scenario.widgets if w.facet_id and w.app_id}
        n = len(order)
        query_final = self.final_step_query == "if_uncovered_capabilities" and has_unattributed_capabilities(scenario, catalog)
        steps: List[Dict] = []
        any_unavailable = False
        for t in range(0, n + 1):
            if t == n and not query_final:
                break
            history = [PlacedFacet(f, tiers.get(f, "")) for f in order[:t]]
            remaining = [f for f in order[t:]]
            target = order[t] if t < n else None
            step: Dict = {"t": t, "history": list(map(str, history)), "target": target}
            try:
                suggestions = list(method.suggest(scenario.context, catalog, history, self.k))
                unavailable = None
            except SuggestionUnavailable as exc:
                suggestions, unavailable = [], exc
                any_unavailable = True
                step.update(unavailable=exc.reason, unavailable_detail=exc.detail)
            step["suggestions"] = suggestions
            if unavailable is not None and unavailable.reason not in EMPTY_PREDICTION_REASONS:
                step["retrieval"] = None  # method failure: costed as manual, not scored for retrieval
            else:
                step["retrieval"] = set_metrics(visible_suggestions(suggestions, self.k), remaining)
            if target is not None:
                episode = score_step(
                    target, suggestions, catalog, cost_model,
                    visible_limit=self.visible_limit, app_scan_apps=widget_apps, proxy=unavailable is not None,
                )
                step["cost"] = {"manual": episode.manual_cost, "suggest": episode.suggest_cost, **episode.terms()}
                step["hsm"] = episode.to_dict()
            else:
                step["cost"] = {"manual": 0.0, "suggest": 0.0}
            steps.append(step)

        record: Dict = {
            "scenario_id": scenario.scenario_id,
            "fold": fold,
            "context": {"user": scenario.context.user, "task": scenario.context.task, "environment": scenario.context.environment},
            "targets": sorted(scenario.target_ids),
            "order": list(order),
            "steps": steps,
        }
        if any_unavailable and self.unmatched == "exclude":
            record.update(evaluated=False, skip_reason="unmatched", skip_detail="method could not suggest at some step")
            return record
        record.update(
            evaluated=True,
            cost={
                "manual": sum(s["cost"]["manual"] for s in steps),
                "suggest": sum(s["cost"]["suggest"] for s in steps),
                "proxy_steps": sum(1 for s in steps if "unavailable" in s and s["target"] is not None),
            },
            retrieval={key: mean_or_none(s["retrieval"][key] for s in steps if s["retrieval"]) for key in METRICS}
            if any(s["retrieval"] for s in steps) else None,
        )
        return record

    def summarize(self, records: List[Dict]) -> Dict:
        return summarize(records, METRICS)
