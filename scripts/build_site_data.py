#!/usr/bin/env python3
"""Export MineXR++ facet graphs for the project website.

    python scripts/build_site_data.py [--data data/minexrpp] [--out site/data/minexrpp.js]

Writes a JS file that sets `window.MINEXRPP`, so the site works from file:// without a server.
Usage counts: the number of scenarios in which a facet (or an app) is some element's `facet_id`.
Scenarios carry their target set Y_q (contextxr.data.loader.derive_targets) and, per target
facet, the capabilities the placed widgets expose. TASK_CATEGORIES groups MineXR's free-text
task labels for browsing on the website only; the benchmark keeps the raw labels. site_user()
renumbers participants for display (see there). `factors` is the context factor analysis
(paper §4.1, Fig. 4) as the benchmark computes it.
"""

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from contextxr.data.loader import load_dataset, normalize_tier, resolve_capability_facet
from contextxr.tasks.factor_analysis import ContextFactorAnalysis

ROOT = Path(__file__).resolve().parent.parent

# MineXR numbers its participants in two series, P01-P10 and P002-P022. They are different
# people whose numbers collide (P03 vs P003), so the site shows one series: P002-P022 continue
# after P10 as P11-P31. Scenario ids, the benchmark and its methods keep the original ids.
def site_user(user: str) -> str:
    m = re.fullmatch(r"P0(\d\d)", user)
    return f"P{int(m.group(1)) + 9:02d}" if m else user


def site_text(text: str) -> str:
    """Renumber participant ids inside free text (e.g. an LLM's rationale); scenario ids stay."""
    return re.sub(r"\bP\d{2,3}\b", lambda m: site_user(m.group(0)), text)


ENVIRONMENTS = {"office": "Office", "coffeeshop": "Coffee shop", "kitchen": "Kitchen", "livingroom": "Living room"}

TASK_CATEGORIES = {
    "Work": ["Work", "WorkingAlone", "Working", "FocusWork", "workonlaptop", "Doingwork", "Remotework",
             "WorkingWithFriend", "WorkingWithFriends", "Figuringoutnexttask"],
    "Meetings": ["InPersonMeeting", "RemoteMeeting", "Remotemeeting", "Zoomcall", "Discussion"],
    "Reading & study": ["reading", "Reading", "Readingbook", "ReadingPaper", "Readingpaper", "Readpaper", "Studying"],
    "Cooking & food": ["Cooking", "CookingSolo", "CookingWithFriends", "CookingInstruction", "BakingWithFriends",
                       "MakingCoffee", "CoffeeMaking", "Eating", "Dining", "Planningfordinner", "Lookingforlunch",
                       "buyingadrink", "Drinkingcoffee"],
    "Socializing": ["CasualChat", "Chatwithfriend", "ChatWithFriends", "Chatting", "Talkingwithfriends",
                    "HangoutWithFriend", "hangingoutwithfriends", "socialize", "Entertaining", "Playingboardgame",
                    "Watchingmoviewithfriends"],
    "Relaxing & media": ["Relaxing", "Chilling", "Watchingtv", "Watchingshow", "WatchingVideo", "Watchingvideos",
                         "Browsing", "Browsinginternet", "Scrollingonphone", "PlayiPhone", "Playingpcgames",
                         "Playgames", "Shopping"],
    "Workout": ["Workout", "Workingout"],
    "Routines & errands": ["Morning", "MorningRoutine", "Dailyroutine", "Leaving", "Wheretogonext"],
}
TASK_CATEGORY = {label: cat for cat, labels in TASK_CATEGORIES.items() for label in labels}


def build_scenarios(data_dir: Path) -> list:
    dataset = load_dataset(data_dir)
    out = []
    for sc in dataset:
        ctx = sc.context
        env_key = "".join(ch for ch in ctx.environment.lower() if ch.isalnum())
        if ctx.task not in TASK_CATEGORY:
            raise SystemExit(f"task label {ctx.task!r} has no category in TASK_CATEGORIES")
        targets = sc.target_tiers
        merged = {}
        for w in sc.widgets:
            merged.update(w.capability_tiers)
        caps = defaultdict(dict)
        for cap_id, tier in merged.items():
            facet_id = resolve_capability_facet(cap_id, dataset.catalog)
            if facet_id in targets:
                caps[facet_id][cap_id.partition(".")[2]] = normalize_tier(tier)
        out.append({
            "id": sc.scenario_id,
            "user": site_user(ctx.user),
            "task": ctx.task,
            "taskCat": TASK_CATEGORY[ctx.task],
            "env": ENVIRONMENTS[env_key],
            "targets": targets,
            "caps": caps,
            "widgets": [
                {"app": w.app_id, "facet": w.facet_id, "desc": w.widget_desc, "screen": w.screen_desc}
                for w in sc.widgets
            ],
        })
    out.sort(key=lambda s: (s["user"], s["env"], s["task"]))
    return out


def build_factors(data_dir: Path) -> dict:
    """Per-facet lifts (U, T, E), dominant factor and occurrences; facets placed in < 2 layouts are left out."""
    fa = ContextFactorAnalysis.from_config()
    lifts = fa.run(load_dataset(data_dir))
    def r(x):
        return round(x, 3)

    return {
        "dominanceRatio": fa.dominance_ratio,
        "counts": fa.counts(lifts),
        "facets": [
            {"id": f.facet_id, "n": f.occurrences, "lift": [r(f.lift_user), r(f.lift_task), r(f.lift_environment)], "dominant": f.dominant}
            for f in lifts
        ],
    }


def build(data_dir: Path) -> dict:
    db = json.loads((data_dir / "facet_db.json").read_text())

    facet_scenarios = defaultdict(set)
    app_scenarios = defaultdict(set)
    scenarios = set()
    with open(data_dir / "events.csv", newline="") as f:
        for row in csv.DictReader(f):
            scenarios.add(row["scenario_id"])
            if row["facet_id"]:
                facet_scenarios[row["facet_id"]].add(row["scenario_id"])
                app_scenarios[row["app_id"]].add(row["scenario_id"])

    capability_names = {c for a in db["apps"] for c in a["capabilities"]}
    return {
        "name": db["name"],
        "benchmark_version": db["benchmark_version"],
        "stats": {
            "apps": len(db["apps"]),
            "facets": len(db["facets"]),
            "capabilities": len(capability_names),
            "edges": len(db["edges"]),
            "scenarios": len(scenarios),
        },
        "apps": [
            {
                "id": a["app_id"],
                "name": a["app_name"],
                "domain": a["app_domain"],
                "entry": a["entry_facet_id"],
                "uses": len(app_scenarios[a["app_id"]]),
            }
            for a in db["apps"]
        ],
        "facets": [
            {
                "id": f["facet_id"],
                "app": f["app_id"],
                "name": f["name"],
                "desc": f["description"],
                "caps": f["capabilities"],
                "uses": len(facet_scenarios[f["facet_id"]]),
            }
            for f in db["facets"]
        ],
        "edges": [[e["source"], e["target"], e["capability"]] for e in db["edges"]],
        "taskCategories": list(TASK_CATEGORIES),
        "environments": list(ENVIRONMENTS.values()),
        "scenarios": build_scenarios(data_dir),
        "factors": build_factors(data_dir),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", type=Path, default=ROOT / "data" / "minexrpp")
    p.add_argument("--out", type=Path, default=ROOT / "site" / "data" / "minexrpp.js")
    args = p.parse_args()

    payload = build(args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "// Generated by scripts/build_site_data.py. Do not edit.\n"
        f"window.MINEXRPP = {json.dumps(payload, separators=(',', ':'))};\n"
    )
    s = payload["stats"]
    print(f"wrote {args.out} ({s['apps']} apps, {s['facets']} facets, {s['edges']} edges)")


if __name__ == "__main__":
    main()
