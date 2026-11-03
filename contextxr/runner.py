"""Run a method on a benchmark task and collect results.

    from contextxr import evaluate, load_minexrpp
    from contextxr.methods import RelationalRetrieval

    results = evaluate(RelationalRetrieval(), "initial")
    print(results.summary)
    results.to_jsonl("runs/relational_initial.jsonl")

The results file format is documented in docs/results_format.md.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Union

from contextxr import BENCHMARK_VERSION, __version__
from contextxr.data.loader import load_folds, load_minexrpp
from contextxr.data.schema import Dataset
from contextxr.methods.base import Suggester
from contextxr.metrics.cost_model import CostModel, DefaultCostModel
from contextxr.tasks.initial_suggestion import InitialFacetTask
from contextxr.tasks.next_suggestion import NextFacetTask

PathLike = Union[str, Path]
RESULTS_FORMAT = "contextxr.results"
RESULTS_FORMAT_VERSION = "1.0"

TASKS = {"initial": InitialFacetTask, "next": NextFacetTask}


@dataclass
class Results:
    """Aggregate summary plus one record per scenario (with per-step records for next facet)."""

    run: Dict
    records: List[Dict]
    summary: Dict = field(default_factory=dict)

    @property
    def method(self) -> str:
        return self.run["method"]["name"]

    @property
    def task(self) -> str:
        return self.run["protocol"]["task"]

    def to_jsonl(self, path: PathLike) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "run", **self.run}, ensure_ascii=False) + "\n")
            for record in self.records:
                handle.write(json.dumps({"type": "scenario", "benchmark_version": self.run["benchmark_version"], **record},
                                        ensure_ascii=False) + "\n")
            handle.write(json.dumps({"type": "summary", "benchmark_version": self.run["benchmark_version"], **self.summary},
                                    ensure_ascii=False) + "\n")
        return path

    @classmethod
    def from_jsonl(cls, path: PathLike) -> "Results":
        run: Dict = {}
        records: List[Dict] = []
        summary: Dict = {}
        with Path(path).open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                obj = json.loads(line)
                kind = obj.pop("type")
                if kind == "run":
                    run = obj
                elif kind == "scenario":
                    obj.pop("benchmark_version", None)
                    records.append(obj)
                elif kind == "summary":
                    obj.pop("benchmark_version", None)
                    summary = obj
        return cls(run, records, summary)

    def row(self) -> Dict:
        """One table row: method, n, manual and assisted cost, reduction, retrieval metrics."""
        s = self.summary
        return {
            "method": self.method,
            "n": s.get("n_evaluated"),
            "manual": s.get("manual_cost"),
            "cost": s.get("suggest_cost"),
            "reduction_%": s.get("cost_reduction_pct"),
            "recall@10": s.get("recall"),
            "f1@10": s.get("f1"),
            "hit@10": s.get("hit"),
        }


def _method_info(method: Suggester) -> Dict:
    info = {"name": getattr(method, "name", type(method).__name__), "class": f"{type(method).__module__}.{type(method).__qualname__}"}
    for attr in ("model", "temperature", "max_examples", "use_history"):
        if hasattr(method, attr):
            info[attr] = getattr(method, attr)
    if hasattr(method, "condition"):
        info["condition"] = getattr(method.condition, "key", method.condition)
    return info


def evaluate(
    method: Suggester,
    task: Union[str, InitialFacetTask, NextFacetTask] = "initial",
    dataset: Optional[Dataset] = None,
    *,
    cost_model: Optional[CostModel] = None,
    folds: Optional[Mapping[str, int]] = "paper",
    out: Optional[PathLike] = None,
    **task_options,
) -> Results:
    """Evaluate `method` on `task` ("initial", "next", or a task object).

    `folds="paper"` uses the exported folds in configs/splits/cv5_seed42.json for MineXR++;
    pass a scenario→fold mapping for other data, or None to fit once on the whole dataset.
    Extra keyword arguments configure the task (e.g. `unmatched="exclude"` for next facet).
    """
    dataset = dataset or load_minexrpp()
    if isinstance(task, str):
        if task not in TASKS:
            raise ValueError(f"Unknown task '{task}'. Choose from {sorted(TASKS)}")
        task = TASKS[task](**task_options)
    elif task_options:
        raise ValueError("Task options can only be given with a task name")
    if isinstance(folds, str) and folds == "paper":
        folds = load_folds()
        if set(folds) != set(dataset.scenarios):
            raise ValueError("The paper's folds only apply to MineXR++; pass folds=... or folds=None for other data")
        fold_source = "configs/splits/cv5_seed42.json"
    else:
        fold_source = "custom" if folds else "none"
    cost_model = (cost_model or DefaultCostModel()).bind(dataset)

    records = task.evaluate(method, dataset, cost_model, folds)
    summary = task.summarize(records)
    run = {
        "format": RESULTS_FORMAT,
        "format_version": RESULTS_FORMAT_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "package_version": __version__,
        "dataset": {"name": dataset.name, "version": dataset.version, "n_scenarios": len(dataset)},
        "method": _method_info(method),
        "protocol": {**task.protocol(), "folds": fold_source},
        "cost_model": cost_model.describe() if hasattr(cost_model, "describe") else {"name": type(cost_model).__name__},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
    }
    results = Results(run, records, summary)
    if out is not None:
        results.to_jsonl(out)
    return results


def results_table(results: Iterable[Results]) -> List[Dict]:
    return [r.row() for r in results]


def compare(methods: Iterable[Suggester], task="initial", dataset: Optional[Dataset] = None, **kwargs) -> List[Results]:
    """Evaluate several methods under identical conditions."""
    dataset = dataset or load_minexrpp()
    return [evaluate(m, task, dataset, **kwargs) for m in methods]


def format_table(results: Iterable[Results], *, sort_by: Optional[str] = None) -> str:
    """Markdown table of results (method, n, manual and assisted cost, reduction, retrieval).

    `sort_by`: None (input order), "reduction" (largest cost reduction first) or "cost".
    Methods evaluated on different scenario subsets are best compared by reduction.
    """
    rows = results_table(results)
    if sort_by:
        key = {"reduction": "reduction_%", "cost": "cost"}[sort_by]
        rows.sort(key=lambda r: (r[key] is None, r[key]))
    lines = ["| method | n | manual | cost | reduction | Recall@10 | F1@10 | Hit@10 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]

    def f(v, d):
        return "–" if v is None else f"{v:.{d}f}"

    for r in rows:
        lines.append(f"| {r['method']} | {r['n']} | {f(r['manual'], 2)} | {f(r['cost'], 2)} | "
                     f"{f(r['reduction_%'], 1)}% | {f(r['recall@10'], 3)} | {f(r['f1@10'], 3)} | {f(r['hit@10'], 3)} |")
    return "\n".join(lines)
