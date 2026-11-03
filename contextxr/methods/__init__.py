"""Suggestion methods. Heavy optional dependencies are imported lazily."""

from contextxr.methods.base import Suggester, SuggestionUnavailable

__all__ = ["Suggester", "SuggestionUnavailable", "GlobalPopularity", "RelationalRetrieval", "LLMSuggester"]


def __getattr__(name):
    if name == "GlobalPopularity":
        from contextxr.methods.popularity import GlobalPopularity

        return GlobalPopularity
    if name == "RelationalRetrieval":
        from contextxr.methods.relational import RelationalRetrieval

        return RelationalRetrieval
    if name == "LLMSuggester":
        from contextxr.methods.llm import LLMSuggester

        return LLMSuggester
    raise AttributeError(name)
