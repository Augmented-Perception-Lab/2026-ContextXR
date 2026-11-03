# Results format (`contextxr.results`, format version 1.0)

(Values in the examples below are illustrative.)

`contextxr.evaluate(...)` returns a `Results` object. `Results.to_jsonl(path)` writes it as JSON Lines (one JSON object per line) and `Results.from_jsonl(path)` reads it back. The format is stable within format version 1.x: fields may be added, but none are removed or renamed. Every line carries `benchmark_version`.

A file contains three kinds of line, in this order:

1. one `run` line;
2. one `scenario` line per scenario, sorted by `scenario_id`;
3. one `summary` line.

## `run`

```json
{"type": "run", "format": "contextxr.results", "format_version": "1.0",
 "benchmark_version": "1.0.0", "package_version": "1.0.0",
 "dataset": {"name": "MineXR++", "version": "1.0.0", "n_scenarios": 109},
 "method": {"name": "relational", "class": "contextxr.methods.relational.RelationalRetrieval", "use_history": true},
 "protocol": {"task": "initial", "k": 10, "visible_limit": 10, "folds": "configs/splits/cv5_seed42.json"},
 "cost_model": {"name": "default", "open_menu": 0.0, "app_page_size": 20, "...": "..."},
 "created_at": "2026-10-03T20:00:00+00:00", "python": "3.12.7"}
```

- **`method`:** includes `model`, `temperature`, `condition` and `max_examples` when the method has them.
- **`protocol`:** for next facet suggestion, also contains `unmatched`, `app_scan_scope`, `final_step_query` and `orders`. See `contextxr/tasks/next_suggestion.py`.

## `scenario`: initial facet suggestion

```json
{"type": "scenario", "benchmark_version": "1.0.0",
 "scenario_id": "P04_LivingRoom_Relaxing", "fold": 3,
 "context": {"user": "P04", "task": "Relaxing", "environment": "LivingRoom"},
 "targets": ["amazon.open_section", "spotify.view_audiobook", "..."],
 "evaluated": true,
 "suggestions": ["spotify.view_now_playing", "..."],
 "cost": {"manual": 25.0, "suggest": 19.5,
          "manual_open_menu": 0.0, "manual_app_scan": 11.0, "manual_facet_nav": 14.0, "manual_total": 25.0,
          "suggest_scan": 4.5, "suggest_adjust": 2.0, "suggest_miss_app_scan": 6.0,
          "suggest_miss_facet_nav": 7.0, "suggest_open_menu": 0.0, "suggest_total": 19.5},
 "hsm": {"partition": {"H": ["spotify.view_now_playing"], "A": ["uber_eats.view_store"], "M": ["..."]},
         "targets": [{"facet_id": "uber_eats.view_store", "outcome": "A", "source_facet_id": "uber_eats.open_section",
                      "source_rank": 4, "hops": 1, "app_scan": 1.0, "facet_nav": 2.0, "adjust": 1.0,
                      "same_app_suggestion_visible": false}, "..."],
         "unreachable_targets": [], "proxy": false, "terms": {"...": "same as cost"}},
 "retrieval": {"precision": 0.1, "recall": 0.111, "f1": 0.105, "hit": 1.0, "mrr": 1.0}}
```

- **`targets`** is the target set Y_q, sorted.
- **`suggestions`** is exactly what the method returned, best first. Only the first 10 distinct suggestions are scored.
- **`cost.manual`** is C_manual and **`cost.suggest`** is C_suggest (paper §3.4.1). The remaining `cost` keys are their terms.
- **`hsm.partition`** gives the exact hits (H), same-app adjustments (A) and misses (M).
- **`hsm.targets[]`** shows, for each target, how it was reached and its cost terms. For A it names the suggestion that served as the entry point. `same_app_suggestion_visible` marks misses for which a same-app suggestion existed but was not cheaper than manual access.
- **Unevaluated scenarios.** If the method could not suggest for the scenario (for example, few-shot prompting with no matching example, or a failed LLM call), the line has `"evaluated": false`, `"skip_reason"` (`"no_matching_examples"`, `"llm_error"`, `"llm_parse_error"`, …) and `"skip_detail"`, and no `suggestions`, `cost`, `hsm` or `retrieval`.

## `scenario`: next facet suggestion

These lines have the same top-level fields, plus `order` and `steps`:

```json
{"type": "scenario", "scenario_id": "...", "fold": 1, "context": {"...": "..."}, "targets": ["..."],
 "order": ["notes.view_note", "spotify.view_now_playing", "..."],
 "evaluated": true,
 "cost": {"manual": 21.0, "suggest": 14.5, "proxy_steps": 0},
 "retrieval": {"recall": 0.31, "f1": 0.15, "hit": 0.6, "precision": 0.1},
 "steps": [
   {"t": 0, "history": [], "target": "notes.view_note",
    "suggestions": ["..."],
    "retrieval": {"precision": 0.1, "recall": 0.2, "f1": 0.1333, "hit": 1.0},
    "cost": {"manual": 3.0, "suggest": 0.5, "...": "terms as above"},
    "hsm": {"partition": {"H": ["notes.view_note"], "A": [], "M": []}, "targets": ["..."], "proxy": false}},
   {"t": 1, "history": ["notes.view_note"], "target": "...", "...": "..."}
 ]}
```

- **`order`** is the order in which targets are revealed. At step `t`, `history = order[:t]` and `target = order[t]`.
- **Scenario totals.** `cost.manual` and `cost.suggest` are sums over the scenario's steps. `retrieval` is the mean over the scenario's steps that have retrieval metrics.
- **Step `retrieval`** is computed against the targets not yet placed, rounded to 4 decimals. Precision divides by the number of suggestions.
- **Failed steps.** A step where the method could not suggest has `"unavailable"` (the reason) and `"unavailable_detail"`. With `unmatched="manual_proxy"`, it is costed at manual cost (`hsm.proxy: true`). Its retrieval is 0 for `no_matching_examples` and `null` for method failures.
- **Final step.** If the method is also queried after the last placement (`final_step_query`), the last step has `"target": null` and cost 0.

## `summary`

```json
{"type": "summary", "benchmark_version": "1.0.0", "n_scenarios": 109, "n_evaluated": 106,
 "manual_cost": 21.09, "suggest_cost": 16.33, "cost_reduction_pct": -22.6,
 "recall": 0.338, "f1": 0.255, "hit": 0.830, "precision": 0.2, "mrr": 0.5,
 "skipped": {"no_matching_examples": 3}}
```

- **Averages.** Means are taken over evaluated scenarios. `manual_cost` is averaged over the same scenarios as `suggest_cost`, so the reduction compares like with like (as in Tables 1 and 2).
- **Next facet** has no `mrr`.

## Context factor analysis

`contextxr run --task factors` writes:

- one `run` line;
- one `facet` line per facet: `facet_id`, `label`, `occurrences`, `lift_user`, `lift_task`, `lift_environment`, `top_dimension`, `dominance_ratio` (`null` if infinite), and `dominant` (`user` | `task` | `environment` | `mixed` | `none`);
- one `summary` line with `dominant_counts`.
