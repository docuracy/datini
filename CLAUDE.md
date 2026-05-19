# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A single-page, no-build static site (`index.html`) that visualises the Datini merchant
correspondence network on a MapLibre map, driven by pre-processed JSON/GeoJSON files
in `data/processed/`. Deployed as-is to GitHub Pages (https://docuracy.github.io/datini/);
`.nojekyll` disables Jekyll processing.

## Commands

- **Run locally:** `python3 -m http.server 8765` from the repo root, then open
  `http://127.0.0.1:8765/`. There is no build/bundle step — MapLibre 4.7.1 and D3 v7
  are loaded from unpkg CDNs directly inside `index.html`.
- **Rebuild correspondent data:** `python3 scripts/build_correspondents.py` regenerates
  `correspondents.json`, `senders_by_city.json`, and `recipients_by_city.json` from
  `data/extracted/Datini Correspondence Complete Metadata.csv` (a raw input that lives
  under `data/extracted/`, which is `.gitignore`d — only the processed outputs are
  committed). Requires `cities.geojson` to already exist; the script validates city
  names against it.
- There are no tests, linters, or package managers in this repo.

## Architecture

### Two-tier pipeline

1. **Offline build (Python).** Raw CSV → `data/processed/*.{json,geojson}`. Currently
   only `build_correspondents.py` exists; the other processed files (`cities.geojson`,
   `routes.geojson`, `timeline.json`, `seasonal_travel.json`) are committed artefacts
   from an upstream pipeline not present in this repo.
2. **Static frontend.** `index.html` is one monolithic file: CSS in `<style>`, markup,
   then a single `<script>` block (~1700 lines) that owns all state, MapLibre layer
   setup, popup rendering, and the D3 ego-network modal. No modules, no transpilation.

### Canonical city key

`name_datini` (the original Italian/period place-name string from the source corpus)
is the join key shared by **every** data file — `cities.geojson` features, `routes.geojson`
`from`/`to`, every key in `senders_by_city.json` / `recipients_by_city.json`, every
`origin`/`destination` in `correspondents.json` edges, and the `focus=` / `from=` /
`to=` values in the URL hash. The English display name (`name_english`) is for labels
only. Don't introduce parallel city identifiers.

### Six visualisation modes

The frontend has a single `currentMode` string switching between `volume`, `traveltime`,
`cities`, `temporal`, `seasonal`, and `trajectory`. Each mode owns its own GeoJSON
source(s) and layer set; `drawLayers()` registers everything once and `applyMode(mode)`
toggles per-layer `visibility`. When adding a new layer, register it in `drawLayers()`,
flip its visibility in `applyMode()`, and (if it's clickable) wire its click handler
in the cursors/click-events block near the bottom of the script.

### URL hash is the source of truth for shareable state

Every state-affecting change (`setMode`, `setMonth`, slider input, popup open/close,
city focus, ego-network modal, trajectory person/year) calls `writeHash()` via
`history.replaceState`, and `parseHash()` is applied on load *before* map init so the
map opens at the shared centre/zoom. If you add new persistent UI state, extend the
hash schema documented in `README.md` (under "URL hash schema") rather than introducing
a separate persistence path — otherwise "Copy link to current view" will silently drop
your state. `VALID_MODES` in the script must stay in sync with the mode buttons.

### Name normalisation (in `build_correspondents.py`)

The corpus records the same person under many partnership variants
(`DATINI FRANCESCO DI MARCO`, `… E COMP.`, `… E LUCA DEL SERA E COMP.`, etc.).
`build_correspondents.py` clusters variants by their pre-` E ` prefix ("core") and
gates merges on prefix specificity (≥3 tokens always merge; 2-token cores only merge
if the bare core is itself an attested entry; 1-token cores never merge) to avoid
false merges on common given names. Canonical entries carry an `aliases` array;
the frontend search indexes canonical + alias text so a query like `FRATELLI` still
hits canonical entries whose merged variants include "… E FRATELLI". If you touch
the clustering rules, update the README's "Name normalisation" section and the
docstring at the top of the script — both are the user-facing reference.

### Trajectory mode data shape

`correspondents.json` entries may carry a `trajectory: [[year, city_datini, count], …]`
array (built by aggregating per-person, per-year presence: a sender's origin or a
recipient's destination, keyed on `data di partenza`). The frontend derives both the
year-by-year highlight circles and the career-path arrows from this same array —
`careerPathSegments()` compresses it into moves between consecutive primary
(max-letter-count) cities. Undated letters are excluded from this mode but still
count everywhere else.