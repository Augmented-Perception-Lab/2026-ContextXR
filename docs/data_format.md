# ContextXR data format (v1.0)

A dataset is a directory containing two files. Check one with `contextxr validate PATH` (or `python -m contextxr.data.validate PATH`). The JSON Schemas live in `contextxr/data/schemas/`.

## `facet_db.json`: apps, facets, capabilities, facet graph (paper §3.1)

```json
{
  "format": "contextxr.facet_db",
  "format_version": "1.0",
  "benchmark_version": "1.0.0",
  "name": "MineXR++",
  "apps":   [{"app_id": "recipes", "app_name": "Recipes", "app_domain": "food",
              "entry_facet_id": "recipes.open_section", "capabilities": ["view_ingredients", "open_cook_recipe", "..."]}],
  "facets": [{"facet_id": "recipes.view_recipe", "app_id": "recipes", "name": "View Recipe",
              "description": "...", "capabilities": ["view_ingredients", "open_cook_recipe", "..."]}],
  "edges":  [{"source": "recipes.view_recipe", "target": "recipes.cook_recipe",
              "capability": "open_cook_recipe", "resolution": "exact"}]
}
```

**Apps and facets**
- `facet_id` is `<app_id>.<facet_suffix>`.
- Each app has an entry facet (`<app_id>.open_section`, the *Open Section* node in Fig. 2): the app's icon or navigation hub. Manual navigation starts there.

**Capabilities**
- Capability names are scoped to their app. The paper's count of 1,007 capabilities is the number of distinct names across apps; there are 1,189 (app, capability) pairs.
- A capability may appear in more than one facet of the same app.

**Edges**
- Edges form the directed facet graph. There is one edge for each navigational capability `open_<facet>` of a source facet.
- The edge list is stored explicitly. In MineXR++ every `open_<x>` capability names its target facet exactly (`<app_id>.<x>`), and `resolution` is `"exact"` for all 351 edges.
- The validator warns about any navigational capability that has no edge.

## `events.csv`: placed elements and their contexts (paper §3.2, Fig. 3)

There is one row per element (widget) a participant placed in a scenario. Row order is significant (see below).

| column | meaning |
|---|---|
| `scenario_id` | one participant's layout for one task in one environment |
| `participant_id`, `task`, `environment` | the context q = (u, t, e), stored as raw labels. They must be identical across a scenario's rows. |
| `widget_id` | unique within a scenario |
| `app_id`, `facet_id` | the single facet this element was resolved to. Empty if unresolved. These are the *events* that count-based methods (popularity, relational retrieval) train on. |
| `capabilities` | JSON object `{"<app_id>.<capability>": "primary" \| "peripheral" \| "ambient"}`: the capabilities the element exposes, with their relevance tier |
| `widget_desc`, `screen_desc` | free-text descriptions (optional) |

### Target facet set Y_q

The target set for a scenario is derived from the capabilities of its rows (`contextxr.data.loader.derive_targets`):

1. Merge the rows' capability maps in file order. A later row overrides an earlier tier for the same capability.
2. Assign each capability to its facet:
   - A capability that belongs to exactly one facet of its app goes to that facet.
   - A navigational capability shared by several facets goes to the app's entry facet, if that is one of them.
   - Any other shared capability, or one not in the facet DB, is ignored.
3. Give each facet the highest tier among its capabilities.

For MineXR++ this gives 731 targets over 109 scenarios. A scenario's targets can include facets that were not any row's `facet_id`, because elements often expose several facets.

## Splits and protocol files (`configs/splits/`)

- `cv5_seed42.json`: scenario → fold (1–5). These are the exact folds used in the paper for global popularity and relational retrieval. The runner reads them; it does not regenerate them.
- `next_order_seed42.json`: scenario → the order in which targets are revealed in next facet suggestion (the seeded order used in the paper).

## MineXR++ notes

- **Participant IDs.** `P01`–`P10` and `P002`–`P022` are two different MineXR cohorts, giving 31 participants in total.
- **Environment labels** keep their original spelling (e.g. `CoffeeShop`, `Coffeeshop`, `coffeeshop`), because the reference methods match labels exactly. Normalization is a method's choice.
- **Placed facets.** "101 facets placed by participants" (paper §3.2) counts the facets that are an element's `facet_id` in at least 2 scenarios. These are the 101 facets of the lift analysis in Fig. 4. Without the 2-scenario threshold, 148 distinct facets occur as `facet_id`s and 163 occur in target sets.
- **Unknown capabilities.** Six capability references in the events point to capabilities absent from the facet DB: `spotify.open_browse_album`, `spotify.open_browse_artist` and `instagram.open_view_content_info`. They are ignored, as in the paper's pipeline.
- **Facet IDs renamed in 1.0.0.** Ten facet IDs were renamed relative to the paper's research code: typos, and IDs that did not match the capability that opens them. Each renamed facet keeps its old ID in `legacy_ids`, and `FacetCatalog.canonical_id()` maps old IDs to new ones. The paper's cached LLM outputs were remapped this way. The paper-regression test (`tests/test_reproduce_paper.py`, Phase 3) checks that the renames leave every reported number unchanged.

  | pre-1.0 ID | 1.0.0 ID |
  |---|---|
  | `clock.mange_alarm_list` | `clock.manage_alarm_list` |
  | `clock.responsd_to_alarm` | `clock.respond_to_alarm` |
  | `uber_eats.track_oder` | `uber_eats.track_order` |
  | `instagram.browse_Explore` | `instagram.browse_explore` |
  | `gmail.view_email_content_actions` | `gmail.view_email_contents_actions` |
  | `gmail.navigate_mailboxes_accounts` | `gmail.navigate_mailboxes_and_accounts` |
  | `amazon.checkout` | `amazon.checkout_purchase` |
  | `camera.select_mode` | `camera.select_capture_mode` |
  | `uber_eats.view_order_history` | `uber_eats.view_order_history_reorder` |
  | `slack.browse_workspace` | `slack.browse_workspaces` |
- **Excluded fields.** Raw widget images and screenshots are not part of the release.
