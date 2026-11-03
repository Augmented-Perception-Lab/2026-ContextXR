"""ContextXR: a benchmarking framework for context-aware XR interfaces (Cho et al., UIST '26)."""

__version__ = "1.0.0"
BENCHMARK_VERSION = "1.0.0"

__all__ = ["__version__", "BENCHMARK_VERSION", "evaluate", "load_minexrpp", "Results"]


def __getattr__(name):
    if name in ("evaluate", "Results"):
        from contextxr import runner

        return getattr(runner, name)
    if name == "load_minexrpp":
        from contextxr.data.loader import load_minexrpp

        return load_minexrpp
    raise AttributeError(name)
