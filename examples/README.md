# Examples

Each notebook is short, runs from the LLM cache without an API key, and points to the relevant paper section. Install with `pip install -e ".[embed,dev]"`.

| notebook | what it shows |
|---|---|
| `01_explore_dataset` | MineXR++: apps, facets, capabilities, a facet graph, one participant's contexts |
| `02_evaluate_baseline` | relational retrieval on initial facet suggestion: cost reduction, retrieval metrics, one scenario's H/A/M breakdown |
| `03_custom_method` | **a new method in ~20 lines, compared against every paper baseline in one table** |
| `04_next_facet` | next facet suggestion: using `history` |
| `05_your_own_sensing` | map free-form sensed labels to the benchmark vocabulary with `ContextNormalizer`, then evaluate |
| `06_custom_cost_model` | subclass the cost model and see method rankings change |
| `07_bring_your_own_dataset` | validate and evaluate a tiny dataset in the ContextXR format |

Only the final result tables are stored with outputs. Run all of them with `pytest tests/test_notebooks.py` or `pytest --nbmake examples/`.
