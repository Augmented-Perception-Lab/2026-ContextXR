# ContextXR

**ContextXR** is a benchmarking framework for context-aware XR interfaces (UIST '26). It represents an app's functionality as **functional facets**: groups of capabilities that serve one user intent, connected in a per-app facet graph. It ships **MineXR++**, a facet-annotated version of the MineXR dataset: 42 apps, 273 facets, 1,007 capabilities, and 109 scenarios from 31 participants. It defines three tasks: **context factor analysis**, **initial facet suggestion**, and **next facet suggestion**. Methods are scored by a simulated **navigation & search cost** (the effort to reach the functionality a user needs, compared with manual access), alongside Recall@10, F1@10 and Hit@10. The package reproduces every number in the paper from a cache of the LLM outputs, with no API key.

Paper: [ACM DL](https://doi.org/10.1145/3830398.3830675) · [arXiv](https://arxiv.org/abs/2609.30466) · Project page: [augmented-perception.org](https://augmented-perception.org/publications/2026-contextXR) · Interactive site: [`site/`](site/)

## Install

Requires Python ≥ 3.10.

```bash
git clone https://github.com/Augmented-Perception-Lab/2026-ContextXR.git contextxr && cd contextxr
pip install -e ".[embed]"     # [embed]: sentence-transformers, for relational retrieval and ContextNormalizer
```

| extra | contents | needed for |
|---|---|---|
| (base) | numpy, jsonschema, pyyaml | data, cost model, popularity, LLM methods replayed from cache, validation |
| `[embed]` | sentence-transformers, scikit-learn | relational retrieval, `ContextNormalizer` |
| `[llm]` | google-genai | live LLM calls (`--live`; reads `GOOGLE_API_KEY` or `GEMINI_API_KEY`) |
| `[dev]` | pytest, nbmake, ruff | tests and notebooks |

## Quickstart

```python
from contextxr import evaluate, load_minexrpp
from contextxr.methods import RelationalRetrieval

ds = load_minexrpp()                                     # MineXR++ (benchmark 1.0.0)
results = evaluate(RelationalRetrieval(), "initial", ds)  # paper's 5 CV folds, top-10 suggestions
s = results.summary
print(f"{s['manual_cost']:.2f} -> {s['suggest_cost']:.2f}")  # 21.20 -> 18.39 (-13.3%)
print(results.records[0]["hsm"]["partition"])             # hits / same-app adjustments / misses
results.to_jsonl("runs/relational_initial.jsonl")         # per-scenario log (docs/results_format.md)
```

Command line:

```bash
contextxr methods                                         # list the paper's methods
contextxr run --task initial --method "few_shot_llm[user]" --out runs/fs_user.jsonl
contextxr run --task next --method relational
contextxr run --task factors
contextxr validate path/to/your_dataset                   # facet_db.json + events.csv
contextxr reproduce                                       # Figure 4 + Tables 1-2, from cache
```

The notebooks in [`examples/`](examples/) cover each use case. The most relevant for new methods is [`03_custom_method`](examples/03_custom_method.ipynb).

## Reproducing the paper

`contextxr reproduce` (or `python scripts/reproduce_paper.py`) regenerates every number in about 3 minutes. Few-shot LLM rows are evaluated only on scenarios with matching examples (n). Costs are mean navigation & search cost per scenario; the reduction is relative to manual access on the same scenarios. Values are shown as printed in the paper. The reproduction matches them within ±0.01 (costs) and ±0.001 (metrics).

| Initial facet suggestion (Table 1) | n | cost | Recall@10 | F1@10 | Hit@10 |
|---|---:|---:|---:|---:|---:|
| Manual access | 109 | 21.20 | | | |
| Global popularity | 109 | 19.85 (−6.4%) | 0.167 | 0.132 | 0.688 |
| Relational retrieval | 109 | 18.39 (−13.3%) | 0.259 | 0.193 | 0.798 |
| Zero-shot LLM | 109 | 17.66 (−16.7%) | 0.228 | 0.168 | 0.761 |
| Few-shot LLM, User | 106 | 16.33 (−22.6%) | 0.338 | 0.255 | 0.830 |
| Few-shot LLM, Task | 40 | 18.41 (−15.9%) | 0.274 | 0.217 | 0.825 |
| Few-shot LLM, Environment | 108 | 17.07 (−18.8%) | 0.287 | 0.206 | 0.870 |
| Few-shot LLM, User+Task | 2 | 15.25 (−30.7%) | 0.464 | 0.399 | 1.000 |
| Few-shot LLM, User+Env | 94 | 15.53 (−22.7%) | 0.319 | 0.229 | 0.862 |
| Few-shot LLM, Task+Env | 47 | 19.54 (−12.6%) | 0.222 | 0.178 | 0.702 |

| Next facet suggestion (Table 2) | cost | Recall@10 | F1@10 | Hit@10 |
|---|---:|---:|---:|---:|
| Manual access | 21.19 | | | |
| Global popularity | 18.70 (−11.7%) | 0.168 | 0.089 | 0.466 |
| Relational retrieval † | 15.68 (−26.0%) | 0.357 | 0.163 | 0.688 |
| Zero-shot LLM | 16.00 (−24.5%) | 0.205 | 0.102 | 0.488 |
| Few-shot LLM, User | 14.61 (−31.1%) | 0.285 | 0.147 | 0.574 |
| Few-shot LLM, Task | 19.22 (−9.3%) | 0.079 | 0.044 | 0.188 |
| Few-shot LLM, Environment | 15.82 (−25.3%) | 0.209 | 0.104 | 0.492 |
| Few-shot LLM, User+Task | 20.98 (−1.0%) | 0.007 | 0.004 | 0.014 |
| Few-shot LLM, User+Env | 15.83 (−25.3%) | 0.257 | 0.122 | 0.494 |
| Few-shot LLM, Task+Env | 19.30 (−8.9%) | 0.090 | 0.046 | 0.205 |

**Context factor analysis (Fig. 4).** Of 101 facets, 47 are user-dominant, 14 task-dominant, 12 environment-dominant, 8 mixed, and 20 show no lift.

† **One change from the paper.** Benchmark 1.0.0 fixes a facet-id case mismatch (`instagram.browse_Explore`) that the paper's run could never match. This changes the paper's 15.70 / 0.355 / 0.162 / 0.687 to the values above. All other numbers equal the paper. See [`docs/reproduction.md`](docs/reproduction.md) for the full comparison with the original code and the protocol details.

## Navigation & search cost: default parameters

`configs/cost_default.yaml` (paper §3.4.1). Each target facet is an exact **hit**, a same-app **adjustment** (a surfaced facet of the same app serves as entry point), or a **miss** (reached manually through the app list).

| term | default | meaning |
|---|---|---|
| c_open_menu | 0 | opening the app list, paid once if any target is a miss |
| c_app_scan(f) | ⌈position/20⌉ × 1 | finding f's app: apps are ordered by usage in MineXR++, in pages of 20 |
| c_facet_nav(f) | facets on path × 1 | navigating from the app's Open Section to f, counting Open Section |
| c_suggest_scan | 0.5 per target | scanning the top-10 suggestions for a target |
| c_adjust(f) | hops × 1 | moving from the surfaced same-app facet to f, ignoring edge direction |

- **Manual access:** C_manual = c_open_menu + Σ (c_app_scan + c_facet_nav).
- **Assisted access:** C_suggest = c_suggest_scan + Σ_A c_adjust + Σ_M (c_app_scan + c_facet_nav) + c_open_menu if any miss.
- **Initial facet suggestion.** Each suggestion serves at most one target. An adjustment is used only if it is no more expensive than manual access.

To change the costs, subclass `CostModel` and pass `cost_model=` to `evaluate`. See [`examples/06_custom_cost_model.ipynb`](examples/06_custom_cost_model.ipynb).

## Adding a method

```python
from contextxr import evaluate
from contextxr.methods import Suggester

class MyMethod(Suggester):
    name = "my_method"

    def fit(self, train):            # called once per CV fold with training scenarios only (optional)
        ...

    def suggest(self, context, catalog, history=None, k=10):
        # context: Context(user, task, environment); catalog: all apps/facets/graphs
        # history: None (initial suggestion) or facets already placed (next suggestion)
        return [...]                 # up to k facet ids, best first

print(evaluate(MyMethod(), "initial").summary)
print(evaluate(MyMethod(), "next").summary)
```

- **Unavailable suggestions.** If your method cannot suggest for a context, raise `SuggestionUnavailable`. The scenario is then skipped in initial facet suggestion, and costed as manual access in next facet suggestion.
- **CLI.** To make the method available to `contextxr run`, add a YAML file to `configs/methods/`.

## Repository

| path | contents |
|---|---|
| `contextxr/data` | schema (`App`, `Facet`, `FacetGraph`, `Context`, `Scenario`, `FacetCatalog`), loader, validation |
| `contextxr/tasks` | context factor analysis, initial and next facet suggestion |
| `contextxr/methods` | `Suggester`, global popularity, relational retrieval, LLM (prompts in `prompts/`, Appendix A) |
| `contextxr/metrics` | cost model, navigation & search cost (H/A/M), retrieval metrics |
| `contextxr/normalize.py` | `ContextNormalizer`: free-form sensed labels → benchmark vocabulary |
| `data/minexrpp` | MineXR++ (`docs/data_format.md`) |
| `configs` | cost model, method configs, the paper's CV folds and step orders |
| `cache/llm` | the paper's LLM prompt/response pairs, replayed by default |
| `docs` | data format, results format, reproduction notes |

## Citation

```bibtex
@inproceedings{cho2026contextxr,
  title     = {A Benchmarking Framework for Context-aware XR Interfaces},
  author    = {Cho, Hyunsung and Yun, Sarah Yewon and Sun, Nancy Ruonan and Lafreniere, Ben and Parent, Mark and
               Todi, Kashyap and Jonker, Tanya R. and Benko, Hrvoje and Wu, Tongshuang and Lindlbauer, David},
  booktitle = {Proceedings of the 39th Annual ACM Symposium on User Interface Software and Technology},
  series    = {UIST '26},
  year      = {2026},
  numpages  = {16},
  location  = {Detroit, MI, USA},
  publisher = {Association for Computing Machinery},
  address   = {New York, NY, USA},
  doi       = {10.1145/3830398.3830675}
}
```

## License

- **Code:** Apache-2.0 ([`LICENSE`](LICENSE)).
- **MineXR++ data, splits and cached LLM outputs:** CC BY 4.0 ([`DATA_LICENSE`](DATA_LICENSE)).
