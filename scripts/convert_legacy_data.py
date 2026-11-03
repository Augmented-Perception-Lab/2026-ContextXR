#!/usr/bin/env python3
"""One-off conversion of the legacy research data into the ContextXR v1 format.

Run once from the repository root while the legacy `python/` tree is present:

    python scripts/convert_legacy_data.py

It calls the legacy code directly (so the output is equivalent by construction) and
writes:

    data/minexrpp/facet_db.json          apps, facets, capabilities, explicit facet-graph edges
    data/minexrpp/events.csv             one row per placed MineXR widget
    configs/splits/cv5_seed42.json       scenario-level CV fold assignments used in the paper
    configs/splits/next_order_seed42.json  step order of targets for next facet suggestion
    tests/data/legacy_reference.json     golden values for equivalence tests

Raw widget images, image paths and absolute paths are not exported.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "python"
sys.path[:0] = [str(LEGACY / "scripts"), str(LEGACY)]

from interaction_cost_dashboard import CostWeights, compute_manual_interaction_cost_results  # noqa: E402
from static_support_common import load_static_support_resources  # noqa: E402
from task_eval_common import order_units  # noqa: E402

BENCHMARK_VERSION = "1.0.0"
ANNOTATIONS = LEGACY / "data/MineXR/minexr_capability_annotations.json"
FACETS = LEGACY / "data/functional_facets/functional_facets.json"
# Paper runs: hitl_context_facet_eval_20260330_150750 (next facet) and
# artifacts/context_facet_dashboard_eval_20260329_191555 (initial) share these folds.
FOLDS_SOURCE = LEGACY / "results/static_support/context_facet_human_in_the_loop/hitl_context_facet_eval_rows_20260330_150750.csv"
FOLDS_CROSSCHECK = LEGACY / "artifacts/context_facet_dashboard_eval_20260329_191555.json"
PAPER_WEIGHTS = CostWeights(1.0, 0.0, 1.0, 0.0, 20, 1.0)
SEED = 42

# v1.0.0 renames: typos and IDs that did not match the navigational capability that opens
# them. With these, every open_<facet> capability names its target exactly. Old IDs are
# kept as `legacy_ids` in the facet DB (the paper's prompts and predictions use them).
FACET_RENAMES = {
    "clock.mange_alarm_list": "clock.manage_alarm_list",
    "clock.responsd_to_alarm": "clock.respond_to_alarm",
    "uber_eats.track_oder": "uber_eats.track_order",
    "instagram.browse_Explore": "instagram.browse_explore",
    "gmail.view_email_content_actions": "gmail.view_email_contents_actions",
    "gmail.navigate_mailboxes_accounts": "gmail.navigate_mailboxes_and_accounts",
    "amazon.checkout": "amazon.checkout_purchase",
    "camera.select_mode": "camera.select_capture_mode",
    "uber_eats.view_order_history": "uber_eats.view_order_history_reorder",
    "slack.browse_workspace": "slack.browse_workspaces",
}


def rn(facet_id: str) -> str:
    return FACET_RENAMES.get(facet_id, facet_id)


def _dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def build_facet_db(resources) -> dict:
    raw = json.loads(FACETS.read_text(encoding="utf-8"))
    apps, facets, edges = [], [], []
    for raw_app in raw["apps"]:
        app_id = raw_app["app_id"]
        graph = resources.app_graphs[app_id]
        apps.append(
            {
                "app_id": app_id,
                "app_name": raw_app.get("app_name") or app_id,
                "app_domain": raw_app.get("app_domain") or "",
                "entry_facet_id": graph.start_facet_id,
                "capabilities": list(raw_app.get("capabilities", [])),
            }
        )
        for raw_facet in raw_app["facets"]:
            record = {
                "facet_id": rn(raw_facet["facet_id"]),
                "app_id": app_id,
                "name": raw_facet.get("name") or "",
                "description": raw_facet.get("description") or "",
                "capabilities": [str(c).lstrip(".") for c in raw_facet.get("capabilities", [])],
            }
            if raw_facet["facet_id"] in FACET_RENAMES:
                record["legacy_ids"] = [raw_facet["facet_id"]]
            facets.append(record)
        # Re-resolve each open_* capability with the legacy resolver to record how it matched.
        for source_id, facet in graph.facets.items():
            for capability in facet["capabilities"]:
                if not capability.startswith("open_"):
                    continue
                target_id, strategy = graph._resolve_target_facet(capability[5:])
                if target_id is None:
                    raise SystemExit(f"Unresolved navigational capability {source_id}:{capability}")
                source, target = rn(source_id), rn(target_id)
                if capability[5:] != target.split(".", 1)[1]:
                    raise SystemExit(f"Edge {source}:{capability} -> {target} still needs name matching ({strategy})")
                edges.append({"source": source, "target": target, "capability": capability, "resolution": "exact"})
    return {
        "format": "contextxr.facet_db",
        "format_version": "1.0",
        "benchmark_version": BENCHMARK_VERSION,
        "name": "MineXR++",
        "description": "Functional facet database of MineXR++ (Cho et al., UIST '26).",
        "apps": apps,
        "facets": facets,
        "edges": edges,
    }


def build_events(manual_results) -> list:
    annotations = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))["annotations"]
    selected = {
        (row["scenario_id"], str(row["widget_anchor_id"])): row for row in manual_results["widget_results"]
    }
    rows = []
    for entry in annotations.values():  # file order matters: later widgets overwrite tiers
        meta = entry["meta"]
        key = (meta["scenario_id"], str(meta["widget_anchor_id"]))
        sel = selected[key]
        rows.append(
            {
                "scenario_id": meta["scenario_id"],
                "participant_id": meta["participant_id"],
                "task": meta["task_id"],
                "environment": meta["environment_id"],
                "widget_id": str(meta["widget_anchor_id"]),
                "app_id": (sel.get("selected_app_id") or "") if sel.get("resolved") else "",
                "facet_id": rn(sel.get("selected_facet_id") or "") if sel.get("resolved") else "",
                "capabilities": json.dumps(entry.get("capabilities") or {}, ensure_ascii=False),
                "widget_desc": meta.get("widget_desc") or "",
                "screen_desc": meta.get("screen_desc") or "",
            }
        )
    return rows


def build_folds() -> dict:
    csv.field_size_limit(10**9)
    folds = {}
    with FOLDS_SOURCE.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            folds.setdefault(row["scenario_id"], int(row["fold_index"]))
    cross = json.loads(FOLDS_CROSSCHECK.read_text(encoding="utf-8"))
    other = {s["scenario_id"] if "scenario_id" in s else s["scenario_key"]: int(s["fold_index"]) for s in cross["scenarios"]}
    mismatches = [k for k in folds if other.get(k) != folds[k]]
    if mismatches or len(folds) != len(other):
        raise SystemExit(f"Fold sources disagree: {mismatches[:5]} ({len(folds)} vs {len(other)})")
    return dict(sorted(folds.items()))


def main() -> None:
    resources, scenarios = load_static_support_resources(
        annotations_path=str(ANNOTATIONS),
        facets_path=str(FACETS),
        app_sort_key="annotation_occurrence",
        weights=PAPER_WEIGHTS,
    )
    manual = compute_manual_interaction_cost_results(
        annotations_path=ANNOTATIONS.resolve(),
        facets_path=FACETS.resolve(),
        weights=PAPER_WEIGHTS,
        app_sort_key="annotation_occurrence",
        text_score_weight=0.35,
    )

    facet_db = build_facet_db(resources)
    _dump(ROOT / "data/minexrpp/facet_db.json", facet_db)

    events = build_events(manual)
    out = ROOT / "data/minexrpp/events.csv"
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(events[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(events)

    folds = build_folds()
    _dump(
        ROOT / "configs/splits/cv5_seed42.json",
        {
            "benchmark_version": BENCHMARK_VERSION,
            "dataset": "MineXR++",
            "description": "Scenario-level 5-fold CV used for global popularity and relational retrieval in the paper "
            "(seed 42; scenarios shuffled with random.Random(42) in event-file order, assigned round-robin).",
            "n_folds": 5,
            "seed": SEED,
            "folds": folds,
        },
    )

    orders = {
        key: [
            rn(f)
            for f in order_units(dict(sorted(sc.ground_truth_facets.items())), policy="random", scenario_key=key, seed=SEED)
        ]
        for key, sc in sorted(scenarios.items())
    }
    _dump(
        ROOT / "configs/splits/next_order_seed42.json",
        {
            "benchmark_version": BENCHMARK_VERSION,
            "dataset": "MineXR++",
            "description": "Order in which each scenario's targets are revealed in next facet suggestion "
            "(seeded shuffle: random.Random('42|<scenario_id>|random') over the sorted target ids, computed with the "
            "pre-1.0 facet ids and then renamed, so the order is exactly the paper's).",
            "seed": SEED,
            "orders": orders,
        },
    )

    paths = {}
    for _app_id, graph in resources.app_graphs.items():
        for facet_id in graph.facets:
            p = graph.path_to(facet_id)
            paths[rn(facet_id)] = None if p is None else len(p)
    reference = {
        "source": "legacy python/ pipeline (static_support_common.load_static_support_resources, "
        "interaction_cost_dashboard.compute_manual_interaction_cost_results)",
        "facet_renames": FACET_RENAMES,
        "targets": {
            k: dict(sorted((rn(f), t) for f, t in sc.ground_truth_facets.items())) for k, sc in sorted(scenarios.items())
        },
        "contexts": {
            k: [sc.participant_id, sc.task_id, sc.environment_id] for k, sc in sorted(scenarios.items())
        },
        "entry_path_nodes": dict(sorted(paths.items())),
        "app_library": [
            {"app_id": r["app_id"], "position": r["position"], "count": r["annotation_occurrence_count"]}
            for r in manual["app_library"]
        ],
        "training_events": len([e for e in events if e["facet_id"]]),
    }
    _dump(ROOT / "tests/data/legacy_reference.json", reference)

    print(
        json.dumps(
            {
                "apps": len(facet_db["apps"]),
                "facets": len(facet_db["facets"]),
                "edges": len(facet_db["edges"]),
                "edge_resolution": Counter(e["resolution"] for e in facet_db["edges"]),
                "widgets": len(events),
                "scenarios": len(scenarios),
                "targets": sum(len(sc.ground_truth_facets) for sc in scenarios.values()),
                "folds": Counter(folds.values()),
            },
            indent=1,
            default=dict,
        )
    )


if __name__ == "__main__":
    main()
