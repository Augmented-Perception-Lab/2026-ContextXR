# Reproducing the paper

`python scripts/reproduce_paper.py` (or `contextxr reproduce`) regenerates Figure 4 and Tables 1–2 from `cache/llm/`, with no API key. `tests/test_reproduce_paper.py` asserts every number within ±0.01 (costs, lifts) and ±0.001 (retrieval metrics).

The table below compares three sources:

- **paper**: the camera-ready values.
- **original**: the paper's research code (`python/` at commit `cb5ca5b` plus its uncommitted working tree), rerun on 2026-10-03 before refactoring. Popularity, relational retrieval and the lift analysis are recomputed. The LLM rows are re-aggregated from the saved paper-run outputs, because the original code has no response cache.
- **1.0.0**: this package.

Recorded original outputs: `tests/data/original_pipeline_outputs.json`.

## Figure 4: dominant context factor

| | paper | original | 1.0.0 |
|---|---|---|---|
| user | 47 | 47 | 47 |
| task | 14 | 14 | 14 |
| environment | 12 | 12 | 12 |
| mixed | 8 | 8 | 8 |
| none | 20 | 20 | 20 |

| facet | lift | paper | original | 1.0.0 |
|---|---|---|---|---|
| duolingo.complete_lesson | U | 18.99 | 18.9871 | 18.9871 |
| duolingo.complete_lesson | T | 0.00 | 0.0000 | 0.0000 |
| duolingo.complete_lesson | E | 0.66 | 0.6575 | 0.6575 |
| books.browse_library | T | 12.91 | 12.9079 | 12.9079 |
| netflix.browse_content | E | 3.94 | 3.9450 | 3.9450 |
| reminders.browse_task_lists | U | 12.66 | 12.6581 | 12.6581 |
| reminders.browse_task_lists | T | 12.91 | 12.9079 | 12.9079 |
| reminders.browse_task_lists | E | 1.31 | 1.3150 | 1.3150 |

The paper prints Netflix E and Reminders E truncated (3.94, 1.31). The code's values are 3.945 and 1.315.

## Table 1: initial facet suggestion

| method | n | cost (paper / original / 1.0.0) | Recall@10 | F1@10 | Hit@10 |
|---|---|---|---|---|---|
| manual access | 109 | 21.20 / 21.2018 / 21.2018 | | | |
| popularity | 109 / 109 / 109 | 19.85 / 19.8486 / 19.8486 | 0.167 / 0.1670 / 0.1670 | 0.132 / 0.1323 / 0.1323 | 0.688 / 0.6881 / 0.6881 |
| relational | 109 / 109 / 109 | 18.39 / 18.3899 / 18.3899 | 0.259 / 0.2594 / 0.2594 | 0.193 / 0.1934 / 0.1934 | 0.798 / 0.7982 / 0.7982 |
| zero_shot_llm | 109 / 109 / 109 | 17.66 / 17.6560 / 17.6560 | 0.228 / 0.2277 / 0.2277 | 0.168 / 0.1683 / 0.1683 | 0.761 / 0.7615 / 0.7615 |
| few_shot_llm[user] | 106 / 106 / 106 | 16.33 / 16.3255 / 16.3255 | 0.338 / 0.3384 / 0.3384 | 0.255 / 0.2551 / 0.2551 | 0.830 / 0.8302 / 0.8302 |
| few_shot_llm[task] | 40 / 40 / 40 | 18.41 / 18.4125 / 18.4125 | 0.274 / 0.2744 / 0.2744 | 0.217 / 0.2175 / 0.2175 | 0.825 / 0.8250 / 0.8250 |
| few_shot_llm[environment] | 108 / 108 / 108 | 17.07 / 17.0694 / 17.0694 | 0.287 / 0.2875 / 0.2875 | 0.206 / 0.2064 / 0.2064 | 0.870 / 0.8704 / 0.8704 |
| few_shot_llm[user+task] | 2 / 2 / 2 | 15.25 / 15.2500 / 15.2500 | 0.464 / 0.4643 / 0.4643 | 0.399 / 0.3987 / 0.3987 | 1.000 / 1.0000 / 1.0000 |
| few_shot_llm[user+env] | 94 / 94 / 94 | 15.53 / 15.5266 / 15.5266 | 0.319 / 0.3191 / 0.3191 | 0.229 / 0.2292 / 0.2292 | 0.862 / 0.8617 / 0.8617 |
| few_shot_llm[task+env] | 47 / 47 / 47 | 19.54 / 19.5426 / 19.5426 | 0.222 / 0.2223 / 0.2223 | 0.178 / 0.1778 / 0.1778 | 0.702 / 0.7021 / 0.7021 |

## Table 2: next facet suggestion

| method | n | cost (paper / original / 1.0.0) | Recall@10 | F1@10 | Hit@10 |
|---|---|---|---|---|---|
| manual access | 109 | 21.19 / 21.1927 / 21.1927 | | | |
| popularity | 109 / 109 / 109 | 18.70 / 18.7018 / 18.7018 | 0.168 / 0.1679 / 0.1679 | 0.089 / 0.0895 / 0.0895 | 0.466 / 0.4660 / 0.4660 |
| relational | 109 / 109 / 109 | 15.70 / 15.7018 / 15.6835 | 0.355 / 0.3554 / 0.3574 | 0.162 / 0.1620 / 0.1633 | 0.687 / 0.6868 / 0.6881 |
| zero_shot_llm | 109 / 109 / 109 | 16.00 / 15.9954 / 15.9954 | 0.205 / 0.2053 / 0.2053 | 0.102 / 0.1017 / 0.1017 | 0.488 / 0.4882 / 0.4882 |
| few_shot_llm[user] | 109 / 109 / 109 | 14.61 / 14.6101 / 14.6101 | 0.285 / 0.2852 / 0.2852 | 0.147 / 0.1472 / 0.1472 | 0.574 / 0.5742 / 0.5742 |
| few_shot_llm[task] | 109 / 109 / 109 | 19.22 / 19.2156 / 19.2156 | 0.079 / 0.0785 / 0.0785 | 0.044 / 0.0438 / 0.0438 | 0.188 / 0.1883 / 0.1883 |
| few_shot_llm[environment] | 109 / 109 / 109 | 15.82 / 15.8211 / 15.8211 | 0.209 / 0.2087 / 0.2087 | 0.104 / 0.1038 / 0.1038 | 0.492 / 0.4917 / 0.4917 |
| few_shot_llm[user+task] | 109 / 109 / 109 | 20.98 / 20.9771 / 20.9771 | 0.007 / 0.0066 / 0.0066 | 0.004 / 0.0042 / 0.0042 | 0.014 / 0.0140 / 0.0140 |
| few_shot_llm[user+env] | 109 / 109 / 109 | 15.83 / 15.8349 / 15.8349 | 0.257 / 0.2572 / 0.2572 | 0.122 / 0.1224 / 0.1224 | 0.494 / 0.4944 / 0.4944 |
| few_shot_llm[task+env] | 109 / 109 / 109 | 19.30 / 19.2982 / 19.2982 | 0.090 / 0.0895 / 0.0895 | 0.046 / 0.0459 / 0.0459 | 0.205 / 0.2051 / 0.2051 |

## Differences

**Original code vs. paper: none.** Rerun today, the original code reproduces every number in Figure 4 and Tables 1–2. The only gap is display rounding in two Figure 4 lifts, noted above.

**1.0.0 vs. original code: one row (Table 2, relational retrieval).**
- **Cause.** The paper's ranker returned lower-cased facet ids. Because the catalog id was `instagram.browse_Explore`, predicting that facet could never be a hit or an adjustment. It also was not excluded or used as history once placed. This affected 3 scenarios.
- **Fix.** Benchmark 1.0.0 renamed the facet `instagram.browse_explore`, which removes the mismatch.
- **Effect.** Cost changes from 15.70 to 15.68 and Recall@10 from 0.355 to 0.357. F1@10 and Hit@10 change by 0.001.
- **Check.** With the old id and behaviour, the 1.0.0 code gives exactly the paper's 15.7018 / 0.3554 / 0.1620 / 0.6868.
- **Regression test.** The test pins the 1.0.0 values for this row (`V1_CHANGES` in `contextxr/reproduce.py`).

## Protocol details the numbers depend on

These details are not spelled out in the paper. They are implemented as documented options whose defaults reproduce the tables.

- **Cost model** (`configs/cost_default.yaml`, `contextxr/metrics/`). Opening the menu costs 0. App scan costs `ceil(position/20)` per target. Facet navigation counts the facets visited from Open Section, including Open Section itself. Suggestion scan costs 0.5 per target sought. Adjustment costs 1 per hop on the undirected facet graph. In initial facet suggestion, an adjustment is used only if it is no more expensive than manual access, and each suggestion serves at most one target.
- **Next facet suggestion.**
  - Targets are revealed in a fixed seeded order (`configs/splits/next_order_seed42.json`).
  - A step where few-shot prompting has no matching example is costed at manual cost and scored as an empty list. A failed LLM response is costed at manual cost and left out of the retrieval averages.
  - The LLM runs also queried the model after the last placement (`final_step_query`).
  - c_app_scan is charged only for apps the participant used in that scenario (`app_scan_scope`).
- **Few-shot examples.** Initial facet suggestion used every matching scenario. The next facet runs used at most 3 (`configs/methods/llm_few_shot.yaml`).
- **Context factor analysis.** Raw task labels are merged with the alias table in `configs/factor_analysis.yaml` before comparing contexts.
