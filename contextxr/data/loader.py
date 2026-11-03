"""Loading ContextXR datasets (facet DB + events table) into `Dataset` objects."""

from __future__ import annotations

import csv
import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Union

from contextxr.data.schema import (
    RELEVANCE_RANK,
    normalize_tier,
    App,
    Context,
    Dataset,
    Edge,
    Facet,
    FacetCatalog,
    Scenario,
    Widget,
)

PathLike = Union[str, Path]

MINEXRPP_VERSION = "1.0.0"
FACET_DB_FILE = "facet_db.json"
EVENTS_FILE = "events.csv"

# ---------------------------------------------------------------------------
# Locating the data
# ---------------------------------------------------------------------------


def default_data_dir() -> Path:
    """Directory holding `facet_db.json` and `events.csv` for MineXR++.

    Resolution order: $CONTEXTXR_DATA_DIR, then `data/minexrpp` as resolved by `contextxr.paths`.
    """
    env = os.environ.get("CONTEXTXR_DATA_DIR")
    if env:
        return Path(env)
    from contextxr.paths import data_dir

    return data_dir() / "minexrpp"


def fetch_minexrpp(version: str = MINEXRPP_VERSION, cache_dir: Optional[PathLike] = None) -> Path:
    """Download MineXR++ from its DOI-hosted release.

    TODO(release): Hook for the archived release (e.g. Zenodo). Implement once the
    dataset DOI is minted: download `facet_db.json` and `events.csv` for `version`,
    verify checksums, store under `cache_dir`, and return that directory.
    """
    raise NotImplementedError(
        "MineXR++ is not yet published under a DOI. Use a source checkout (data/minexrpp/) "
        "or set CONTEXTXR_DATA_DIR to a directory containing facet_db.json and events.csv."
    )


# ---------------------------------------------------------------------------
# Facet DB
# ---------------------------------------------------------------------------


def load_facet_db(path: PathLike) -> FacetCatalog:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return catalog_from_dict(raw)


def catalog_from_dict(raw: Mapping) -> FacetCatalog:
    facets = [
        Facet(
            facet_id=f["facet_id"],
            app_id=f["app_id"],
            name=f.get("name", ""),
            description=f.get("description", ""),
            capabilities=tuple(f.get("capabilities", [])),
            legacy_ids=tuple(f.get("legacy_ids", [])),
        )
        for f in raw["facets"]
    ]
    facet_ids_by_app: Dict[str, List[str]] = OrderedDict()
    for facet in facets:
        facet_ids_by_app.setdefault(facet.app_id, []).append(facet.facet_id)
    apps = [
        App(
            app_id=a["app_id"],
            name=a.get("app_name", a["app_id"]),
            domain=a.get("app_domain", ""),
            entry_facet_id=a.get("entry_facet_id", f"{a['app_id']}.open_section"),
            capabilities=tuple(a.get("capabilities", [])),
            facet_ids=tuple(facet_ids_by_app.get(a["app_id"], [])),
        )
        for a in raw["apps"]
    ]
    edges = [
        Edge(e["source"], e["target"], e.get("capability", ""), e.get("resolution", "exact"))
        for e in raw.get("edges", [])
    ]
    return FacetCatalog(apps, facets, edges, name=raw.get("name", ""), version=raw.get("benchmark_version", ""))


# ---------------------------------------------------------------------------
# Events → scenarios
# ---------------------------------------------------------------------------


def resolve_capability_facet(capability_id: str, catalog: FacetCatalog) -> str:
    """Facet a widget-exposed capability (`app.capability`) counts toward, or "" if ambiguous/unknown.

    A capability belonging to exactly one facet of its app maps to that facet. A
    navigational capability shared by several facets maps to the app's entry facet
    when that is one of them. Other shared capabilities are not attributed.
    """
    candidates = catalog.facets_with_capability(capability_id)
    if len(candidates) == 1:
        return candidates[0]
    app_id, _, name = capability_id.partition(".")
    if len(candidates) > 1 and name.startswith("open_"):
        entry = f"{app_id}.open_section"
        if entry in candidates:
            return entry
    return ""


def derive_targets(widgets: List[Widget], catalog: FacetCatalog) -> Dict[str, str]:
    """Target facet set Y_q of a scenario with each facet's relevance tier.

    Capability tiers are merged across widgets in placement-file order (a later widget
    overrides an earlier tier for the same capability); a facet takes the highest tier
    among its capabilities.
    """
    merged: Dict[str, str] = {}
    for widget in widgets:
        merged.update(widget.capability_tiers)
    targets: Dict[str, str] = {}
    for capability_id, tier in merged.items():
        facet_id = resolve_capability_facet(capability_id, catalog)
        if not facet_id:
            continue
        tier = normalize_tier(tier)
        if facet_id not in targets or RELEVANCE_RANK.get(tier, 0) >= RELEVANCE_RANK.get(targets[facet_id], 0):
            targets[facet_id] = tier
    return dict(sorted(targets.items()))


def read_events(path: PathLike) -> List[Dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def scenarios_from_events(rows: List[Mapping[str, str]], catalog: FacetCatalog) -> Dict[str, Scenario]:
    grouped: Dict[str, List[Mapping[str, str]]] = OrderedDict()
    for row in rows:
        grouped.setdefault(row["scenario_id"], []).append(row)
    scenarios: Dict[str, Scenario] = {}
    for scenario_id, scenario_rows in grouped.items():
        widgets = [
            Widget(
                scenario_id=scenario_id,
                widget_id=r["widget_id"],
                app_id=r.get("app_id", ""),
                facet_id=r.get("facet_id", ""),
                capabilities=tuple(json.loads(r["capabilities"] or "{}").items()),
                widget_desc=r.get("widget_desc", ""),
                screen_desc=r.get("screen_desc", ""),
            )
            for r in scenario_rows
        ]
        first = scenario_rows[0]
        context = Context(user=first["participant_id"], task=first["task"], environment=first["environment"])
        targets = derive_targets(widgets, catalog)
        scenarios[scenario_id] = Scenario(scenario_id, context, tuple(targets.items()), tuple(widgets))
    return scenarios


def load_dataset(data_dir: PathLike, *, name: str = "") -> Dataset:
    """Load any dataset in the ContextXR format from a directory with facet_db.json + events.csv."""
    data_dir = Path(data_dir)
    catalog = load_facet_db(data_dir / FACET_DB_FILE)
    scenarios = scenarios_from_events(read_events(data_dir / EVENTS_FILE), catalog)
    return Dataset(catalog, scenarios, name=name or catalog.name, version=catalog.version)


def load_minexrpp(data_dir: Optional[PathLike] = None, *, version: str = MINEXRPP_VERSION) -> Dataset:
    """Load MineXR++ (paper §3.2).

    Reads from `data_dir`, $CONTEXTXR_DATA_DIR, or the source checkout's `data/minexrpp/`.
    """
    directory = Path(data_dir) if data_dir is not None else default_data_dir()
    if not (directory / FACET_DB_FILE).exists():
        # Hook for the DOI-hosted release; currently raises with instructions.
        directory = fetch_minexrpp(version)
    dataset = load_dataset(directory, name="MineXR++")
    if dataset.version and dataset.version != version:
        raise ValueError(f"Requested MineXR++ {version}, found {dataset.version} in {directory}")
    return dataset


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------


def configs_dir() -> Path:
    from contextxr.paths import configs_dir as _configs_dir

    return _configs_dir()


def load_folds(path: Optional[PathLike] = None) -> Dict[str, int]:
    """Scenario → fold index (1-based) exactly as used in the paper."""
    path = Path(path) if path else configs_dir() / "splits" / "cv5_seed42.json"
    return {k: int(v) for k, v in json.loads(path.read_text(encoding="utf-8"))["folds"].items()}


def load_next_orders(path: Optional[PathLike] = None) -> Dict[str, List[str]]:
    """Scenario → order in which targets are revealed in next facet suggestion."""
    path = Path(path) if path else configs_dir() / "splits" / "next_order_seed42.json"
    return {k: list(v) for k, v in json.loads(path.read_text(encoding="utf-8"))["orders"].items()}
