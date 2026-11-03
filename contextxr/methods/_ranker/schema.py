"""Schema-constrained entity and relation tables.

Ported from the paper's research code (context_facet_ranker); logic unchanged.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

from .normalization import clean_display_label, normalize_label


ENTITY_TYPES: Tuple[str, ...] = (
    "user",
    "task",
    "environment",
    "app",
    "facet",
    "capability",
)

RELATION_TYPES: Tuple[str, ...] = (
    "user_performs_task",
    "user_is_in_environment",
    "user_uses_facet",
    "task_occurs_in_environment",
    "facet_supports_task",
    "environment_influences_facet",
    "app_offers_facet",
    "app_implements_capability",
    "facet_composed_of_capability",
    "facet_links_to_facet",
)


@dataclass
class EntityRecord:
    entity_id: int
    key: str
    label: str
    entity_type: str
    properties: Dict[str, str] = field(default_factory=dict)


class EntityRegistry:
    def __init__(self, entity_type: str) -> None:
        self.entity_type = entity_type
        self._next_id = 1
        self._records: Dict[str, EntityRecord] = {}

    def upsert(
        self,
        key: object,
        *,
        label: Optional[object] = None,
        properties: Optional[Mapping[str, object]] = None,
    ) -> Optional[EntityRecord]:
        normalized_key = normalize_label(key)
        if not normalized_key:
            return None

        display_label = clean_display_label(label if label is not None else key) or normalized_key
        existing = self._records.get(normalized_key)
        if existing is None:
            merged_props = {
                str(prop_key): clean_display_label(prop_value)
                for prop_key, prop_value in (properties or {}).items()
                if clean_display_label(prop_value)
            }
            record = EntityRecord(
                entity_id=self._next_id,
                key=normalized_key,
                label=display_label,
                entity_type=self.entity_type,
                properties=merged_props,
            )
            self._records[normalized_key] = record
            self._next_id += 1
            return record

        if display_label and existing.label == existing.key and display_label != existing.key:
            existing.label = display_label
        if properties:
            for prop_key, prop_value in properties.items():
                cleaned = clean_display_label(prop_value)
                if cleaned:
                    existing.properties[str(prop_key)] = cleaned
        return existing

    def get(self, key: object) -> Optional[EntityRecord]:
        return self._records.get(normalize_label(key))

    def items(self) -> Iterable[Tuple[str, EntityRecord]]:
        return self._records.items()

    def values(self) -> Iterable[EntityRecord]:
        return self._records.values()

    def as_dict(self) -> Dict[str, EntityRecord]:
        return self._records

    def __contains__(self, key: object) -> bool:
        return normalize_label(key) in self._records

    def __len__(self) -> int:
        return len(self._records)


@dataclass
class SchemaTables:
    users: Dict[str, EntityRecord]
    tasks: Dict[str, EntityRecord]
    environments: Dict[str, EntityRecord]
    apps: Dict[str, EntityRecord]
    facets: Dict[str, EntityRecord]
    capabilities: Dict[str, EntityRecord]
    relation_counts: Dict[str, Counter]
    relation_adjacency: Dict[str, Dict[str, Set[str]]]


def build_empty_relation_counts() -> Dict[str, Counter]:
    return {name: Counter() for name in RELATION_TYPES}


def build_empty_relation_adjacency() -> Dict[str, Dict[str, Set[str]]]:
    return {name: defaultdict(set) for name in RELATION_TYPES}


def add_relation(
    relation_counts: MutableMapping[str, Counter],
    relation_adjacency: MutableMapping[str, Dict[str, Set[str]]],
    relation_name: str,
    source_key: object,
    target_key: object,
    weight: float = 1.0,
) -> None:
    source = normalize_label(source_key)
    target = normalize_label(target_key)
    if not source or not target:
        return
    relation_counts[relation_name][(source, target)] += float(weight)
    relation_adjacency[relation_name].setdefault(source, set()).add(target)


def registries_to_schema(
    registries: Mapping[str, EntityRegistry],
    relation_counts: Mapping[str, Counter],
    relation_adjacency: Mapping[str, Mapping[str, Set[str]]],
) -> SchemaTables:
    return SchemaTables(
        users=dict(registries["user"].as_dict()),
        tasks=dict(registries["task"].as_dict()),
        environments=dict(registries["environment"].as_dict()),
        apps=dict(registries["app"].as_dict()),
        facets=dict(registries["facet"].as_dict()),
        capabilities=dict(registries["capability"].as_dict()),
        relation_counts={name: Counter(counter) for name, counter in relation_counts.items()},
        relation_adjacency={
            name: {source: set(targets) for source, targets in adjacency.items()}
            for name, adjacency in relation_adjacency.items()
        },
    )
