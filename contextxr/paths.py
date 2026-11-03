"""Where the benchmark's data, configs and LLM cache live.

Resolution order for each resource directory:

1. `$CONTEXTXR_HOME/<name>` if CONTEXTXR_HOME is set (a directory laid out like the repo);
2. the source checkout this package was imported from (editable / development installs);
3. the copy bundled in the wheel (package `contextxr_assets`).

The LLM cache is read from the first location that exists. Responses recorded in live mode
are written to the checkout's `cache/llm/`, or to `$CONTEXTXR_LLM_CACHE` /
`~/.cache/contextxr/llm` when the package is installed (the bundled copy is read-only).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import List, Optional

_PACKAGE_ROOT = Path(__file__).resolve().parent
_CHECKOUT = _PACKAGE_ROOT.parent
_RESOURCES = ("data", "configs", "cache")


def checkout_root() -> Optional[Path]:
    """Repository root if running from a source checkout, else None."""
    if (_CHECKOUT / "pyproject.toml").exists() and (_CHECKOUT / "configs").is_dir():
        return _CHECKOUT
    return None


def resource_dir(name: str) -> Path:
    if name not in _RESOURCES:
        raise ValueError(f"Unknown resource '{name}'")
    home = os.environ.get("CONTEXTXR_HOME")
    if home:
        return Path(home) / name
    root = checkout_root()
    if root is not None:
        return root / name
    # Bundled copy: resource directories are namespace packages, so use their search location.
    spec = None
    try:
        spec = importlib.util.find_spec(f"contextxr_assets.{name}")
    except ModuleNotFoundError:
        pass
    if spec is None or not spec.submodule_search_locations:
        raise FileNotFoundError(f"ContextXR resources '{name}' not found. Set CONTEXTXR_HOME to a ContextXR checkout.")
    return Path(list(spec.submodule_search_locations)[0])


def configs_dir() -> Path:
    return resource_dir("configs")


def data_dir() -> Path:
    return resource_dir("data")


def llm_cache_read_dirs() -> List[Path]:
    """LLM cache directories to read from, most specific first."""
    dirs = []
    env = os.environ.get("CONTEXTXR_LLM_CACHE")
    if env:
        dirs.append(Path(env))
    dirs.append(llm_cache_write_dir())
    dirs.append(resource_dir("cache") / "llm")
    out: List[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def llm_cache_write_dir() -> Path:
    """Where live-mode responses are recorded."""
    env = os.environ.get("CONTEXTXR_LLM_CACHE")
    if env:
        return Path(env)
    if os.environ.get("CONTEXTXR_HOME") or checkout_root() is not None:
        return resource_dir("cache") / "llm"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "contextxr" / "llm"
