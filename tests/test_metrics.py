"""Cost model, H/A/M partition and retrieval metrics on a hand-checkable toy dataset.

Toy facet graphs (tests/data/toy):
    music:   open_section -> browse_music -> now_playing,  open_section -> now_playing
    recipes: open_section -> browse_recipes -> view_recipe -> cook_recipe
Both apps are on the first page of the app list, so c_app_scan = 1 for every facet.
c_facet_nav counts visited facets incl. Open Section: now_playing 2, browse_recipes 2,
view_recipe 3, cook_recipe 4.
"""

from pathlib import Path

import pytest

from contextxr.data.loader import load_dataset
from contextxr.metrics.cost_model import CostParams, DefaultCostModel
from contextxr.metrics.nav_search_cost import score_episode, score_step
from contextxr.metrics.retrieval import set_metrics, top_k_metrics

TOY = Path(__file__).parent / "data" / "toy"


@pytest.fixture(scope="module")
def toy():
    return load_dataset(TOY)


def model(toy, **overrides):
    return DefaultCostModel(CostParams(**overrides)).bind(toy)


def test_step_costs(toy):
    cm = model(toy)
    cat = toy.catalog
    f = cat.facet
    assert cm.app_scan(f("music.now_playing")) == 1.0
    assert cm.facet_nav(f("music.open_section"), cat.graph("music")) == 1.0
    assert cm.facet_nav(f("music.now_playing"), cat.graph("music")) == 2.0
    assert cm.facet_nav(f("recipes.cook_recipe"), cat.graph("recipes")) == 4.0
    # adjustment ignores edge direction: cook_recipe -> browse_recipes is 2 hops back up the chain
    assert cm.adjust(f("recipes.browse_recipes"), f("recipes.cook_recipe"), cat.graph("recipes")) == 2.0
    assert cm.suggest_scan(["a", "b"], n_targets=3) == 1.5


def test_app_pages(toy):
    cm = model(toy, app_page_size=1)  # music (more placements, then name) is first, recipes second
    assert cm.app_scan(toy.catalog.facet("music.now_playing")) == 1.0
    assert cm.app_scan(toy.catalog.facet("recipes.view_recipe")) == 2.0


def test_partition_and_totals(toy):
    targets = ["music.now_playing", "recipes.cook_recipe"]
    ep = score_episode(targets, ["recipes.view_recipe"], toy.catalog, model(toy))
    assert (ep.hits, ep.adjustments, ep.misses) == ([], ["recipes.cook_recipe"], ["music.now_playing"])
    assert ep.manual_cost == (1 + 2) + (1 + 4)
    assert ep.suggest_cost == 0.5 * 2 + 1 + (1 + 2)  # scan + adjust + miss


def test_open_menu_only_with_misses(toy):
    targets = ["music.now_playing", "recipes.cook_recipe"]
    cm = model(toy, open_menu=2.0)
    with_miss = score_episode(targets, ["recipes.view_recipe"], toy.catalog, cm)
    no_miss = score_episode(targets, ["recipes.view_recipe", "music.now_playing"], toy.catalog, cm)
    assert with_miss.manual_cost == 2.0 + 8.0
    assert with_miss.suggest_cost == 1.0 + 1.0 + 3.0 + 2.0
    assert no_miss.misses == [] and no_miss.suggest_cost == 1.0 + 1.0


def test_initial_adjustment_only_if_not_costlier_than_manual(toy):
    cm = model(toy, adjust_per_hop=10.0)  # adjusting view_recipe -> cook_recipe costs 10 > manual 5
    ep = score_episode(["recipes.cook_recipe"], ["recipes.view_recipe"], toy.catalog, cm)
    assert ep.misses == ["recipes.cook_recipe"]
    assert ep.targets[0].same_app_suggestion_visible


def test_next_step_adjustment_is_uncapped(toy):
    cm = model(toy, adjust_per_hop=10.0)
    ep = score_step("recipes.cook_recipe", ["recipes.view_recipe"], toy.catalog, cm)
    assert ep.adjustments == ["recipes.cook_recipe"] and ep.suggest_cost == 0.5 + 10.0


def test_each_suggestion_serves_one_target(toy):
    targets = ["recipes.browse_recipes", "recipes.view_recipe"]
    ep = score_episode(targets, ["recipes.cook_recipe"], toy.catalog, model(toy))
    # cook -> view_recipe saves 3 (1 hop vs 4); cook -> browse saves 1 (2 hops vs 3): the optimum uses the former
    assert ep.adjustments == ["recipes.view_recipe"] and ep.misses == ["recipes.browse_recipes"]
    assert ep.suggest_cost == 0.5 * 2 + 1 + 3


def test_exact_hit_and_visibility_limit(toy):
    many = [f"x.{i}" for i in range(10)] + ["music.now_playing"]
    assert score_episode(["music.now_playing"], many, toy.catalog, model(toy)).misses == ["music.now_playing"]
    assert score_episode(["music.now_playing"], many[1:], toy.catalog, model(toy)).hits == ["music.now_playing"]


def test_proxy_step_costs_manual(toy):
    ep = score_step("recipes.cook_recipe", [], toy.catalog, model(toy), proxy=True)
    assert ep.suggest_cost == ep.manual_cost == 5.0


def test_app_scan_scope(toy):
    ep = score_step("music.now_playing", [], toy.catalog, model(toy), app_scan_apps={"recipes"})
    assert ep.manual_cost == 2.0  # music not among the scenario's apps: locating it costs 0


def test_retrieval_metrics():
    m = top_k_metrics(["a", "b", "a", "c"], {"b", "c", "d", "e"}, k=10)
    assert m["precision"] == pytest.approx(2 / 10)
    assert m["recall"] == pytest.approx(2 / 4)
    assert m["hit"] == 1.0 and m["mrr"] == pytest.approx(1 / 2)
    assert top_k_metrics(["a"], set()) is None
    s = set_metrics(["a", "b", "c"], ["c", "d"])
    assert (s["precision"], s["recall"], s["f1"], s["hit"]) == (0.3333, 0.5, 0.4, 1.0)
