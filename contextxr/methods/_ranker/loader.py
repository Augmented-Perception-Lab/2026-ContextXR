"""Data loading and schema construction for the context facet ranker.

Ported from the paper's research code (context_facet_ranker); logic unchanged.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from .normalization import (
    capability_name,
    clean_display_label,
    dedupe_preserve,
    normalize_column_name,
    normalize_label,
    split_multi_value_field,
)
from .schema import (
    EntityRegistry,
    SchemaTables,
    add_relation,
    build_empty_relation_adjacency,
    build_empty_relation_counts,
    registries_to_schema,
)


@dataclass(frozen=True)
class AppCatalogEntry:
    app_id: str
    app_label: str
    category: str
    capabilities: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FacetCatalogEntry:
    facet_id: str
    facet_label: str
    facet_description: str
    app_id: str
    app_label: str
    app_category: str
    capabilities: Tuple[str, ...] = ()
    linked_facets: Tuple[str, ...] = ()


@dataclass
class FacetCatalogBundle:
    apps: Dict[str, AppCatalogEntry]
    facets: Dict[str, FacetCatalogEntry]
    facet_lookup: Dict[str, str]
    app_lookup: Dict[str, str]
    capability_lookup: Dict[str, str]

    def resolve_facet(self, value: object) -> str:
        normalized = normalize_label(value)
        if not normalized:
            return ""
        return self.facet_lookup.get(normalized, normalized)

    def resolve_app(self, value: object) -> str:
        normalized = normalize_label(value)
        if not normalized:
            return ""
        return self.app_lookup.get(normalized, normalized)


@dataclass(frozen=True)
class FacetEvent:
    event_id: str
    user: str
    task: str
    environment: str
    facet: str
    app: str = ""
    capabilities: Tuple[str, ...] = ()
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventDataset:
    events: List[FacetEvent]
    schema: SchemaTables
    facet_catalog: Optional[FacetCatalogBundle] = None

    @property
    def facet_count(self) -> int:
        return len(self.schema.facets)


_FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "event_id": ("event_id", "id", "row_id"),
    "user": ("user", "user_id", "participant_id"),
    "task": ("task", "task_id"),
    "environment": ("environment", "environment_id", "env"),
    "facet": ("facet", "facet_id", "facet_name"),
    "app": ("app", "app_id", "app_name"),
    "capability": ("capability", "capability_id"),
    "capabilities": ("capabilities", "capability_ids"),
    "timestamp": ("timestamp", "time", "ts"),
}


def load_facet_catalog(path: str | Path) -> FacetCatalogBundle:
    return catalog_from_payload(json.loads(Path(path).read_text(encoding="utf-8")))


def catalog_from_payload(payload: Any) -> FacetCatalogBundle:
    apps_payload = payload.get("apps", []) if isinstance(payload, dict) else payload

    apps: Dict[str, AppCatalogEntry] = {}
    facets: Dict[str, FacetCatalogEntry] = {}
    facet_lookup: Dict[str, str] = {}
    app_lookup: Dict[str, str] = {}
    capability_lookup: Dict[str, str] = {}

    for app_payload in apps_payload or []:
        app_id = normalize_label(app_payload.get("app_id") or app_payload.get("app_name"))
        if not app_id:
            continue
        app_label = clean_display_label(app_payload.get("app_name") or app_payload.get("app_id") or app_id)
        category = clean_display_label(app_payload.get("app_domain"))
        app_caps = tuple(
            dedupe_preserve(capability_name(item) for item in app_payload.get("capabilities", []) or [])
        )
        apps[app_id] = AppCatalogEntry(
            app_id=app_id,
            app_label=app_label,
            category=category,
            capabilities=app_caps,
        )
        app_lookup[app_id] = app_id
        app_lookup[normalize_label(app_label)] = app_id

        for facet_payload in app_payload.get("facets", []) or []:
            facet_id = normalize_label(facet_payload.get("facet_id") or facet_payload.get("name"))
            if not facet_id:
                continue
            facet_label = clean_display_label(facet_payload.get("name") or facet_payload.get("facet_id") or facet_id)
            facet_description = clean_display_label(facet_payload.get("description"))
            facet_caps = tuple(
                dedupe_preserve(capability_name(item) for item in facet_payload.get("capabilities", []) or [])
            )
            facet_links = tuple(
                dedupe_preserve(normalize_label(item) for item in facet_payload.get("linked_facets", []) or [])
            )
            facets[facet_id] = FacetCatalogEntry(
                facet_id=facet_id,
                facet_label=facet_label,
                facet_description=facet_description,
                app_id=app_id,
                app_label=app_label,
                app_category=category,
                capabilities=facet_caps,
                linked_facets=facet_links,
            )
            facet_lookup[facet_id] = facet_id
            facet_lookup[normalize_label(facet_label)] = facet_id
            for cap in facet_caps:
                capability_lookup[normalize_label(cap)] = cap

    return FacetCatalogBundle(
        apps=apps,
        facets=facets,
        facet_lookup=facet_lookup,
        app_lookup=app_lookup,
        capability_lookup=capability_lookup,
    )


def _read_rows_from_path(path: str | Path) -> List[Dict[str, Any]]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with source.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]
    if suffix in {".jsonl", ".ndjson"}:
        rows: List[Dict[str, Any]] = []
        with source.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                rows.append(dict(json.loads(raw)))
        return rows
    if suffix == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [dict(row) for row in payload]
        if isinstance(payload, dict):
            for key in ("rows", "events", "data"):
                if isinstance(payload.get(key), list):
                    return [dict(row) for row in payload[key]]
        raise ValueError(f"Unsupported JSON event payload shape: {source}")
    raise ValueError(f"Unsupported event file type: {source}")


def _normalize_row_keys(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {normalize_column_name(key): value for key, value in row.items()}


def _pick_value(row: Mapping[str, Any], logical_name: str) -> Any:
    for alias in _FIELD_ALIASES[logical_name]:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return ""


def _canonical_capabilities(
    row: Mapping[str, Any],
    *,
    facet_catalog: Optional[FacetCatalogBundle],
    facet_key: str,
) -> Tuple[str, ...]:
    raw_values = split_multi_value_field(_pick_value(row, "capabilities"))
    if not raw_values:
        raw_values = split_multi_value_field(_pick_value(row, "capability"))
    if not raw_values and facet_catalog and facet_key in facet_catalog.facets:
        return tuple(facet_catalog.facets[facet_key].capabilities)

    out: List[str] = []
    seen = set()
    for raw in raw_values:
        cap = capability_name(raw)
        if facet_catalog:
            cap = facet_catalog.capability_lookup.get(normalize_label(cap), cap)
        if not cap or cap in seen:
            continue
        seen.add(cap)
        out.append(cap)
    return tuple(out)


def build_event_dataset(
    rows: Sequence[Mapping[str, Any]],
    *,
    facet_catalog: Optional[FacetCatalogBundle] = None,
) -> EventDataset:
    registries = {
        entity_type: EntityRegistry(entity_type)
        for entity_type in ("user", "task", "environment", "app", "facet", "capability")
    }
    relation_counts = build_empty_relation_counts()
    relation_adjacency = build_empty_relation_adjacency()
    events: List[FacetEvent] = []

    if facet_catalog is not None:
        for app in facet_catalog.apps.values():
            registries["app"].upsert(
                app.app_id,
                label=app.app_label,
                properties={"category": app.category},
            )
            for capability in app.capabilities:
                registries["capability"].upsert(capability, label=capability)
                add_relation(
                    relation_counts,
                    relation_adjacency,
                    "app_implements_capability",
                    app.app_id,
                    capability,
                )
        for facet in facet_catalog.facets.values():
            registries["facet"].upsert(
                facet.facet_id,
                label=facet.facet_label,
                properties={
                    "facet_description": facet.facet_description,
                    "app_id": facet.app_id,
                    "app_label": facet.app_label,
                    "category": facet.app_category,
                },
            )
            add_relation(
                relation_counts,
                relation_adjacency,
                "app_offers_facet",
                facet.app_id,
                facet.facet_id,
            )
            for capability in facet.capabilities:
                registries["capability"].upsert(capability, label=capability)
                add_relation(
                    relation_counts,
                    relation_adjacency,
                    "facet_composed_of_capability",
                    facet.facet_id,
                    capability,
                )
                add_relation(
                    relation_counts,
                    relation_adjacency,
                    "app_implements_capability",
                    facet.app_id,
                    capability,
                )
            for linked_facet in facet.linked_facets:
                add_relation(
                    relation_counts,
                    relation_adjacency,
                    "facet_links_to_facet",
                    facet.facet_id,
                    linked_facet,
                )

    for index, raw_row in enumerate(rows):
        row = _normalize_row_keys(raw_row)
        facet_key = normalize_label(_pick_value(row, "facet"))
        if facet_catalog is not None:
            facet_key = facet_catalog.resolve_facet(facet_key)
        if not facet_key:
            continue

        user = normalize_label(_pick_value(row, "user"))
        task = normalize_label(_pick_value(row, "task"))
        environment = normalize_label(_pick_value(row, "environment"))
        app = normalize_label(_pick_value(row, "app"))
        if facet_catalog is not None:
            app = facet_catalog.resolve_app(app)
            if not app and facet_key in facet_catalog.facets:
                app = facet_catalog.facets[facet_key].app_id

        capabilities = _canonical_capabilities(row, facet_catalog=facet_catalog, facet_key=facet_key)
        timestamp = clean_display_label(_pick_value(row, "timestamp"))
        event_id = clean_display_label(_pick_value(row, "event_id")) or f"event_{index:06d}"

        facet_label = facet_key
        facet_properties: Dict[str, Any] = {}
        if facet_catalog is not None and facet_key in facet_catalog.facets:
            facet_entry = facet_catalog.facets[facet_key]
            facet_label = facet_entry.facet_label
            facet_properties = {
                "facet_description": facet_entry.facet_description,
                "app_id": facet_entry.app_id,
                "app_label": facet_entry.app_label,
                "category": facet_entry.app_category,
            }
        registries["facet"].upsert(facet_key, label=facet_label, properties=facet_properties)
        if user:
            registries["user"].upsert(user, label=_pick_value(row, "user") or user)
        if task:
            registries["task"].upsert(task, label=_pick_value(row, "task") or task)
        if environment:
            registries["environment"].upsert(
                environment,
                label=_pick_value(row, "environment") or environment,
            )
        if app:
            app_label = app
            app_properties: Dict[str, Any] = {}
            if facet_catalog is not None and app in facet_catalog.apps:
                app_entry = facet_catalog.apps[app]
                app_label = app_entry.app_label
                app_properties = {"category": app_entry.category}
            registries["app"].upsert(app, label=app_label, properties=app_properties)

        for capability in capabilities:
            registries["capability"].upsert(capability, label=capability)

        reserved = {alias for aliases in _FIELD_ALIASES.values() for alias in aliases}
        metadata = {
            key: value
            for key, value in row.items()
            if key not in reserved and value not in (None, "")
        }
        event = FacetEvent(
            event_id=event_id,
            user=user,
            task=task,
            environment=environment,
            facet=facet_key,
            app=app,
            capabilities=capabilities,
            timestamp=timestamp,
            metadata=metadata,
        )
        events.append(event)

        if user and task:
            add_relation(relation_counts, relation_adjacency, "user_performs_task", user, task)
        if user and environment:
            add_relation(
                relation_counts,
                relation_adjacency,
                "user_is_in_environment",
                user,
                environment,
            )
        if user:
            add_relation(relation_counts, relation_adjacency, "user_uses_facet", user, facet_key)
        if task and environment:
            add_relation(
                relation_counts,
                relation_adjacency,
                "task_occurs_in_environment",
                task,
                environment,
            )
        if task:
            add_relation(relation_counts, relation_adjacency, "facet_supports_task", facet_key, task)
        if environment:
            add_relation(
                relation_counts,
                relation_adjacency,
                "environment_influences_facet",
                environment,
                facet_key,
            )
        if app:
            add_relation(relation_counts, relation_adjacency, "app_offers_facet", app, facet_key)
            for capability in capabilities:
                add_relation(
                    relation_counts,
                    relation_adjacency,
                    "app_implements_capability",
                    app,
                    capability,
                )
        for capability in capabilities:
            add_relation(
                relation_counts,
                relation_adjacency,
                "facet_composed_of_capability",
                facet_key,
                capability,
            )

    schema = registries_to_schema(registries, relation_counts, relation_adjacency)
    return EventDataset(events=events, schema=schema, facet_catalog=facet_catalog)


def load_event_dataset(
    events_path: str | Path,
    *,
    facet_catalog_path: Optional[str | Path] = None,
) -> EventDataset:
    facet_catalog = load_facet_catalog(facet_catalog_path) if facet_catalog_path else None
    rows = _read_rows_from_path(events_path)
    return build_event_dataset(rows, facet_catalog=facet_catalog)
