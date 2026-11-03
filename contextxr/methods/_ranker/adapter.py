"""Bridge between ContextXR datasets and the reference ranker's event format."""

from __future__ import annotations

from typing import Dict, List, Optional

from contextxr.data.schema import Context, Dataset, FacetCatalog

from .loader import EventDataset, FacetCatalogBundle, build_event_dataset, catalog_from_payload
from .model import ContextFacetRanker, RankerConfig, ScoreWeights
from .normalization import normalize_label


def catalog_payload(catalog: FacetCatalog) -> dict:
    """Facet DB in the nested layout the reference loader reads (apps → facets)."""
    apps = []
    for app in catalog.apps.values():
        apps.append(
            {
                "app_id": app.app_id,
                "app_name": app.name,
                "app_domain": app.domain,
                "capabilities": list(app.capabilities),
                "facets": [
                    {
                        "facet_id": fid,
                        "name": catalog.facets[fid].name,
                        "description": catalog.facets[fid].description,
                        "capabilities": list(catalog.facets[fid].capabilities),
                    }
                    for fid in app.facet_ids
                ],
            }
        )
    return {"apps": apps}


def training_rows(dataset: Dataset) -> List[Dict[str, str]]:
    """One event row per placed widget that resolves to a facet (680 rows for MineXR++)."""
    rows = []
    for scenario in dataset:
        for widget in scenario.widgets:
            if not widget.facet_id:
                continue
            rows.append(
                {
                    "event_id": f"{scenario.scenario_id}::{widget.widget_id}",
                    "scenario_id": scenario.scenario_id,
                    "user": scenario.context.user,
                    "task": scenario.context.task,
                    "environment": scenario.context.environment,
                    "facet": widget.facet_id,
                    "app": widget.app_id,
                    "capabilities": "|".join(cap for cap, _ in widget.capabilities),
                }
            )
    return rows


class RankerBackend:
    """Fits the reference `ContextFacetRanker` on a training split and maps ids back."""

    def __init__(self, *, variant: str, mode: str = "TEU", weights: Optional[ScoreWeights] = None,
                 config: Optional[RankerConfig] = None):
        self.variant = variant
        self.mode = mode
        self.config = config or RankerConfig()
        if weights is not None:
            self.config.default_weights = weights
        self.ranker: Optional[ContextFacetRanker] = None
        self._bundle: Optional[FacetCatalogBundle] = None
        self._catalog_key: Optional[int] = None
        self._to_catalog_id: Dict[str, str] = {}

    def _catalog_bundle(self, catalog: FacetCatalog) -> FacetCatalogBundle:
        if self._bundle is None or self._catalog_key != id(catalog):
            self._bundle = catalog_from_payload(catalog_payload(catalog))
            self._catalog_key = id(catalog)
            self._to_catalog_id = {normalize_label(fid): fid for fid in catalog.facets}
        return self._bundle

    def fit(self, train: Dataset) -> None:
        bundle = self._catalog_bundle(train.catalog)
        events: EventDataset = build_event_dataset(training_rows(train), facet_catalog=bundle)
        self.ranker = ContextFacetRanker(config=self.config)
        self.ranker.fit(events)

    def rank(self, context: Context, catalog: FacetCatalog, history: Optional[List[str]], k: int) -> List[str]:
        if self.ranker is None:
            raise RuntimeError("fit() must be called before suggest()")
        self._catalog_bundle(catalog)
        result = self.ranker.rank(
            task=context.task,
            environment=context.environment,
            user=context.user,
            mode=self.mode,
            top_k=k,
            variant=self.variant,
            prior_facet_ids=list(history) if history else None,
            exclude_facet_ids=list(history) if history else None,
        )
        return [self._to_catalog_id.get(row["facet_id"], row["facet_id"]) for row in result["results"]]
