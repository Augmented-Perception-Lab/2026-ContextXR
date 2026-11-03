"""Navigation & search cost (paper §3.4.1).

Given a target facet set Y and suggestions Ŷ, every reachable target f ∈ Y is put in
exactly one of

    H  exact hits          f itself is among the visible suggestions
    A  same-app adjustments a visible suggestion from f's app is an entry point to f
    M  misses              the user falls back to manual access

and

    C_manual(Y)     = c_open_menu + Σ_{f∈Y} [c_app_scan(f) + c_facet_nav(f)]
    C_suggest(Y, Ŷ) = c_suggest_scan(Ŷ) + Σ_{f∈A} c_adjust(f)
                      + Σ_{f∈M} [c_app_scan(f) + c_facet_nav(f)] + 1[|M|>0] · c_open_menu

Two assignment policies reproduce the paper's two tasks:

* `score_episode` (initial facet suggestion): exact hits are claimed greedily in rank
  order, each suggestion serving at most one target. The remaining suggestions are then
  assigned to remaining targets one-to-one so as to minimise total cost. An adjustment
  is used only when it is no more expensive than manual access (otherwise the target is
  a miss); ties prefer fewer misses, then fewer hops, then better-ranked suggestions.
* `score_step` (next facet suggestion): one target per step. A hit if it is visible;
  otherwise the same-app suggestion with the fewest hops (then best rank, then id),
  regardless of whether manual access would be cheaper; otherwise a miss.

Only the top `visible_limit` (10) suggestions are considered. Targets that cannot be
reached from their app's entry facet are excluded from both costs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from contextxr.data.schema import FacetCatalog, FacetId
from contextxr.metrics.cost_model import CostModel

VISIBLE_LIMIT = 10

HIT, ADJUST, MISS = "H", "A", "M"


@dataclass
class TargetOutcome:
    """How one target facet was reached, with its cost terms (manual and assisted)."""

    facet_id: FacetId
    outcome: str  # "H" | "A" | "M"
    source_facet_id: Optional[FacetId] = None  # suggestion used (H/A)
    source_rank: Optional[int] = None
    hops: Optional[int] = None
    app_scan: float = 0.0  # c_app_scan(f)
    facet_nav: float = 0.0  # c_facet_nav(f)
    adjust: float = 0.0  # c_adjust(f), A only
    same_app_suggestion_visible: bool = False  # M only: a same-app suggestion existed but was not worth using

    @property
    def manual_access(self) -> float:
        return self.app_scan + self.facet_nav


@dataclass
class EpisodeCost:
    """Costs of reaching one target set (a scenario, or one step of a timeline)."""

    targets: List[TargetOutcome]
    suggestions: List[FacetId]
    open_menu: float
    suggest_scan: float
    unreachable_targets: List[FacetId] = field(default_factory=list)
    proxy: bool = False  # method gave no suggestions; assisted cost := manual cost

    @property
    def hits(self) -> List[FacetId]:
        return [t.facet_id for t in self.targets if t.outcome == HIT]

    @property
    def adjustments(self) -> List[FacetId]:
        return [t.facet_id for t in self.targets if t.outcome == ADJUST]

    @property
    def misses(self) -> List[FacetId]:
        return [t.facet_id for t in self.targets if t.outcome == MISS]

    @property
    def manual_cost(self) -> float:
        if not self.targets:
            return 0.0
        return self.open_menu + sum(t.manual_access for t in self.targets)

    @property
    def suggest_cost(self) -> float:
        if self.proxy:
            return self.manual_cost
        if not self.targets:
            return 0.0
        misses = [t for t in self.targets if t.outcome == MISS]
        return (
            self.suggest_scan
            + sum(t.adjust for t in self.targets if t.outcome == ADJUST)
            + sum(t.manual_access for t in misses)
            + (self.open_menu if misses else 0.0)
        )

    def terms(self) -> Dict[str, float]:
        """Cost terms of C_manual and C_suggest, for logging."""
        misses = [t for t in self.targets if t.outcome == MISS]
        return {
            "manual_open_menu": self.open_menu if self.targets else 0.0,
            "manual_app_scan": sum(t.app_scan for t in self.targets),
            "manual_facet_nav": sum(t.facet_nav for t in self.targets),
            "manual_total": self.manual_cost,
            "suggest_scan": 0.0 if self.proxy or not self.targets else self.suggest_scan,
            "suggest_adjust": 0.0 if self.proxy else sum(t.adjust for t in self.targets if t.outcome == ADJUST),
            "suggest_miss_app_scan": 0.0 if self.proxy else sum(t.app_scan for t in misses),
            "suggest_miss_facet_nav": 0.0 if self.proxy else sum(t.facet_nav for t in misses),
            "suggest_open_menu": 0.0 if self.proxy else (self.open_menu if misses else 0.0),
            "suggest_total": self.suggest_cost,
        }

    def to_dict(self) -> Dict:
        return {
            "partition": {"H": self.hits, "A": self.adjustments, "M": self.misses},
            "targets": [asdict(t) for t in self.targets],
            "unreachable_targets": list(self.unreachable_targets),
            "proxy": self.proxy,
            "terms": self.terms(),
        }


def visible_suggestions(suggestions: Sequence[FacetId], limit: int = VISIBLE_LIMIT) -> List[FacetId]:
    """De-duplicated suggestions in rank order, truncated to what the user sees."""
    out: List[FacetId] = []
    for facet_id in suggestions:
        if facet_id and facet_id not in out:
            out.append(facet_id)
        if len(out) >= limit:
            break
    return out


def _app_of(catalog: FacetCatalog, facet_id: FacetId) -> str:
    return catalog.app_of(facet_id) if facet_id in catalog else facet_id.split(".", 1)[0]


def _manual_terms(
    facet_id: FacetId, catalog: FacetCatalog, cost_model: CostModel, app_scan_apps: Optional[set]
) -> Optional[Tuple[float, float]]:
    if facet_id not in catalog:
        return None
    facet = catalog.facet(facet_id)
    nav = cost_model.facet_nav(facet, catalog.graph(facet.app_id))
    if nav is None:
        return None
    if app_scan_apps is not None and facet.app_id not in app_scan_apps:
        app = 0.0
    else:
        app = cost_model.app_scan(facet)
    return app, nav


def _adjustment(
    target: FacetId, source: FacetId, catalog: FacetCatalog, cost_model: CostModel
) -> Optional[Tuple[float, int]]:
    if source not in catalog or target not in catalog:
        return None
    graph = catalog.graph_of(target)
    if source not in graph:
        return None
    cost = cost_model.adjust(catalog.facet(target), catalog.facet(source), graph)
    if cost is None:
        return None
    hops = graph.hops(source, target, directed=False)
    return float(cost), int(hops if hops is not None else 0)


def score_episode(
    targets: Sequence[FacetId],
    suggestions: Sequence[FacetId],
    catalog: FacetCatalog,
    cost_model: CostModel,
    *,
    visible_limit: int = VISIBLE_LIMIT,
) -> EpisodeCost:
    """Cost of reaching all `targets` at once (initial facet suggestion)."""
    visible = visible_suggestions(suggestions, visible_limit)
    rows: List[TargetOutcome] = []
    unreachable: List[FacetId] = []
    for facet_id in targets:
        manual = _manual_terms(facet_id, catalog, cost_model, None)
        if manual is None:
            unreachable.append(facet_id)
            continue
        rows.append(TargetOutcome(facet_id=facet_id, outcome=MISS, app_scan=manual[0], facet_nav=manual[1]))

    # 1) Exact hits: each suggestion (in rank order) claims the first unmatched equal target.
    used_predictions: set = set()
    unmatched = list(range(len(rows)))
    for p_index, facet_id in enumerate(visible):
        for r_index in unmatched:
            if rows[r_index].facet_id == facet_id:
                row = rows[r_index]
                row.outcome, row.source_facet_id, row.source_rank, row.hops = HIT, facet_id, p_index + 1, 0
                used_predictions.add(p_index)
                unmatched.remove(r_index)
                break

    # 2) Same-app adjustments: optimal one-to-one assignment of remaining suggestions.
    remaining_preds = [(i, f) for i, f in enumerate(visible) if i not in used_predictions]
    bit_of = {p_index: bit for bit, (p_index, _) in enumerate(remaining_preds)}
    candidates: Dict[int, List[Tuple[float, int, float, FacetId, int]]] = {}
    for r_index in unmatched:
        target = rows[r_index].facet_id
        target_app = _app_of(catalog, target)
        options = []
        for p_index, source in remaining_preds:
            if _app_of(catalog, source) != target_app:
                continue
            adj = _adjustment(target, source, catalog, cost_model)
            if adj is None:
                continue
            options.append((adj[0], adj[1], float(p_index + 1), source, p_index))
        candidates[r_index] = options

    open_cost = float(cost_model.open_menu())
    memo: Dict[Tuple[int, int, bool], Tuple[Tuple[float, int, int, float], Dict[int, tuple]]] = {}

    def solve(pos: int, used_mask: int, fallback_used: bool):
        key = (pos, used_mask, fallback_used)
        if key in memo:
            return memo[key]
        if pos >= len(unmatched):
            return (0.0, 0, 0, 0.0), {}
        r_index = unmatched[pos]
        nxt_key, nxt_assign = solve(pos + 1, used_mask, True)
        best_key = (
            rows[r_index].manual_access + (open_cost if not fallback_used else 0.0) + nxt_key[0],
            1 + nxt_key[1],
            nxt_key[2],
            nxt_key[3],
        )
        best_assign = dict(nxt_assign)
        for cand in candidates.get(r_index, []):
            bit = 1 << bit_of[cand[4]]
            if used_mask & bit:
                continue
            nxt_key, nxt_assign = solve(pos + 1, used_mask | bit, fallback_used)
            cand_key = (cand[0] + nxt_key[0], nxt_key[1], cand[1] + nxt_key[2], cand[2] + nxt_key[3])
            if cand_key < best_key:
                best_key = cand_key
                best_assign = dict(nxt_assign)
                best_assign[r_index] = cand
        memo[key] = (best_key, best_assign)
        return memo[key]

    _, assignment = solve(0, 0, False)
    visible_apps = {_app_of(catalog, f) for f in visible}
    for r_index in unmatched:
        row = rows[r_index]
        if r_index in assignment:
            cost, hops, rank, source, _ = assignment[r_index]
            row.outcome, row.source_facet_id, row.source_rank, row.hops, row.adjust = ADJUST, source, int(rank), hops, cost
        else:
            row.same_app_suggestion_visible = _app_of(catalog, row.facet_id) in visible_apps

    scan = cost_model.suggest_scan(visible, len(rows)) if rows else 0.0
    return EpisodeCost(rows, list(visible), open_cost, float(scan), unreachable)


def score_step(
    target: FacetId,
    suggestions: Sequence[FacetId],
    catalog: FacetCatalog,
    cost_model: CostModel,
    *,
    visible_limit: int = VISIBLE_LIMIT,
    app_scan_apps: Optional[set] = None,
    proxy: bool = False,
) -> EpisodeCost:
    """Cost of reaching the single next `target` (one step of next facet suggestion).

    `app_scan_apps`, if given, restricts c_app_scan to targets whose app is in the set
    (others cost 0 to locate); see `NextFacetTask.app_scan_scope`. `proxy=True` marks a
    step where the method produced no suggestions: its assisted cost equals the manual cost.
    """
    visible = visible_suggestions(suggestions, visible_limit)
    manual = _manual_terms(target, catalog, cost_model, app_scan_apps)
    if manual is None:
        return EpisodeCost([], list(visible), float(cost_model.open_menu()), 0.0, [target], proxy=proxy)
    row = TargetOutcome(facet_id=target, outcome=MISS, app_scan=manual[0], facet_nav=manual[1])
    if not proxy:
        if target in visible:
            row.outcome, row.source_facet_id, row.source_rank, row.hops = HIT, target, visible.index(target) + 1, 0
        else:
            target_app = _app_of(catalog, target)
            best = None
            for p_index, source in enumerate(visible):
                if _app_of(catalog, source) != target_app:
                    continue
                adj = _adjustment(target, source, catalog, cost_model)
                if adj is None:
                    continue
                key = (adj[0], adj[1], p_index + 1, source)
                if best is None or key < best:
                    best = key
            if best is not None:
                row.outcome, row.adjust, row.hops, row.source_rank, row.source_facet_id = ADJUST, best[0], best[1], best[2], best[3]
            else:
                row.same_app_suggestion_visible = False
    scan = 0.0 if proxy else cost_model.suggest_scan(visible, 1)
    return EpisodeCost([row], list(visible), float(cost_model.open_menu()), float(scan), [], proxy=proxy)
