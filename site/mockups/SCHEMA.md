# Facet mockup specs

One JSON file per app, `site/mockups/<app_id>.json`. Each facet is drawn as a small XR panel
whose UI elements are exactly the facet's capabilities. `scripts/build_site_mockups.py`
validates the specs and bundles them into `site/data/mockups.js`.

## Rules

1. **Exactly the capabilities.** Every capability of the facet appears in exactly one element,
   and every element belongs to a capability of the facet. (Several items of the same block may
   share one capability, e.g. "Previous" and "Next" for `navigate_steps`.) Do not add decorative elements
   (no extra titles, no fake tabs or buttons). Panel chrome (app name, facet name) is drawn by
   the renderer.
2. **Realistic, specific content.** Content looks like a real app screen in a plausible everyday
   moment: "Tomato Pasta", "Blinding Lights · The Weeknd", "Standup in 15 min". No lorem
   ipsum, no "Item 1". Keep text short: the panel is 340 px wide.
3. **Navigational capabilities** (`open_<facet>`) are drawn as a `link` or a `button`
   (or a `tabs` item) whose label reads like real UI ("Start Cooking", "See all playlists").
   They render in blue.
4. Order elements as a real screen would: identity/title first, content, then actions.
5. Aim for a compact panel. Merge related capabilities into one element via `items` (e.g.,
   play / pause / skip in one `controls` row) rather than a block each.

## File format

```json
{
  "app": "recipes",
  "icon": "chef-hat",            // Lucide icon name for the app (https://lucide.dev/icons)
  "color": "#e8590c",            // app accent colour (hex), used for the app badge and media tints
  "facets": {
    "recipes.view_recipe": {
      "blocks": [ ... ]
    }
  }
}
```

Every facet of the app, including `<app>.open_section`, needs an entry.

## Blocks

Every block has a `type`. A block is tied to capabilities in one of two ways:

- `"cap": "name"` (or `"caps": ["a", "b"]`) on the block, or
- a `cap` on each entry of its `items` (for `controls`, `buttons`, `tabs`, and item actions).

Any block may also have `"label"`: a small uppercase section heading drawn above it
(e.g. `"Ingredients"`).

`icon` values are Lucide icon names in kebab-case (`play`, `skip-forward`, `map-pin`, …).
`hue` values are 0–360 and tint media placeholders.

| type | fields | use for |
|---|---|---|
| `header` | `title`, `subtitle?`, `thumb?` (`{icon, hue}`) | the main identity of the screen (recipe name, song + artist, contact name) |
| `text` | `text`, `size?` (`sm`/`md`/`lg`), `muted?` | a paragraph, description, caption, body of an email |
| `list` | `items: [{title, meta?, trailing?, icon?, avatar?, hue?, done?, action?}]`, `style?` (`plain`/`check`/`numbered`/`thumbs`) | lists of emails, songs, tasks, results, steps |
| `kv` | `items: [[key, value], …]` | label/value rows (ingredients with amounts, product specs) |
| `media` | `kind` (`photo`/`video`/`art`/`doc`/`camera`), `hue?`, `icon?`, `caption?`, `aspect?` (`wide`/`square`/`tall`), `duration?` | images, album art, video frames, camera viewfinders |
| `player` | `progress` (0–1), `elapsed`, `total` | playback position / seek bar |
| `controls` | `items: [{cap, icon, label?, primary?}]` | a row of round icon buttons (media controls, quick actions) |
| `button` | `label`, `icon?`, `style?` (`primary`/`secondary`/`ghost`/`danger`) | one action |
| `buttons` | `items: [{cap, label, icon?, style?}]` | a row of actions |
| `link` | `label`, `icon?`, `meta?` | a navigation row with a chevron (typically an `open_*` capability) |
| `tabs` | `items: [{cap, label, icon}]`, `selected?` | a tab or navigation bar (typically the `open_*` capabilities of `open_section`) |
| `toggle` | `label`, `on`, `desc?` | a switch |
| `slider` | `label`, `value` (0–1), `icon?`, `display?` | volume, brightness, zoom |
| `stepper` | `label`, `value` | − value + (servings, quantity) |
| `input` | `placeholder`, `value?`, `icon?`, `multiline?`, `trailing?` (icon) | text fields, search bars, composers |
| `chips` | `items: [string]`, `selected?` (index or list of indices) | filters, tags, categories |
| `segmented` | `items: [string]`, `selected` | a mode switch (Day/Week/Month, Photo/Video) |
| `select` | `label`, `value` | a dropdown setting (language, sound, account) |
| `stat` | `value`, `unit?`, `label?`, `icon?`, `delta?` | one big number (temperature, price, steps) |
| `progress` | `label`, `value` (0–1), `display?` | progress bars (order, download, goal) |
| `timer` | `display` (e.g. `"14:52"`), `label?` | big clock / countdown digits |
| `grid` | `items: [{label, icon?, hue?}]`, `cols?` (2–4) | tiles: categories, shortcuts, photo grids |
| `cards` | `items: [{title, meta?, hue?, icon?}]` | a horizontal carousel of media cards (recommendations, playlists) |
| `map` | `kind` (`pins`/`route`/`area`), `label?` | maps, routes, location sharing |
| `chart` | `kind` (`line`/`bars`), `values?` (numbers), `label?` | stock price, health trends, forecasts |
| `calendar` | `kind` (`month`/`agenda`/`week`), `items?: [{time, title, hue?}]`, `month?` | calendar views and agendas |
| `chat` | `items: [{from: "me"/"them", text, name?}]` | message threads |
| `keypad` | `keys?: [string]` (default calculator keys) | calculators, dial pads |
| `avatar` | `name`, `status?`, `hue?` | a person/account row |
| `badge` | `label`, `tone?` (`green`/`red`/`blue`/`amber`/`gray`) | a status pill ("Active", "Delivered") |
| `notice` | `title`, `text?`, `icon?`, `tone?` | an alert or banner (alarm ringing, order arriving) |
| `rating` | `value` (0–5), `count?` | star ratings |
| `code` | `lines: [string]` | code or LaTeX source |
| `row` | `blocks: [block, …]`, `widths?: [number, …]` | lay child blocks side by side (no capability of its own) |
| `group` | `cap`, `blocks: [block, …]` | one capability drawn as several pieces (a step header + its text). Children carry no `cap`. |

Item actions: `list` items may carry `"action": {"cap": "star_email", "icon": "star"}`, a small
icon button at the end of the row, so a per-row action capability (star, delete, add to
playlist) can live inside the list. The same action capability may repeat on several rows of one list.

## Example

```json
"recipes.view_recipe": {
  "blocks": [
    {"type": "row", "widths": [1, 1.25], "blocks": [
      {"type": "media", "cap": "view_recipe_media", "kind": "photo", "hue": 18, "icon": "utensils", "aspect": "tall"},
      {"type": "header", "cap": "view_cooking_time", "title": "Tomato Pasta", "subtitle": "Prep 15 min · Cook 20 min"}
    ]},
    {"type": "stepper", "cap": "adjust_serving_size", "label": "Servings", "value": "4"},
    {"type": "kv", "cap": "view_ingredients", "label": "Ingredients",
     "items": [["Spaghetti", "400 g"], ["Crushed tomatoes", "1 can"], ["Garlic cloves", "2"]]},
    {"type": "text", "cap": "view_preparation_steps", "label": "Preparation", "size": "sm",
     "text": "Boil the pasta in salted water. Sauté garlic in olive oil, add tomatoes and simmer."},
    {"type": "row", "widths": [1, 3], "blocks": [
      {"type": "button", "cap": "save_recipe", "icon": "bookmark", "style": "secondary", "label": "Save"},
      {"type": "button", "cap": "open_cook_recipe", "label": "Start Cooking", "icon": "chevron-right"}
    ]}
  ]
}
```
