# Project website

Static site, no build step. Open `index.html` directly or serve the folder:

```bash
python -m http.server -d site 8000     # then open http://localhost:8000
```

## Pages and sections

| path | contents |
|---|---|
| `index.html` | header with the authors and links (paper, arXiv, code, data, BibTeX), side navigation, three sections, and a citation footer with a copy-BibTeX button. The sections are: MineXR++ facet graphs (Fig. 2 top), MineXR++ contextual layouts (with the functionality suggestion test), and context factor analysis (Fig. 4) |
| `gallery.html` | every facet's mockup panel with its capabilities (hover a capability to find its element) |
| `js/facet-graph.js` | facet graphs; hovering a facet previews its panel, and the button beside it opens the panel with every capability annotated |
| `js/layouts.js` | contextual layouts: one scenario's ground-truth facets, picked with an environment tab and then from that room's layouts grouped by task category, placed by tier in the participant's view (primary in the centre, peripheral in columns on the left and right, ambient in the outermost columns; a single row along the bottom when the view is too narrow); widgets drag with the mouse or move with the arrow keys, and positions are kept per scenario until "Reset layout"; a click opens the panel with the capabilities the participant's widgets exposed |
| `js/factors.js`, `css/factors.css` | context factor analysis (paper §4.1, Fig. 4) for every facet placed in at least 2 layouts: the dominant-factor counts as a bar that filters the rest, a triangle with one dot per facet placed by the share of its user / task / environment lift (sized by layouts, coloured by dominant factor), and a searchable list of each facet's three lifts; hovering shows the panel and lifts, clicking opens the annotated panel |
| `js/nav.js` | side navigation: marks the section in view (a sticky top bar below 1100px); the copy-BibTeX button |
| `js/suggest.js` | functionality suggestion test (initial facet suggestion, paper §3.4) inside contextual layouts: a bar below the view picks one of the 9 methods (off by default; each shows its cost change for the layout), the method's suggestions appear between the view and the bar, linked to the widgets they serve (links follow dragged widgets), the widgets show each outcome, and a step-by-step breakdown follows; also the facet detail dialog used across the page (its panel with each capability annotated, and the facet's place in its app's graph with the path from the app's entry) |
| `js/scenes.js` | first-person line drawings of the 4 environments (slate lines and halftone dots on a blue-white ground, after the "Glasses that understand" explainer); the camera and the objects on the table follow the environment and the raw task (e.g. ordering at the café counter, working out on a mat) |
| `js/mockups.js`, `css/mockups.css` | renders a facet as an XR panel whose elements are exactly its capabilities |
| `mockups/*.json` | one mockup spec per app (format: `mockups/SCHEMA.md`) |

## Generated data (do not edit)

All three need the package installed (`pip install -e ".[embed]"`).

| file | built by | from |
|---|---|---|
| `data/minexrpp.js` | `python scripts/build_site_data.py` | `data/minexrpp/` (facet DB, scenarios, target sets) and the benchmark's context factor analysis (`contextxr/tasks/factor_analysis.py`, `configs/factor_analysis.yaml`) |
| `data/results.js` | `python scripts/build_site_results.py` | the paper's 9 methods replayed from `cache/llm` (about 3 min, no API key) |
| `data/mockups.js` | `python scripts/build_site_mockups.py --strict` | `site/mockups/*.json`, validated against the facet DB; embeds the Lucide icons used (`scripts/vendor/lucide`, ISC) |

Participants are renumbered for display: MineXR has two series, P01–P10 and P002–P022, which are
different people with colliding numbers (P03 vs P003), so the site shows P002–P022 as P11–P31
(`site_user` in `scripts/build_site_data.py`, also applied to the LLM rationales in `data/results.js`).
Scenario ids, the benchmark and its methods keep the original ids.

The factor analysis uses the benchmark's own task aliases and environment spellings, not the
site's 8 task categories, so its numbers match the paper (47 / 14 / 12 / 8 / 20).

The contextual layouts picker groups MineXR's 66 free-text task labels into 8 categories
(`TASK_CATEGORIES` in `scripts/build_site_data.py`) and merges environment spellings into 4 rooms.
This grouping is for browsing on the site only. The benchmark and its methods use the raw labels.
The "evidence" chips in the suggestion test use the same grouping and count other MineXR layouts
(leave-one-out), so they approximate, rather than reproduce, what each method saw in training.

Scene backgrounds are illustrations, not MineXR room scans: raw MineXR media is not part of the
release (DATA_LICENSE), and there is no kitchen scan.
