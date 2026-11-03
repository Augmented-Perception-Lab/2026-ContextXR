"""Core data types for ContextXR (paper §3.1–3.3).

An app `a` offers a set of functional facets F_a. Each facet groups capabilities
(atomic actions). Navigational capabilities follow the `open_<facet_name>`
convention and induce the directed facet graph G_a = (F_a, E_a). A context is the
triple (user, task, environment); a scenario pairs one context with its target
facet set Y_q.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

FacetId = str
AppId = str

ENTRY_FACET_SUFFIX = "open_section"
NAVIGATION_PREFIX = "open_"
RELEVANCE_TIERS: Tuple[str, ...] = ("primary", "peripheral", "ambient")
RELEVANCE_RANK: Dict[str, int] = {"primary": 3, "peripheral": 2, "ambient": 1}
_TIER_ALIASES: Dict[str, str] = {
    "primary": "primary",
    "peripheral": "peripheral",
    "secondary": "peripheral",
    "supporting": "peripheral",
    "support": "peripheral",
    "ambient": "ambient",
    "background": "ambient",
}


def normalize_tier(raw: object) -> str:
    """Canonical relevance tier; empty values default to "peripheral" (reference behaviour)."""
    value = str(raw or "").strip().lower()
    return _TIER_ALIASES.get(value, value or "peripheral")


@dataclass(frozen=True)
class Capability:
    """An atomic action of an app, e.g. `spotify.play_track`."""

    app_id: AppId
    name: str

    @property
    def capability_id(self) -> str:
        return f"{self.app_id}.{self.name}"

    @property
    def is_navigational(self) -> bool:
        return self.name.startswith(NAVIGATION_PREFIX)


@dataclass(frozen=True)
class Facet:
    """A semantically coherent group of capabilities serving one user intent."""

    facet_id: FacetId
    app_id: AppId
    name: str
    description: str
    capabilities: Tuple[str, ...]
    legacy_ids: Tuple[str, ...] = ()

    @property
    def is_entry(self) -> bool:
        return self.facet_id == f"{self.app_id}.{ENTRY_FACET_SUFFIX}"


@dataclass(frozen=True)
class App:
    app_id: AppId
    name: str
    domain: str
    entry_facet_id: FacetId
    capabilities: Tuple[str, ...]
    facet_ids: Tuple[FacetId, ...]


@dataclass(frozen=True)
class Edge:
    """Directed facet-graph edge induced by navigational capability `capability`."""

    source: FacetId
    target: FacetId
    capability: str
    resolution: str = "exact"


class FacetGraph:
    """Facet graph of one app.

    Manual navigation (c_facet_nav) uses directed BFS from the app's entry facet;
    same-app adjustment (c_adjust) uses BFS on the graph with edges symmetrized.
    Neighbours are visited in sorted order, matching the reference implementation.
    """

    def __init__(self, app_id: AppId, entry_facet_id: FacetId, facet_ids: Iterable[FacetId], edges: Iterable[Edge]):
        self.app_id = app_id
        self.entry_facet_id = entry_facet_id
        self.nodes: Tuple[FacetId, ...] = tuple(facet_ids)
        self.edges: Tuple[Edge, ...] = tuple(edges)
        adjacency: Dict[FacetId, set] = {node: set() for node in self.nodes}
        undirected: Dict[FacetId, set] = {node: set() for node in self.nodes}
        for edge in self.edges:
            adjacency.setdefault(edge.source, set()).add(edge.target)
            undirected.setdefault(edge.source, set()).add(edge.target)
            undirected.setdefault(edge.target, set()).add(edge.source)
        self._adjacency = {node: sorted(nbrs) for node, nbrs in adjacency.items()}
        self._undirected = {node: sorted(nbrs) for node, nbrs in undirected.items()}
        self._entry_paths = self._bfs_tree(self.entry_facet_id) if self.entry_facet_id in self._adjacency else {}

    def __contains__(self, facet_id: object) -> bool:
        return facet_id in self._adjacency

    def successors(self, facet_id: FacetId) -> List[FacetId]:
        return list(self._adjacency.get(facet_id, []))

    def neighbors(self, facet_id: FacetId) -> List[FacetId]:
        """Neighbours ignoring edge direction."""
        return list(self._undirected.get(facet_id, []))

    def _bfs_tree(self, source: FacetId) -> Dict[FacetId, Optional[FacetId]]:
        parents: Dict[FacetId, Optional[FacetId]] = {source: None}
        queue = deque([source])
        while queue:
            node = queue.popleft()
            for nbr in self._adjacency.get(node, []):
                if nbr not in parents:
                    parents[nbr] = node
                    queue.append(nbr)
        return parents

    def path_from_entry(self, facet_id: FacetId) -> Optional[List[FacetId]]:
        """Directed shortest path entry → facet, including both endpoints; None if unreachable."""
        if facet_id not in self._entry_paths:
            return None
        path = [facet_id]
        while self._entry_paths[path[-1]] is not None:
            path.append(self._entry_paths[path[-1]])  # type: ignore[arg-type]
        return path[::-1]

    def shortest_path(self, source: FacetId, target: FacetId, *, directed: bool = True) -> Optional[List[FacetId]]:
        """Shortest path between two facets, including both endpoints; None if unreachable."""
        if source not in self._adjacency or target not in self._adjacency:
            return None
        if source == target:
            return [source]
        adjacency = self._adjacency if directed else self._undirected
        parents: Dict[FacetId, Optional[FacetId]] = {source: None}
        queue = deque([source])
        while queue:
            node = queue.popleft()
            for nbr in adjacency.get(node, []):
                if nbr in parents:
                    continue
                parents[nbr] = node
                if nbr == target:
                    path = [target]
                    while parents[path[-1]] is not None:
                        path.append(parents[path[-1]])  # type: ignore[arg-type]
                    return path[::-1]
                queue.append(nbr)
        return None

    def hops(self, source: FacetId, target: FacetId, *, directed: bool = False) -> Optional[int]:
        path = self.shortest_path(source, target, directed=directed)
        return None if path is None else len(path) - 1


@dataclass(frozen=True)
class Context:
    """Usage context q = (u, t, e)."""

    user: str
    task: str
    environment: str


@dataclass(frozen=True)
class Widget:
    """One element a participant placed in their envisioned XR layout (a MineXR widget).

    `facet_id` is the single facet the widget was resolved to (used as a training
    event by count-based methods); `capabilities` maps exposed capability ids
    (`app.capability`) to relevance tiers.
    """

    scenario_id: str
    widget_id: str
    app_id: str
    facet_id: str
    capabilities: Tuple[Tuple[str, str], ...]
    widget_desc: str = ""
    screen_desc: str = ""

    @property
    def capability_tiers(self) -> Dict[str, str]:
        return dict(self.capabilities)


@dataclass(frozen=True)
class Scenario:
    """A context together with its target facet set Y_q (facet id → relevance tier)."""

    scenario_id: str
    context: Context
    targets: Tuple[Tuple[FacetId, str], ...]
    widgets: Tuple[Widget, ...] = field(default=(), repr=False)

    @property
    def target_ids(self) -> List[FacetId]:
        return [facet_id for facet_id, _ in self.targets]

    @property
    def target_tiers(self) -> Dict[FacetId, str]:
        return dict(self.targets)


class FacetCatalog:
    """All apps, facets, capabilities and facet graphs of a benchmark (the facet DB)."""

    def __init__(self, apps: Sequence[App], facets: Sequence[Facet], edges: Sequence[Edge], *, name: str = "", version: str = ""):
        self.name = name
        self.version = version
        self.apps: Dict[AppId, App] = {app.app_id: app for app in apps}
        self.facets: Dict[FacetId, Facet] = {facet.facet_id: facet for facet in facets}
        self.edges: Tuple[Edge, ...] = tuple(edges)
        edges_by_app: Dict[AppId, List[Edge]] = {app_id: [] for app_id in self.apps}
        for edge in self.edges:
            edges_by_app[self.facets[edge.source].app_id].append(edge)
        self.graphs: Dict[AppId, FacetGraph] = {
            app.app_id: FacetGraph(app.app_id, app.entry_facet_id, app.facet_ids, edges_by_app[app.app_id])
            for app in apps
        }

    def __len__(self) -> int:
        return len(self.facets)

    def __iter__(self) -> Iterator[Facet]:
        return iter(self.facets.values())

    def __contains__(self, facet_id: object) -> bool:
        return facet_id in self.facets

    def facet(self, facet_id: FacetId) -> Facet:
        return self.facets[facet_id]

    def canonical_id(self, facet_id: str) -> FacetId:
        """Map a pre-1.0 facet id (see `Facet.legacy_ids`) to its current id; other ids pass through."""
        if not hasattr(self, "_legacy_map"):
            self._legacy_map = {old: f.facet_id for f in self.facets.values() for old in f.legacy_ids}
        return self._legacy_map.get(facet_id, facet_id)

    def app_of(self, facet_id: FacetId) -> AppId:
        return self.facets[facet_id].app_id

    def graph(self, app_id: AppId) -> FacetGraph:
        return self.graphs[app_id]

    def graph_of(self, facet_id: FacetId) -> FacetGraph:
        return self.graphs[self.app_of(facet_id)]

    def capabilities(self) -> List[Capability]:
        return [Capability(app.app_id, name) for app in self.apps.values() for name in app.capabilities]

    def capability_names(self) -> List[str]:
        """Distinct capability names across apps (the paper's capability count)."""
        return sorted({name for app in self.apps.values() for name in app.capabilities})

    def facets_with_capability(self, capability_id: str) -> List[FacetId]:
        app_id, _, name = capability_id.partition(".")
        app = self.apps.get(app_id)
        if app is None:
            return []
        return [fid for fid in app.facet_ids if name in self.facets[fid].capabilities]


@dataclass
class Dataset:
    """A benchmark dataset: a facet catalog plus scenarios."""

    catalog: FacetCatalog
    scenarios: Dict[str, Scenario]
    name: str = ""
    version: str = ""

    def __len__(self) -> int:
        return len(self.scenarios)

    def __iter__(self) -> Iterator[Scenario]:
        return iter(self.scenarios.values())

    def subset(self, scenario_ids: Iterable[str]) -> "Dataset":
        keep = [sid for sid in scenario_ids]
        return Dataset(self.catalog, {sid: self.scenarios[sid] for sid in keep}, self.name, self.version)

    def with_contexts(self, contexts: Mapping[str, Context]) -> "Dataset":
        """Copy with some scenarios' contexts replaced (e.g. by labels from a sensing module)."""
        scenarios = {
            sid: Scenario(sid, contexts.get(sid, s.context), s.targets, s.widgets) for sid, s in self.scenarios.items()
        }
        return Dataset(self.catalog, scenarios, self.name, self.version)

    def widgets(self) -> List[Widget]:
        return [w for s in self.scenarios.values() for w in s.widgets]

    def participants(self) -> List[str]:
        return sorted({s.context.user for s in self.scenarios.values()})

    def contexts_for(self, user: str) -> List[Context]:
        return [s.context for s in self.scenarios.values() if s.context.user == user]

    def placed_facets(self) -> List[FacetId]:
        """Distinct facets that appear in at least one scenario's target set."""
        return sorted({fid for s in self.scenarios.values() for fid, _ in s.targets})
