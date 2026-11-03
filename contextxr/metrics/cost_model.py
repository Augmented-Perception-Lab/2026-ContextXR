"""Per-step costs of the navigation & search cost model (paper §3.4.1).

A `CostModel` prices the elementary steps of the simulated user. The partition of
targets into hits / adjustments / misses and the totals C_manual and C_suggest are
computed in `contextxr.metrics.nav_search_cost`; subclass `CostModel` to change what
steps cost (see examples/06_custom_cost_model.ipynb).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Union

from contextxr.data.schema import Dataset, Facet, FacetGraph

PathLike = Union[str, Path]


class CostModel:
    """Costs of the steps a simulated user takes to reach a facet.

    `bind(dataset)` is called by the runner before scoring, so dataset-dependent
    quantities (e.g. the app list order) can be computed.
    """

    name: str = "cost_model"

    def bind(self, dataset: Dataset) -> "CostModel":
        return self

    def open_menu(self) -> float:
        """c_open_menu: opening the app list (paid once per episode with at least one miss)."""
        raise NotImplementedError

    def app_scan(self, facet: Facet) -> float:
        """c_app_scan(f): locating the app of facet f in the app list."""
        raise NotImplementedError

    def facet_nav(self, facet: Facet, graph: FacetGraph) -> Optional[float]:
        """c_facet_nav(f): navigating inside the app from its entry facet to f (None if unreachable)."""
        raise NotImplementedError

    def suggest_scan(self, suggested: Sequence[str], n_targets: int = 1) -> float:
        """c_suggest_scan(Ŷ): scanning the surfaced suggestions while looking for `n_targets` facets."""
        raise NotImplementedError

    def adjust(self, target: Facet, suggested: Facet, graph: FacetGraph) -> Optional[float]:
        """c_adjust(f): reaching target f from a surfaced facet of the same app (None if unreachable)."""
        raise NotImplementedError


@dataclass(frozen=True)
class CostParams:
    """Parameters of `DefaultCostModel` (defaults reproduce the paper; configs/cost_default.yaml)."""

    open_menu: float = 0.0
    app_page_size: int = 20
    app_page_cost: float = 1.0
    facet_step_cost: float = 1.0
    count_entry_facet: bool = True
    suggest_scan_per_target: float = 0.5
    adjust_per_hop: float = 1.0
    adjust_directed: bool = False
    app_order: str = "occurrence"  # "occurrence" (most-used apps first) or "name"

    @classmethod
    def from_mapping(cls, raw: Mapping) -> "CostParams":
        known = {k: raw[k] for k in cls.__dataclass_fields__ if k in raw}
        unknown = set(raw) - set(known)
        if unknown:
            raise ValueError(f"Unknown cost parameters: {sorted(unknown)}")
        return cls(**known)


def default_cost_config_path() -> Path:
    from contextxr.paths import configs_dir

    return configs_dir() / "cost_default.yaml"


def load_cost_params(path: Optional[PathLike] = None) -> CostParams:
    path = Path(path) if path else default_cost_config_path()
    if not path.exists():
        return CostParams()
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return CostParams.from_mapping(raw.get("cost_model", raw))


def app_occurrence_counts(dataset: Dataset) -> Counter:
    """Number of placed elements whose exposed capabilities touch each app."""
    counts: Counter = Counter()
    for widget in dataset.widgets():
        counts.update({cap.split(".", 1)[0] for cap, _ in widget.capabilities if "." in cap})
    return counts


class DefaultCostModel(CostModel):
    """The paper's fixed-step model.

    - App list: apps ordered by how often participants used them (ties by name), shown in
      pages of 20; finding an app costs one unit per page inspected: ceil(position / 20).
    - Facet navigation: one unit per facet visited on the shortest directed path from the
      app's entry facet (Open Section), counting the entry facet itself.
    - Suggestion scan: 0.5 per target sought (only the top 10 suggestions are visible).
    - Adjustment: one unit per hop between the surfaced same-app facet and the target,
      ignoring edge direction.
    - Opening the app list: 0.
    """

    name = "default"

    def __init__(self, params: Optional[CostParams] = None, *, app_positions: Optional[Dict[str, int]] = None):
        self.params = params or load_cost_params()
        self.app_positions: Dict[str, int] = dict(app_positions or {})

    @classmethod
    def from_config(cls, path: Optional[PathLike] = None) -> "DefaultCostModel":
        return cls(load_cost_params(path))

    def bind(self, dataset: Dataset) -> "DefaultCostModel":
        apps = list(dataset.catalog.apps.values())
        if self.params.app_order == "occurrence":
            counts = app_occurrence_counts(dataset)
            ordered = sorted(apps, key=lambda a: (-counts.get(a.app_id, 0), a.name.lower(), a.app_id))
        elif self.params.app_order == "name":
            ordered = sorted(apps, key=lambda a: (a.name.lower(), a.app_id))
        else:
            raise ValueError(f"Unknown app_order: {self.params.app_order}")
        self.app_positions = {app.app_id: i for i, app in enumerate(ordered, start=1)}
        return self

    def open_menu(self) -> float:
        return float(self.params.open_menu)

    def app_scan(self, facet: Facet) -> float:
        position = self.app_positions.get(facet.app_id)
        if position is None:
            raise KeyError(f"App '{facet.app_id}' has no list position; call bind(dataset) first")
        pages = math.ceil(position / self.params.app_page_size)
        return pages * float(self.params.app_page_cost)

    def facet_nav(self, facet: Facet, graph: FacetGraph) -> Optional[float]:
        path = graph.path_from_entry(facet.facet_id)
        if path is None:
            return None
        steps = len(path) if self.params.count_entry_facet else len(path) - 1
        return steps * float(self.params.facet_step_cost)

    def suggest_scan(self, suggested: Sequence[str], n_targets: int = 1) -> float:
        return float(self.params.suggest_scan_per_target) * n_targets

    def adjust(self, target: Facet, suggested: Facet, graph: FacetGraph) -> Optional[float]:
        hops = graph.hops(suggested.facet_id, target.facet_id, directed=self.params.adjust_directed)
        if hops is None:
            return None
        return hops * float(self.params.adjust_per_hop)

    def describe(self) -> Dict:
        return {"name": self.name, **asdict(self.params)}
