"""The `Suggester` interface every method implements (paper §3.3)."""

from __future__ import annotations

from typing import List, Optional

from contextxr.data.schema import Context, Dataset, FacetCatalog, FacetId


class Suggester:
    """A context-aware facet suggestion method.

    `fit` is called once per cross-validation fold with the training scenarios only
    (methods without training can ignore it). `suggest` returns up to `k` facet ids,
    best first. `history` is None for initial facet suggestion and the facets already
    placed (in placement order) for next facet suggestion.
    """

    name: str = "suggester"

    def fit(self, train: Dataset) -> None:  # noqa: B027 - optional hook
        """Optional: learn from training scenarios."""

    def suggest(
        self,
        context: Context,
        catalog: FacetCatalog,
        history: Optional[List[FacetId]] = None,
        k: int = 10,
    ) -> List[FacetId]:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


class SuggestionUnavailable(Exception):
    """Raised by `suggest` when a method cannot produce suggestions for a context.

    Example: few-shot LLM prompting when no example matches the transfer condition, or
    a failed LLM response. The runner records the reason and treats the scenario (or
    step) according to the task's protocol.
    """

    def __init__(self, reason: str, *, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail
