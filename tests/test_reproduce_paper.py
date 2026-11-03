"""Acceptance test: the paper's Figure 4, Table 1 and Table 2, regenerated from cache/llm/.

Tolerances: costs ±0.01, retrieval metrics ±0.001, lifts ±0.01 (contextxr/reproduce.py).
Needs the [embed] extra (relational retrieval) but no API key. Takes a few minutes.
"""

import pytest

pytest.importorskip("sentence_transformers")

from contextxr.data.loader import load_minexrpp  # noqa: E402
from contextxr.methods.registry import paper_methods  # noqa: E402
from contextxr.reproduce import V1_CHANGES, reproduce_figure4, reproduce_table  # noqa: E402


@pytest.fixture(scope="module")
def ds():
    return load_minexrpp()


def _assert_ok(checks):
    bad = [c for c in checks if not c["ok"]]
    assert not bad, "\n".join(f"{c['table']} {c['method']} {c['metric']}: expected {c['expected']}, got {c['got']}" for c in bad)


def test_figure4(ds):
    _assert_ok(reproduce_figure4(ds))


@pytest.mark.parametrize("method", paper_methods())
def test_table1(ds, method):
    _assert_ok(reproduce_table("initial", ds, methods=[method]))


@pytest.mark.parametrize("method", paper_methods())
def test_table2(ds, method):
    _assert_ok(reproduce_table("next", ds, methods=[method]))


def test_only_documented_change():
    assert list(V1_CHANGES) == [("next", "relational")]
