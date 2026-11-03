"""Reproduce the paper's Figure 4, Table 1 and Table 2 from the cache (no API key needed).

    python scripts/reproduce_paper.py            # or: contextxr reproduce
    python scripts/reproduce_paper.py --out runs/paper

Every number is compared with the camera-ready paper (costs ±0.01, retrieval metrics
±0.001, lifts ±0.01). One cell intentionally differs in benchmark 1.0.0; see
`V1_CHANGES`.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from contextxr import BENCHMARK_VERSION
from contextxr.data.loader import load_minexrpp
from contextxr.methods.registry import build_method, paper_methods
from contextxr.runner import evaluate
from contextxr.tasks.factor_analysis import ContextFactorAnalysis

COST_TOL = 0.01
METRIC_TOL = 0.001
LIFT_TOL = 0.01

# --- Camera-ready values -------------------------------------------------------------

FIG4_COUNTS = {"user": 47, "task": 14, "environment": 12, "mixed": 8, "none": 20}
FIG4_LIFTS = {  # facet -> (U, T, E); None = not shown in the paper
    "duolingo.complete_lesson": (18.99, 0.00, 0.66),
    "books.browse_library": (None, 12.91, None),
    "netflix.browse_content": (None, None, 3.94),
    "reminders.browse_task_lists": (12.66, 12.91, 1.31),
}

# method -> (cost, recall@10, f1@10, hit@10, n evaluated scenarios or None)
TABLE1_MANUAL = 21.20
TABLE1 = {
    "popularity": (19.85, 0.167, 0.132, 0.688, 109),
    "relational": (18.39, 0.259, 0.193, 0.798, 109),
    "zero_shot_llm": (17.66, 0.228, 0.168, 0.761, 109),
    "few_shot_llm[user]": (16.33, 0.338, 0.255, 0.830, 106),
    "few_shot_llm[task]": (18.41, 0.274, 0.217, 0.825, 40),
    "few_shot_llm[environment]": (17.07, 0.287, 0.206, 0.870, 108),
    "few_shot_llm[user+task]": (15.25, 0.464, 0.399, 1.000, 2),
    "few_shot_llm[user+env]": (15.53, 0.319, 0.229, 0.862, 94),
    "few_shot_llm[task+env]": (19.54, 0.222, 0.178, 0.702, 47),
}
TABLE2_MANUAL = 21.19
TABLE2 = {
    "popularity": (18.70, 0.168, 0.089, 0.466, 109),
    "relational": (15.70, 0.355, 0.162, 0.687, 109),
    "zero_shot_llm": (16.00, 0.205, 0.102, 0.488, 109),
    "few_shot_llm[user]": (14.61, 0.285, 0.147, 0.574, 109),
    "few_shot_llm[task]": (19.22, 0.079, 0.044, 0.188, 109),
    "few_shot_llm[environment]": (15.82, 0.209, 0.104, 0.492, 109),
    "few_shot_llm[user+task]": (20.98, 0.007, 0.004, 0.014, 109),
    "few_shot_llm[user+env]": (15.83, 0.257, 0.122, 0.494, 109),
    "few_shot_llm[task+env]": (19.30, 0.090, 0.046, 0.205, 109),
}

# Benchmark 1.0.0 differs from the paper in exactly one cell group. The paper's research
# code compared the ranker's lower-cased facet ids case-sensitively with the catalog id
# `instagram.browse_Explore`, so predicting that facet could never hit (3 scenarios of next
# facet relational retrieval). 1.0.0 renamed the facet to `instagram.browse_explore`,
# which removes the mismatch. With the old id and behaviour the port gives exactly the
# paper's 15.7018 / 0.3554 / 0.1620 / 0.6868.
V1_CHANGES = {
    ("next", "relational"): {
        "values": (15.6835, 0.3574, 0.1633, 0.6881, 109),
        "reason": "facet id instagram.browse_Explore renamed; paper run could not match it (case bug)",
    }
}


def _close(a: Optional[float], b: Optional[float], tol: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol + 1e-12


def _row_checks(task: str, method: str, summary: Dict, expected: Tuple, label: str) -> List[Dict]:
    names = [("cost", "suggest_cost", COST_TOL), ("recall@10", "recall", METRIC_TOL), ("f1@10", "f1", METRIC_TOL),
             ("hit@10", "hit", METRIC_TOL)]
    out = []
    for (name, key, tol), exp in zip(names, expected[:4], strict=True):
        got = summary.get(key)
        out.append({"table": label, "task": task, "method": method, "metric": name, "expected": exp, "got": got,
                    "ok": _close(got, exp, tol)})
    if expected[4] is not None:
        out.append({"table": label, "task": task, "method": method, "metric": "n", "expected": expected[4],
                    "got": summary.get("n_evaluated"), "ok": summary.get("n_evaluated") == expected[4]})
    return out


def reproduce_figure4(ds) -> List[Dict]:
    fa = ContextFactorAnalysis.from_config()
    lifts = fa.run(ds)
    counts = fa.counts(lifts)
    checks = [{"table": "Fig. 4", "task": "factors", "method": "-", "metric": f"count[{k}]", "expected": v,
               "got": counts[k], "ok": counts[k] == v} for k, v in FIG4_COUNTS.items()]
    by_id = {f.facet_id: f for f in lifts}
    for fid, values in FIG4_LIFTS.items():
        f = by_id.get(fid)
        for dim, exp in zip(("user", "task", "environment"), values, strict=True):
            if exp is None:
                continue
            got = getattr(f, f"lift_{dim}") if f else None
            checks.append({"table": "Fig. 4", "task": "factors", "method": fid, "metric": f"lift[{dim[0].upper()}]",
                           "expected": exp, "got": got, "ok": _close(got, exp, LIFT_TOL)})
    return checks


def reproduce_table(task: str, ds, out_dir: Optional[Path] = None, methods: Optional[List[str]] = None) -> List[Dict]:
    table = TABLE1 if task == "initial" else TABLE2
    manual = TABLE1_MANUAL if task == "initial" else TABLE2_MANUAL
    label = "Table 1" if task == "initial" else "Table 2"
    checks: List[Dict] = []
    for name in methods or paper_methods():
        method, protocol = build_method(name, task=task, dataset=ds)
        out = None if out_dir is None else out_dir / task / f"{name}.jsonl"
        results = evaluate(method, task, ds, out=out, **protocol)
        s = results.summary
        change = V1_CHANGES.get((task, name))
        expected = change["values"] if change else table[name]
        rows = _row_checks(task, name, s, expected, label)
        if change:
            for r in rows:
                r["note"] = f"1.0.0 change: {change['reason']} (paper: {table[name]})"
        checks += rows
        if name == "popularity":  # all scenarios evaluated: the manual baseline of the table
            checks.append({"table": label, "task": task, "method": "manual", "metric": "cost", "expected": manual,
                           "got": s["manual_cost"], "ok": _close(s["manual_cost"], manual, COST_TOL)})
    return checks


def reproduce(out_dir: Optional[Path] = None) -> List[Dict]:
    ds = load_minexrpp()
    return reproduce_figure4(ds) + reproduce_table("initial", ds, out_dir) + reproduce_table("next", ds, out_dir)


def format_checks(checks: List[Dict]) -> str:
    def fmt(v):
        if isinstance(v, float):
            return "inf" if math.isinf(v) else f"{v:.4f}"
        return str(v)

    lines = [f"ContextXR benchmark {BENCHMARK_VERSION}: paper reproduction", "",
             f"{'table':<8} {'method':<28} {'metric':<18} {'paper/expected':>14} {'got':>10}  ok"]
    for c in checks:
        lines.append(f"{c['table']:<8} {c['method'][:28]:<28} {c['metric']:<18} {fmt(c['expected']):>14} {fmt(c['got']):>10}  "
                     f"{'✓' if c['ok'] else '✗ MISMATCH'}{'  *' if c.get('note') else ''}")
    notes = sorted({c["note"] for c in checks if c.get("note")})
    if notes:
        lines += ["", *[f"* {n}" for n in notes]]
    failed = [c for c in checks if not c["ok"]]
    lines += ["", f"{len(checks) - len(failed)}/{len(checks)} checks passed"]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=None, help="write per-method results (JSONL) under this directory")
    args = parser.parse_args(argv)
    checks = reproduce(args.out)
    print(format_checks(checks))
    return 0 if all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
