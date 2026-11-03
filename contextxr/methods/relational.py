"""Relational retrieval (paper §4.2.2, Fig. 3).

Builds the typed entity–relation schema (users, tasks, environments, apps, facets,
capabilities) from the training events and scores each facet f for a query
q = (u, t, e) as a weighted mean of context-conditioned statistics:

    exact     P(f|t), P(f|e), P(f|u)                   weight 1.0 each
    pairwise  P(f|t,e), P(f|t,u), P(f|e,u)             weight 0.6 each
    triple    P(f|t,e,u)                               weight 0.25
    soft      similarity-weighted P(f|t'), P(f|e')      weight 0.7 each
              over the 3 nearest training task / environment labels (cosine ≥ 0.15,
              all-MiniLM-L6-v2), scaled by 0.2 when the label itself has ≥ 3 training events
    history   max over placed facets p of max(0.35·Jaccard(caps(f), caps(p)), 0.2·same_app)
              weight 2.0, next facet suggestion only

All conditionals use add-0.5 smoothing over the catalog. Scores are rounded to 6
decimals; ties are broken by global popularity, then facet id. Placed facets are
excluded from next-facet suggestions. Requires the [embed] extra.
"""

from __future__ import annotations

from typing import List, Optional

from contextxr.data.schema import Context, Dataset, FacetCatalog, FacetId
from contextxr.methods._ranker.adapter import RankerBackend
from contextxr.methods._ranker.model import ScoreWeights
from contextxr.methods.base import Suggester


class RelationalRetrieval(Suggester):
    """`use_history=True` adds the placed-facet (prior schema) term used for next facet suggestion.

    With an empty history the two settings rank identically, so one instance serves both tasks.
    """

    name = "relational"

    def __init__(self, *, use_history: bool = True, weights: Optional[ScoreWeights] = None) -> None:
        variant = "exact_embeddings_prior_schema" if use_history else "exact_embeddings"
        self.use_history = use_history
        self._backend = RankerBackend(variant=variant, mode="TEU", weights=weights)

    def fit(self, train: Dataset) -> None:
        self._backend.fit(train)

    def suggest(self, context: Context, catalog: FacetCatalog, history: Optional[List[FacetId]] = None,
                k: int = 10) -> List[FacetId]:
        return self._backend.rank(context, catalog, history, k)
