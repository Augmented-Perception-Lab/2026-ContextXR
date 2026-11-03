"""Phase 1: data layer — format, validation, splits, and equivalence with the reference pipeline."""

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from contextxr.data.loader import load_dataset, load_folds, load_minexrpp, load_next_orders
from contextxr.data.validate import validate_dataset

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / "tests/data/legacy_reference.json").read_text())


@pytest.fixture(scope="module")
def ds():
    return load_minexrpp()


# --- Paper §3.2 counts -------------------------------------------------------------


def test_paper_counts(ds):
    assert len(ds.catalog.apps) == 42
    assert len(ds.catalog) == 273
    assert len(ds.catalog.capability_names()) == 1007  # distinct capability names
    assert len(ds) == 109
    assert len(ds.participants()) == 31


def test_placed_facet_count_matches_paper_definition(ds):
    """The paper's "101 facets placed" = facets assigned to widgets in >= 2 scenarios (lift analysis, min_occurrences=2)."""
    occ = Counter(f for s in ds for f in {w.facet_id for w in s.widgets if w.facet_id})
    assert sum(1 for n in occ.values() if n >= 2) == 101


# --- Equivalence with the reference (legacy) pipeline -----------------------------


def test_targets_match_reference(ds):
    mine = {sid: s.target_tiers for sid, s in ds.scenarios.items()}
    assert mine == REFERENCE["targets"]
    assert sum(len(t) for t in mine.values()) == 731


def test_contexts_match_reference(ds):
    for sid, (user, task, env) in REFERENCE["contexts"].items():
        c = ds.scenarios[sid].context
        assert (c.user, c.task, c.environment) == (user, task, env)


def test_entry_paths_match_reference(ds):
    for fid, n_nodes in REFERENCE["entry_path_nodes"].items():
        path = ds.catalog.graph_of(fid).path_from_entry(fid)
        assert (None if path is None else len(path)) == n_nodes, fid


def test_training_events(ds):
    assert sum(1 for w in ds.widgets() if w.facet_id) == REFERENCE["training_events"] == 680
    assert len(ds.widgets()) == 682


# --- Splits --------------------------------------------------------------------------


def test_folds_cover_all_scenarios(ds):
    folds = load_folds()
    assert set(folds) == set(ds.scenarios)
    assert sorted(Counter(folds.values()).values()) == [21, 22, 22, 22, 22]


def test_next_orders_are_permutations_of_targets(ds):
    orders = load_next_orders()
    assert set(orders) == set(ds.scenarios)
    for sid, order in orders.items():
        assert sorted(order) == sorted(ds.scenarios[sid].target_ids)


# --- Validation ----------------------------------------------------------------------


def test_minexrpp_validates():
    report = validate_dataset(ROOT / "data/minexrpp")
    assert report.ok, str(report)


def _copy_dataset(tmp_path):
    for name in ("facet_db.json", "events.csv"):
        shutil.copy(ROOT / "data/minexrpp" / name, tmp_path / name)
    return tmp_path


def test_validation_reports_bad_edge(tmp_path):
    d = _copy_dataset(tmp_path)
    db = json.loads((d / "facet_db.json").read_text())
    db["edges"].append({"source": "spotify.open_section", "target": "gmail.search_mail", "capability": "open_search_mail"})
    (d / "facet_db.json").write_text(json.dumps(db))
    report = validate_dataset(d)
    assert not report.ok
    assert any("same app" in e for e in report.errors)
    assert any("not a capability of the source facet" in e for e in report.errors)


def test_validation_reports_unknown_facet_and_inconsistent_context(tmp_path):
    d = _copy_dataset(tmp_path)
    lines = (d / "events.csv").read_text().splitlines()
    lines[1] = lines[1].replace("spotify.view_now_playing", "spotify.not_a_facet", 1)
    lines[2] = lines[2].replace(",ChatWithFriends,", ",SomethingElse,", 1)
    (d / "events.csv").write_text("\n".join(lines) + "\n")
    report = validate_dataset(d)
    assert any("unknown facet_id 'spotify.not_a_facet'" in e for e in report.errors)
    assert any("inconsistent context" in e for e in report.errors)


def test_validation_reports_missing_files(tmp_path):
    report = validate_dataset(tmp_path)
    assert not report.ok and any("missing file" in e for e in report.errors)


def test_load_dataset_roundtrip(tmp_path):
    d = _copy_dataset(tmp_path)
    assert len(load_dataset(d)) == 109


# --- 1.0.0 facet-ID renames -------------------------------------------------------


def test_every_edge_names_its_target_exactly(ds):
    assert len(ds.catalog.edges) == 351
    for edge in ds.catalog.edges:
        assert edge.resolution == "exact"
        assert f"{ds.catalog.app_of(edge.source)}.{edge.capability[len('open_'):]}" == edge.target


def test_legacy_ids_map_to_renamed_facets(ds):
    renames = REFERENCE["facet_renames"]
    assert len(renames) == 10
    for old, new in renames.items():
        assert old not in ds.catalog
        assert ds.catalog.canonical_id(old) == new
        assert old in ds.catalog.facet(new).legacy_ids
