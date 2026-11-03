"""Validate a ContextXR dataset directory (facet_db.json + events.csv).

Checks JSON-Schema conformance and cross-references the schema cannot express
(unique ids, edges between facets of one app, entry facets, known capabilities,
one context per scenario). Usage:

    contextxr validate PATH          # or: python -m contextxr.data.validate PATH
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Dict, List, Union

import jsonschema

from contextxr.data.loader import EVENTS_FILE, FACET_DB_FILE, read_events

PathLike = Union[str, Path]


@dataclass
class ValidationReport:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [f"{'OK' if self.ok else 'INVALID'}: {len(self.errors)} error(s), {len(self.warnings)} warning(s)"]
        lines += [f"  {k}: {v}" for k, v in self.stats.items()]
        lines += [f"ERROR   {e}" for e in self.errors]
        lines += [f"WARNING {w}" for w in self.warnings]
        return "\n".join(lines)


def _schema(name: str) -> dict:
    return json.loads(resources.files("contextxr.data").joinpath(f"schemas/{name}").read_text(encoding="utf-8"))


def _schema_errors(instance, schema, where: str) -> List[str]:
    validator = jsonschema.Draft202012Validator(schema)
    out = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in err.absolute_path)
        out.append(f"{where}{'/' + loc if loc else ''}: {err.message}")
    return out


def validate_facet_db(raw: dict, report: ValidationReport) -> None:
    report.errors += _schema_errors(raw, _schema("facet_db.schema.json"), FACET_DB_FILE)
    if report.errors:
        return
    apps = {a["app_id"]: a for a in raw["apps"]}
    if len(apps) != len(raw["apps"]):
        report.errors.append(f"{FACET_DB_FILE}: duplicate app_id values")
    facets: Dict[str, dict] = {}
    for i, f in enumerate(raw["facets"]):
        where = f"{FACET_DB_FILE}/facets/{i} ({f['facet_id']})"
        if f["facet_id"] in facets:
            report.errors.append(f"{where}: duplicate facet_id")
        facets[f["facet_id"]] = f
        if f["app_id"] not in apps:
            report.errors.append(f"{where}: unknown app_id '{f['app_id']}'")
            continue
        if not f["facet_id"].startswith(f["app_id"] + "."):
            report.errors.append(f"{where}: facet_id must start with '{f['app_id']}.'")
        unknown = [c for c in f["capabilities"] if c not in set(apps[f["app_id"]]["capabilities"])]
        if unknown:
            report.errors.append(f"{where}: capabilities not listed on app: {unknown[:5]}")
    for app_id, a in apps.items():
        if a["entry_facet_id"] not in facets:
            report.errors.append(f"{FACET_DB_FILE}/apps ({app_id}): entry_facet_id '{a['entry_facet_id']}' is not a facet")
        used = {c for f in raw["facets"] if f["app_id"] == app_id for c in f["capabilities"]}
        unused = [c for c in a["capabilities"] if c not in used]
        if unused:
            report.warnings.append(f"{FACET_DB_FILE}/apps ({app_id}): capabilities in no facet: {unused[:5]}")
    edge_caps = defaultdict(set)
    for i, e in enumerate(raw["edges"]):
        where = f"{FACET_DB_FILE}/edges/{i} ({e['source']} -> {e['target']})"
        src, tgt = facets.get(e["source"]), facets.get(e["target"])
        if src is None or tgt is None:
            report.errors.append(f"{where}: endpoint is not a facet")
            continue
        if src["app_id"] != tgt["app_id"]:
            report.errors.append(f"{where}: edges must connect facets of the same app")
        if e["capability"] not in src["capabilities"]:
            report.errors.append(f"{where}: capability '{e['capability']}' is not a capability of the source facet")
        edge_caps[e["source"]].add(e["capability"])
    for fid, f in facets.items():
        missing = [c for c in f["capabilities"] if c.startswith("open_") and c not in edge_caps[fid]]
        if missing:
            report.warnings.append(f"{FACET_DB_FILE}/facets ({fid}): navigational capabilities without an edge: {missing}")
    # Reachability of every facet from its app's entry facet (manual navigation must be defined).
    from contextxr.data.loader import catalog_from_dict

    catalog = catalog_from_dict(raw)
    unreachable = [fid for fid in facets if catalog.graph_of(fid).path_from_entry(fid) is None]
    if unreachable:
        report.warnings.append(f"{FACET_DB_FILE}: {len(unreachable)} facet(s) unreachable from their entry facet: {unreachable[:5]}")
    report.stats.update(
        apps=len(apps),
        facets=len(facets),
        capabilities_distinct_names=len({c for a in apps.values() for c in a["capabilities"]}),
        capabilities_app_pairs=sum(len(a["capabilities"]) for a in apps.values()),
        edges=len(raw["edges"]),
    )


def validate_events(rows: List[Dict[str, str]], raw_db: dict, report: ValidationReport) -> None:
    schema = _schema("events.schema.json")
    tier_schema = dict(schema["$defs"]["capability_tiers"])
    facets = {f["facet_id"]: f for f in raw_db.get("facets", [])}
    app_caps = {a["app_id"]: set(a["capabilities"]) for a in raw_db.get("apps", [])}
    contexts: Dict[str, tuple] = {}
    seen = set()
    unknown_caps = 0
    for i, row in enumerate(rows, start=2):  # line 1 is the header
        where = f"{EVENTS_FILE}:{i}"
        errs = _schema_errors(row, schema, where)
        if errs:
            report.errors += errs
            continue
        try:
            caps = json.loads(row["capabilities"] or "{}")
        except json.JSONDecodeError as exc:
            report.errors.append(f"{where}/capabilities: not valid JSON ({exc.msg})")
            continue
        report.errors += _schema_errors(caps, tier_schema, f"{where}/capabilities")
        for cap in caps:
            app_id, _, name = cap.partition(".")
            if name not in app_caps.get(app_id, set()):
                unknown_caps += 1
        key = (row["scenario_id"], row["widget_id"])
        if key in seen:
            report.errors.append(f"{where}: duplicate (scenario_id, widget_id) {key}")
        seen.add(key)
        ctx = (row["participant_id"], row["task"], row["environment"])
        if contexts.setdefault(row["scenario_id"], ctx) != ctx:
            report.errors.append(f"{where}: scenario '{row['scenario_id']}' has inconsistent context {ctx} vs {contexts[row['scenario_id']]}")
        fid = row.get("facet_id", "")
        if fid and fid not in facets:
            report.errors.append(f"{where}: unknown facet_id '{fid}'")
        if fid and row.get("app_id") and facets.get(fid, {}).get("app_id") != row["app_id"]:
            report.errors.append(f"{where}: facet '{fid}' does not belong to app '{row['app_id']}'")
    if unknown_caps:
        report.warnings.append(f"{EVENTS_FILE}: {unknown_caps} capability reference(s) not in the facet DB (ignored when deriving targets)")
    report.stats.update(
        widgets=len(rows),
        scenarios=len(contexts),
        participants=len({c[0] for c in contexts.values()}),
    )


def validate_dataset(path: PathLike) -> ValidationReport:
    """Validate a directory containing facet_db.json and events.csv."""
    path = Path(path)
    report = ValidationReport()
    db_path, ev_path = path / FACET_DB_FILE, path / EVENTS_FILE
    for p in (db_path, ev_path):
        if not p.exists():
            report.errors.append(f"missing file: {p}")
    if report.errors:
        return report
    try:
        raw_db = json.loads(db_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.errors.append(f"{FACET_DB_FILE}: not valid JSON (line {exc.lineno}: {exc.msg})")
        return report
    validate_facet_db(raw_db, report)
    validate_events(read_events(ev_path), raw_db, report)
    if report.ok:
        from contextxr.data.loader import load_dataset

        ds = load_dataset(path)
        empty = [sid for sid, s in ds.scenarios.items() if not s.targets]
        if empty:
            report.warnings.append(f"{len(empty)} scenario(s) have no target facets: {empty[:5]}")
        report.stats.update(targets=sum(len(s.targets) for s in ds), placed_facets_distinct=len(ds.placed_facets()))
    return report


def main(argv: List[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m contextxr.data.validate DATASET_DIR", file=sys.stderr)
        return 2
    report = validate_dataset(argv[0])
    print(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
