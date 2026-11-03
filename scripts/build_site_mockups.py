#!/usr/bin/env python3
"""Validate the facet mockup specs and bundle them for the project website.

    python scripts/build_site_mockups.py [--strict] [--out site/data/mockups.js]

Reads site/mockups/<app_id>.json (format: site/mockups/SCHEMA.md) and checks that each facet's
elements are exactly its capabilities. Embeds the Lucide icons the specs use
(scripts/vendor/lucide). Facets without a spec are reported; --strict makes that an error.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / "site" / "mockups"
ICONS = ROOT / "scripts" / "vendor" / "lucide" / "icon-nodes.json"

# type -> required fields
BLOCK_TYPES = {
    "header": ["title"], "text": ["text"], "list": ["items"], "kv": ["items"], "media": [],
    "player": [], "controls": ["items"], "button": ["label"], "buttons": ["items"], "link": ["label"],
    "tabs": ["items"], "toggle": ["label"], "slider": ["label"], "stepper": ["label", "value"],
    "input": [], "chips": ["items"], "segmented": ["items"], "select": ["label", "value"],
    "stat": ["value"], "progress": [], "timer": ["display"], "grid": ["items"], "cards": ["items"],
    "map": [], "chart": [], "calendar": [], "chat": ["items"], "keypad": [], "avatar": ["name"],
    "badge": ["label"], "notice": ["title"], "rating": ["value"], "code": ["lines"],
    "row": ["blocks"], "group": ["cap", "blocks"],
}
ITEM_CAP_TYPES = {"controls", "buttons", "tabs"}  # caps live on items
RENDERER_ICONS = ["check", "play", "chevron-right", "chevron-down", "minus", "plus", "image", "app-window"]  # js/mockups.js


class SpecError(Exception):
    pass


def walk(blocks, where, icons, *, in_group=False):
    """Yield (block_index_path, caps_of_block) for capability-bearing blocks; collect icon names."""
    if not isinstance(blocks, list) or not blocks:
        raise SpecError(f"{where}: 'blocks' must be a non-empty list")
    for i, b in enumerate(blocks):
        here = f"{where}[{i}]"
        t = b.get("type")
        if t not in BLOCK_TYPES:
            raise SpecError(f"{here}: unknown type {t!r}")
        for field in BLOCK_TYPES[t]:
            if field not in b:
                raise SpecError(f"{here} ({t}): missing {field!r}")
        for key in ("icon", "trailing"):
            if isinstance(b.get(key), str) and key == "icon":
                icons.add((b[key], here))
        if t == "input" and b.get("trailing"):
            icons.add((b["trailing"], here))
        if isinstance(b.get("thumb"), dict) and b["thumb"].get("icon"):
            icons.add((b["thumb"]["icon"], here))
        caps = set()
        if b.get("cap"):
            caps.add(b["cap"])
        caps.update(b.get("caps") or [])
        actions = set()  # row actions; one capability may repeat across rows of the same list
        for j, it in enumerate(b.get("items") or []):
            if isinstance(it, dict):
                if it.get("icon"):
                    icons.add((it["icon"], f"{here}.items[{j}]"))
                if it.get("cap"):
                    if t not in ITEM_CAP_TYPES:
                        raise SpecError(f"{here}.items[{j}]: item 'cap' is only allowed in {sorted(ITEM_CAP_TYPES)}")
                    caps.add(it["cap"])
                act = it.get("action")
                if act:
                    if t != "list" or not act.get("cap") or not act.get("icon"):
                        raise SpecError(f"{here}.items[{j}]: 'action' needs a list item, 'cap' and 'icon'")
                    icons.add((act["icon"], f"{here}.items[{j}].action"))
                    actions.add(act["cap"])
            elif t in ITEM_CAP_TYPES:
                raise SpecError(f"{here}.items[{j}]: must be an object with 'cap'")
        if actions:
            yield f"{here}.actions", actions
        if t in ITEM_CAP_TYPES and any(isinstance(it, dict) and not it.get("cap") for it in b["items"]):
            raise SpecError(f"{here}: every item of a {t} block needs a 'cap'")
        if in_group and caps:
            raise SpecError(f"{here}: blocks inside a group carry no cap")
        if t == "row":
            if caps:
                raise SpecError(f"{here}: a row has no cap of its own")
            yield from walk(b["blocks"], f"{here}.blocks", icons, in_group=in_group)
            continue
        if t == "group":
            list(walk(b["blocks"], f"{here}.blocks", icons, in_group=True))
        if not caps and not in_group:
            raise SpecError(f"{here} ({t}): no capability (use 'cap', 'caps' or item caps)")
        if caps:
            yield here, caps


def check_facet(fid, facet, spec, icons):
    seen = {}
    for where, caps in walk(spec.get("blocks"), fid, icons):
        for c in caps:
            if c in seen:
                raise SpecError(f"{fid}: capability {c!r} appears in two elements ({seen[c]} and {where})")
            seen[c] = where
    expected = set(facet["capabilities"])
    extra = set(seen) - expected
    missing = expected - set(seen)
    if extra:
        raise SpecError(f"{fid}: not capabilities of this facet: {sorted(extra)}")
    if missing:
        raise SpecError(f"{fid}: capabilities without an element: {sorted(missing)}")


def build(strict: bool):
    db = json.loads((ROOT / "data" / "minexrpp" / "facet_db.json").read_text())
    facets = {f["facet_id"]: f for f in db["facets"]}
    lucide = json.loads(ICONS.read_text())
    errors, apps, specs, used_icons = [], {}, {}, {(n, "renderer") for n in RENDERER_ICONS}

    for path in sorted(SPEC_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        app = raw.get("app")
        if app != path.stem:
            errors.append(f"{path.name}: 'app' must be {path.stem!r}")
            continue
        apps[app] = {"icon": raw.get("icon", "app-window"), "color": raw.get("color", "#868e96")}
        used_icons.add((apps[app]["icon"], path.name))
        for fid, spec in (raw.get("facets") or {}).items():
            if fid not in facets or facets[fid]["app_id"] != app:
                errors.append(f"{path.name}: unknown facet {fid!r}")
                continue
            icons = set()
            try:
                check_facet(fid, facets[fid], spec, icons)
            except SpecError as exc:
                errors.append(str(exc))
                continue
            used_icons |= icons
            specs[fid] = spec["blocks"]

    for name, where in sorted(used_icons):
        if name not in lucide:
            errors.append(f"{where}: unknown Lucide icon {name!r}")
    missing = sorted(set(facets) - set(specs))
    return db, apps, specs, {n: lucide[n] for n, _ in used_icons if n in lucide}, errors, missing


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--strict", action="store_true", help="fail if any facet has no spec")
    p.add_argument("--out", type=Path, default=ROOT / "site" / "data" / "mockups.js")
    args = p.parse_args()

    db, apps, specs, icons, errors, missing = build(args.strict)
    for e in errors:
        print("error:", e, file=sys.stderr)
    if missing:
        print(f"{len(missing)} facets have no spec yet" + (f": {', '.join(missing[:8])}…" if missing else ""), file=sys.stderr)
    if errors or (args.strict and missing):
        sys.exit(1)
    args.out.write_text(
        "// Generated by scripts/build_site_mockups.py from site/mockups/*.json. Do not edit.\n"
        f"window.MINEXRPP_MOCKUPS = {json.dumps({'apps': apps, 'facets': specs, 'icons': icons}, separators=(',', ':'), ensure_ascii=False)};\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out} ({len(specs)}/{len(db['facets'])} facets, {len(icons)} icons)")


if __name__ == "__main__":
    main()
