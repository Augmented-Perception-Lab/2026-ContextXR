"""Tasks, runner, LLM cache and the paper's method configurations (no API key needed)."""

import json
from pathlib import Path

import pytest

from contextxr import evaluate, load_minexrpp
from contextxr.data.loader import load_dataset
from contextxr.methods.base import SuggestionUnavailable, Suggester
from contextxr.methods.llm import LLMSuggester, catalog_text
from contextxr.methods.llm_cache import CacheMiss, LLMCache
from contextxr.methods.popularity import GlobalPopularity
from contextxr.methods.registry import build_method, paper_methods
from contextxr.runner import Results
from contextxr.tasks.common import PlacedFacet

TOY = Path(__file__).parent / "data" / "toy"
TOY_FOLDS = {"S1": 1, "S2": 1, "S3": 2, "S4": 2}


@pytest.fixture(scope="module")
def toy():
    return load_dataset(TOY)


@pytest.fixture(scope="module")
def ds():
    return load_minexrpp()


class Fixed(Suggester):
    name = "fixed"

    def __init__(self, out, fail_on=()):
        self.out, self.fail_on = out, set(fail_on)

    def suggest(self, context, catalog, history=None, k=10):
        if context.user in self.fail_on:
            raise SuggestionUnavailable("no_matching_examples")
        return list(self.out)[:k]


def test_popularity_counts_training_folds_only(toy):
    m = GlobalPopularity()
    m.fit(toy.subset(["S1", "S2"]))  # music.now_playing x1, browse_music x1, recipes.cook_recipe x1
    top = m.suggest(toy.scenarios["S3"].context, toy.catalog, None, k=3)
    assert set(top) == {"music.browse_music", "music.now_playing", "recipes.cook_recipe"}


def test_initial_task_skips_unavailable(toy):
    r = evaluate(Fixed(["recipes.view_recipe"], fail_on={"U2"}), "initial", toy, folds=TOY_FOLDS)
    assert r.summary["n_evaluated"] == 2 and r.summary["skipped"] == {"no_matching_examples": 2}
    rec = {x["scenario_id"]: x for x in r.records}
    assert rec["S3"]["evaluated"] is False and "cost" not in rec["S3"]


def test_next_task_steps_and_proxy(toy):
    r = evaluate(Fixed(["music.now_playing"], fail_on={"U2"}), "next", toy, folds=TOY_FOLDS,
                 orders={"S1": ["recipes.cook_recipe", "music.now_playing"], "S2": ["music.browse_music"],
                         "S3": ["recipes.browse_recipes", "recipes.view_recipe"], "S4": ["music.now_playing"]})
    rec = {x["scenario_id"]: x for x in r.records}
    s1 = rec["S1"]["steps"]
    assert [s["history"] for s in s1] == [[], ["recipes.cook_recipe"]]
    assert s1[1]["hsm"]["partition"]["H"] == ["music.now_playing"]
    s3 = rec["S3"]
    assert s3["cost"]["proxy_steps"] == 2 and s3["cost"]["suggest"] == s3["cost"]["manual"]
    assert s3["retrieval"]["recall"] == 0.0  # no matching examples count as empty suggestions


def test_results_jsonl_roundtrip(toy, tmp_path):
    r = evaluate(Fixed(["music.now_playing"]), "initial", toy, folds=TOY_FOLDS, out=tmp_path / "r.jsonl")
    lines = [json.loads(line) for line in (tmp_path / "r.jsonl").read_text().splitlines()]
    assert [x["type"] for x in lines] == ["run"] + ["scenario"] * 4 + ["summary"]
    assert all(x["benchmark_version"] == "1.0.0" for x in lines)
    back = Results.from_jsonl(tmp_path / "r.jsonl")
    assert back.summary == r.summary and back.records == r.records


def test_history_items_are_facet_ids():
    f = PlacedFacet("music.now_playing", "primary")
    assert f == "music.now_playing" and f.tier == "primary" and isinstance(f, str)


def test_llm_cache_miss_is_loud(ds, tmp_path):
    m = LLMSuggester(ds, None, cache=LLMCache(tmp_path))  # empty cache, replay mode
    s = next(iter(ds))
    with pytest.raises(CacheMiss):
        m.suggest(s.context, ds.catalog, None, 10)


def test_llm_replays_paper_outputs(ds):
    s = ds.scenarios["P04_LivingRoom_Relaxing"]
    zero = LLMSuggester(ds, None).suggest(s.context, ds.catalog, None, 10)
    few = LLMSuggester(ds, "user").suggest(s.context, ds.catalog, None, 10)
    assert len(zero) == 10 and len(few) == 10
    assert "spotify.view_audiobook" in few  # Fig. 5: user-matched examples recover View Audiobook


def test_llm_without_matching_examples(ds):
    s = next(s for s in ds if not any(o.context.user == s.context.user and o.context.task == s.context.task
                                      and o.scenario_id != s.scenario_id for o in ds))
    with pytest.raises(SuggestionUnavailable):
        LLMSuggester(ds, "user+task").suggest(s.context, ds.catalog, None, 10)


def test_catalog_lists_every_facet_once(ds):
    lines = catalog_text(ds.catalog).splitlines()
    assert len(lines) == 273
    assert lines[0].startswith('1. {"facet_id": "gmail.browse_mailbox"')


def test_paper_method_configs(ds):
    names = paper_methods()
    assert len(names) == 9
    m, protocol = build_method("few_shot_llm[task+env]", task="next", dataset=ds)
    assert m.max_examples == 3 and protocol == {"final_step_query": "if_uncovered_capabilities"}
    m, protocol = build_method("few_shot_llm[task+env]", task="initial", dataset=ds)
    assert m.max_examples is None and protocol == {}
