"""Command-line interface.

    contextxr run --task initial --method relational [--out runs/relational_initial.jsonl]
    contextxr run --task next --method "few_shot_llm[user]" --live
    contextxr run --task factors
    contextxr reproduce [--out runs/paper]
    contextxr validate PATH
    contextxr methods
    contextxr export-web            (not yet implemented)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from contextxr import BENCHMARK_VERSION, __version__


def _cmd_run(args) -> int:
    from contextxr.data.loader import load_dataset, load_minexrpp

    dataset = load_dataset(args.data) if args.data else load_minexrpp()
    if args.task == "factors":
        from contextxr.tasks.factor_analysis import ContextFactorAnalysis

        fa = ContextFactorAnalysis.from_config(args.factor_config)
        lifts = fa.run(dataset)
        counts = fa.counts(lifts)
        print(f"dominant context factor over {len(lifts)} facets: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        if args.out:
            print("wrote", fa.to_jsonl(lifts, args.out, dataset))
        return 0

    if not args.method:
        print("--method is required for --task initial/next (see `contextxr methods`)", file=sys.stderr)
        return 2
    from contextxr.methods.llm_cache import LLMCache
    from contextxr.methods.registry import build_method
    from contextxr.metrics.cost_model import DefaultCostModel
    from contextxr.runner import evaluate, format_table

    cache = LLMCache(mode="live" if args.live else "replay")
    method, protocol = build_method(args.method, task=args.task, dataset=dataset, cache=cache)
    folds = None if args.no_cv else ("paper" if not args.data else None)
    if args.data and not args.no_cv:
        print("note: custom dataset, fitting on all scenarios (no folds); use the Python API for custom folds",
              file=sys.stderr)
    cost_model = DefaultCostModel.from_config(args.cost_config) if args.cost_config else None
    results = evaluate(method, args.task, dataset, cost_model=cost_model, folds=folds, out=args.out, **protocol)
    print(format_table([results]))
    if args.out:
        print("wrote", args.out)
    return 0


def _cmd_reproduce(args) -> int:
    from contextxr.reproduce import format_checks, reproduce

    checks = reproduce(args.out)
    print(format_checks(checks))
    return 0 if all(c["ok"] for c in checks) else 1


def _cmd_validate(args) -> int:
    from contextxr.data.validate import validate_dataset

    report = validate_dataset(args.path)
    print(report)
    return 0 if report.ok else 1


def _cmd_methods(args) -> int:
    from contextxr.methods.registry import method_configs, paper_methods

    configs = method_configs()
    for name in paper_methods() + sorted(set(configs) - set(paper_methods())):
        print(f"{name:28} {configs[name]['class']}")
    return 0


def _cmd_export_web(args) -> int:
    # TODO(website): convert results JSONL (docs/results_format.md) into the static site's data files.
    print("contextxr export-web is not implemented yet; the website export is a separate task.", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contextxr", description=f"ContextXR benchmark {BENCHMARK_VERSION}")
    parser.add_argument("--version", action="version", version=f"contextxr {__version__} (benchmark {BENCHMARK_VERSION})")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="evaluate a method on a task (or run the context factor analysis)")
    run.add_argument("--task", required=True, choices=["initial", "next", "factors"])
    run.add_argument("--method", help="method name (see `contextxr methods`)")
    run.add_argument("--out", type=Path, help="write results as JSON Lines (docs/results_format.md)")
    run.add_argument("--data", type=Path, help="dataset directory (default: MineXR++)")
    run.add_argument("--live", action="store_true", help="call the LLM on cache misses and record responses")
    run.add_argument("--cost-config", type=Path, help="YAML with DefaultCostModel parameters")
    run.add_argument("--factor-config", type=Path, help="YAML for the context factor analysis")
    run.add_argument("--no-cv", action="store_true", help="fit once on all scenarios instead of the paper's folds")
    run.set_defaults(func=_cmd_run)

    rep = sub.add_parser("reproduce", help="regenerate the paper's Figure 4 and Tables 1-2 from the cache")
    rep.add_argument("--out", type=Path, help="write per-method results under this directory")
    rep.set_defaults(func=_cmd_reproduce)

    val = sub.add_parser("validate", help="validate a dataset directory (facet_db.json + events.csv)")
    val.add_argument("path", type=Path)
    val.set_defaults(func=_cmd_validate)

    met = sub.add_parser("methods", help="list available methods")
    met.set_defaults(func=_cmd_methods)

    web = sub.add_parser("export-web", help="export results for the project website (not yet implemented)")
    web.set_defaults(func=_cmd_export_web)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    from contextxr.methods.llm_cache import CacheMiss

    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except CacheMiss as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
