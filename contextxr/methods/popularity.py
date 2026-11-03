"""Global popularity baseline (paper §4.2.2).

Ranks facets by how often they were placed in the training scenarios, ignoring the
query context: P(f) = (n_f + α) / (N + α|F|) with α = 0.5. Ties are broken by facet
id. For next facet suggestion, already-placed facets are excluded.
"""

from __future__ import annotations

from typing import List, Optional

from contextxr.data.schema import Context, Dataset, FacetCatalog, FacetId
from contextxr.methods._ranker.adapter import RankerBackend
from contextxr.methods._ranker.embeddings import EmbeddingConfig
from contextxr.methods._ranker.model import RankerConfig
from contextxr.methods.base import Suggester


class GlobalPopularity(Suggester):
    name = "popularity"

    def __init__(self) -> None:
        # Popularity uses no soft transfer, so the embedding model is never loaded.
        config = RankerConfig(embedding=EmbeddingConfig(enabled=False))
        self._backend = RankerBackend(variant="global_popularity", mode="TEU", config=config)

    def fit(self, train: Dataset) -> None:
        self._backend.fit(train)

    def suggest(self, context: Context, catalog: FacetCatalog, history: Optional[List[FacetId]] = None,
                k: int = 10) -> List[FacetId]:
        return self._backend.rank(context, catalog, history, k)
