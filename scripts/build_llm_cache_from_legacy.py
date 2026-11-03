#!/usr/bin/env python3
"""Build cache/llm/ from the LLM outputs saved by the paper runs (no API calls).

The paper runs saved, for every LLM call, the full user prompt and the parsed JSON
response, but not the raw response text. This script:

1. rebuilds each prompt with `contextxr.methods.llm` on the pre-1.0 facet ids and
   checks it is byte-identical to the saved prompt (this verifies the port);
2. maps renamed facet ids in the saved response to their 1.0.0 ids and checks that
   the 1.0.0 normalizer yields exactly the paper's prediction list;
3. stores the response, re-serialized as JSON, under the key of the 1.0.0 prompt,
   marked `"provenance": "reconstructed_from_parsed"`. Calls whose response could
   not be parsed are stored as cached errors.

Run from the repository root while the legacy `python/` tree is present:

    python scripts/build_llm_cache_from_legacy.py
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

from contextxr.data.loader import catalog_from_dict, load_minexrpp, read_events, scenarios_from_events
from contextxr.data.schema import Dataset
from contextxr.methods.base import SuggestionUnavailable
from contextxr.methods.llm import LEGACY_CONDITION_KEYS, LLMSuggester, catalog_text
from contextxr.methods.llm_cache import LLMCache, LLMRequest, LLMResponse
from contextxr.tasks.common import PlacedFacet

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "python" / "results" / "static_support"
INITIAL_ZERO_SHOT = RESULTS / "static_support_eval_20260322_120448_corrected_ground_truth.json"
INITIAL_FEW_SHOT = RESULTS / "static_support_eval_20260322_164757-warmstart.json"
NEXT_ALL = RESULTS / "human_in_the_loop" / "hitl_eval_20260329_175808.json"
MODEL = "gemini-3-flash-preview"
TEMPERATURE = 0.2
CONDITION_BY_LEGACY = {v: k for k, v in LEGACY_CONDITION_KEYS.items()}


def legacy_view(ds: Dataset) -> Dataset:
    """The same dataset with pre-1.0 facet ids (as used in the paper's prompts)."""
    back = {f.facet_id: f.legacy_ids[0] for f in ds.catalog if f.legacy_ids}
    raw = json.loads((ROOT / "data/minexrpp/facet_db.json").read_text(encoding="utf-8"))
    raw = deepcopy(raw)
    for f in raw["facets"]:
        f["facet_id"] = back.get(f["facet_id"], f["facet_id"])
        f.pop("legacy_ids", None)
    for e in raw["edges"]:
        e["source"], e["target"] = back.get(e["source"], e["source"]), back.get(e["target"], e["target"])
    catalog = catalog_from_dict(raw)
    rows = read_events(ROOT / "data/minexrpp/events.csv")
    for r in rows:
        r["facet_id"] = back.get(r["facet_id"], r["facet_id"])
    return Dataset(catalog, scenarios_from_events(rows, catalog), name="MineXR++ (pre-1.0 ids)")


def remap_response(payload: dict, renames: dict) -> dict:
    out = deepcopy(payload)
    for row in out.get("recommendations") or []:
        if isinstance(row, dict) and row.get("facet_id") in renames:
            row["facet_id"] = renames[row["facet_id"]]
    return out


class Builder:
    def __init__(self):
        self.ds = load_minexrpp()
        self.old = legacy_view(self.ds)
        self.renames = {old: f.facet_id for f in self.ds.catalog for old in f.legacy_ids}
        self.cache = LLMCache(mode="refresh", client=object())
        self.stats = Counter()
        self.problems = []

    def add(self, *, task, legacy_condition, scenario_id, history_old, saved_prompt, method_payload, max_examples, max_facets):
        cond = CONDITION_BY_LEGACY[legacy_condition]
        old_m = LLMSuggester(self.old, None if cond == "zero_shot" else cond, max_examples=max_examples,
                             max_facets_per_tier=max_facets, cache=self.cache)
        new_m = LLMSuggester(self.ds, None if cond == "zero_shot" else cond, max_examples=max_examples,
                             max_facets_per_tier=max_facets, cache=self.cache)
        tiers_old = self.old.scenarios[scenario_id].target_tiers
        tiers_new = self.ds.scenarios[scenario_id].target_tiers
        h_old = None if history_old is None else [PlacedFacet(f, tiers_old.get(f, "")) for f in history_old]
        h_new = None if history_old is None else [
            PlacedFacet(self.renames.get(f, f), tiers_new.get(self.renames.get(f, f), "")) for f in history_old
        ]
        ctx = self.ds.scenarios[scenario_id].context
        try:
            _, old_user = old_m.prompts(ctx, self.old.catalog, h_old, 10)
            system, new_user = new_m.prompts(ctx, self.ds.catalog, h_new, 10)
        except SuggestionUnavailable:
            self.problems.append((task, legacy_condition, scenario_id, "no pool in port but call in paper"))
            return
        if old_user != saved_prompt:
            self.stats["prompt_mismatch"] += 1
            self.problems.append((task, legacy_condition, scenario_id, history_old and len(history_old), "prompt mismatch"))
            return
        self.stats["prompt_verified"] += 1
        request = LLMRequest(MODEL, TEMPERATURE, task, cond, scenario_id, None if history_old is None else len(history_old),
                             system, new_user)
        meta = {"legacy_prompt_sha256": LLMRequest(MODEL, TEMPERATURE, task, cond, scenario_id, None, system, saved_prompt).prompt_sha256,
                "legacy_condition_key": legacy_condition}
        error = str(method_payload.get("error") or "")
        raw = (method_payload.get("raw_result") or {}).get("raw_model_result")
        if error:
            self.cache.put(request, LLMResponse(error=error, provenance="reconstructed_from_parsed", meta=meta))
            self.stats["cached_error"] += 1
            return
        remapped = remap_response(raw, self.renames)
        changed = sorted({r["facet_id"] for r in raw.get("recommendations", []) if r.get("facet_id") in self.renames})
        if changed:
            meta["remapped_facet_ids"] = {o: self.renames[o] for o in changed}
        expected = [self.renames.get(r["facet_id"], r["facet_id"])
                    for r in sorted((method_payload.get("raw_result") or {}).get("recommendations") or [], key=lambda r: r["rank"])]
        got = new_m._catalog(self.ds.catalog)[1].normalize(remapped, 10)
        if got != expected:
            self.stats["prediction_mismatch"] += 1
            self.problems.append((task, legacy_condition, scenario_id, "prediction mismatch", got, expected))
            return
        self.cache.put(request, LLMResponse(text=json.dumps(remapped, ensure_ascii=False), provenance="reconstructed_from_parsed", meta=meta))
        self.stats["cached"] += 1

    def initial(self, path: Path, max_facets: int, conditions):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for s in payload["scenarios"]:
            for legacy_condition, m in s["methods"].items():
                if legacy_condition not in conditions:
                    continue
                if (m.get("raw_result") or {}).get("skipped"):
                    self.stats["skipped_no_examples"] += 1
                    continue
                self.add(task="initial", legacy_condition=legacy_condition, scenario_id=s["scenario_key"], history_old=None,
                         saved_prompt=m["prompt_context"], method_payload=m, max_examples=None, max_facets=max_facets)

    def next(self, path: Path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for s in payload["scenarios"]:
            scenario_id = s["scenario_key"].split("__hitl_")[0]
            for method_key, m in s["methods"].items():
                legacy_condition = method_key.split("__")[0]
                if (m.get("raw_result") or {}).get("skipped") or not m.get("prompt_context"):
                    self.stats["next_no_call"] += 1
                    continue
                history = list((m.get("trace") or {}).get("prior_units") or [])
                self.add(task="next", legacy_condition=legacy_condition, scenario_id=scenario_id, history_old=history,
                         saved_prompt=m["prompt_context"], method_payload=m, max_examples=3, max_facets=0)


def main():
    target = ROOT / "cache" / "llm"
    if target.exists():
        shutil.rmtree(target)
    b = Builder()
    b.initial(INITIAL_ZERO_SHOT, 3, {"static_cold_start"})
    b.initial(INITIAL_FEW_SHOT, 0, set(LEGACY_CONDITION_KEYS.values()) - {"static_cold_start"})
    b.next(NEXT_ALL)
    print(json.dumps(b.stats, indent=1))
    for p in b.problems[:20]:
        print("PROBLEM", p)
    if b.problems:
        sys.exit(1)
    assert catalog_text(b.ds.catalog)


if __name__ == "__main__":
    main()
