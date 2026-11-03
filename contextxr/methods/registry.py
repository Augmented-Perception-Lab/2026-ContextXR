"""Build the paper's methods from configs/methods/*.yaml.

    method, protocol = build_method("relational", task="initial", dataset=ds)
    method, protocol = build_method("few_shot_llm[user+env]", task="next", dataset=ds)

`protocol` holds task options the paper used with that method (passed to the task).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Dict, List, Tuple

from contextxr.data.schema import Dataset
from contextxr.methods.base import Suggester


def methods_dir() -> Path:
    from contextxr.paths import configs_dir

    return configs_dir() / "methods"


def _load(path: Path) -> Dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def method_configs() -> Dict[str, Dict]:
    """Method name -> config, with one entry per few-shot transfer condition."""
    out: Dict[str, Dict] = {}
    for path in sorted(methods_dir().glob("*.yaml")):
        cfg = _load(path)
        if cfg.get("conditions"):
            for cond in cfg["conditions"]:
                c = dict(cfg)
                c["params"] = {**cfg.get("params", {}), "condition": cond}
                out[f"{cfg['name']}[{cond}]"] = c
        else:
            out[cfg["name"]] = cfg
    return out


def paper_methods() -> List[str]:
    """Method names in the order of the paper's tables."""
    return ["popularity", "relational", "zero_shot_llm"] + [
        f"few_shot_llm[{c}]" for c in ["user", "task", "environment", "user+task", "user+env", "task+env"]
    ]


def build_method(name: str, *, task: str, dataset: Dataset, cache=None) -> Tuple[Suggester, Dict]:
    configs = method_configs()
    if name not in configs:
        raise KeyError(f"Unknown method '{name}'. Available: {sorted(configs)}")
    cfg = configs[name]
    module, _, cls_name = cfg["class"].rpartition(".")
    cls = getattr(importlib.import_module(module), cls_name)
    task_cfg = (cfg.get("tasks") or {}).get(task, {}) or {}
    params = {**cfg.get("params", {}), **(task_cfg.get("params") or {})}
    if cls_name == "LLMSuggester":
        params = {"dataset": dataset, **params}
        if cache is not None:
            params["cache"] = cache
    return cls(**params), dict(task_cfg.get("protocol") or {})
