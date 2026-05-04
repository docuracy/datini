# Datini Letters — Geospatial Explorer

Interactive MapLibre GL JS visualisation of the **Datini merchant correspondence network**
(Francesco di Marco Datini, c. 1363–1412).

**Live demo:** https://docuracy.github.io/datini/

**Data source:** Franklin-Lyons & Oleinikov (2025). *Datini Letter Collection Metadata.*
Digital Philology 14(2): 384–391. [OSF](https://osf.io/mt25a/)

**Letter editions:** [Archivio di Stato di Prato — Le edizioni delle lettere](http://datini.archiviodistato.prato.it/la-ricerca/le-edizioni-delle-lettere)

---

## Visualisation modes

### 📨 Letter Volume (default)
Curved arcs connecting every origin–destination pair with **≥ N letters** (adjustable).
Line width and opacity scale with letter count. Fondacos (main offices: Pisa, Florence,
Barcelona, Genoa, Valencia, Majorca) shown in pink; all other cities in blue.

### ⏱ Travel Time
Same arc network but **coloured by average delivery time**:
- 🔵 Cyan → fast (0–5 days, e.g. Florence→Prato ~1 day)
- 🟢 Green → moderate (5–14 days, e.g. Barcelona→Valencia ~7 days)
- 🟡 Yellow → slow (14–30 days, e.g. Florence→Genoa ~9 days)
- 🔴 Red/magenta → very slow or variable (30+ days, e.g. Palma→Florence)

This visualises the paper's macro-level finding (Fig. 1) that **sea-borne correspondence had
highly variable, unpredictable delivery times** — Palma→Florence letters could arrive in
days or take over a month — while predominantly land routes such as Valencia↔Barcelona
cluster tightly in a 5–10 day band. The authors note this gap was large enough to shape
business expectations: "Business communication would feel quite different if you could
reasonably expect the person to receive the news in about one week versus having to guess
at somewhere between one and four weeks."

> ⚠️ **The recorded times are not pure sea-journey times.** As Franklin-Lyons & Oleinikov
> point out, a letter from a sea-only origin like Palma was often "channeled through a
> closer port and then forwarded by land," so every travel-time figure here is the full
> multi-leg sender-to-recipient duration — not the speed of any single ship. This is
> especially relevant for the red/magenta arcs across the western Mediterranean.

### 🏛 City Activity
City bubbles only (no arc lines), scaled by total letters sent+received. Good for seeing
the geographic distribution of the network at a glance.

### 📅 Timeline (1368–1412)
Drag the year slider to see which cities were generating correspondence in any given year.
The dramatic growth in the 1390s — when the Iberian offices opened — is immediately visible.

### 🌿 Seasonal Travel Time
Pick a month (Jan–Dec) and see how delivery times shifted with the seasons. Arc width
shows how many timed letters fall in that month; arc colour is the average travel time.
Click any arc to see a full 12-month sparkline for that route — sea-influenced routes show
strong winter slowdowns, and some mountain crossings vanish entirely from the data in deep
winter. The same caveat as Travel Time applies: these are full sender-to-recipient times,
not isolated ship- or pass-crossing durations.

### 👤 Person Trajectory
Pick a single correspondent (via the sidebar search, or by clicking **📍 Track on map**
in any ego-network modal) and follow their movements year by year. The map shows three
elements at once:

- **Bright gold circles** for cities the person was active in for the *selected* year
  (sized by letter count), driven by the year slider.
- **Faint background dots** for every other city in their career footprint, so the
  selected year sits in spatial context.
- **Purple arrowed arcs** for the entire career path — one arc per recorded relocation
  between consecutive primary (most-active) cities, with a rotated arrow glyph at the
  destination end pointing in the direction of travel. Click any arc for the from→to
  years of that move.

AGLI MANNO DI ALBIZO's trajectory is a good showcase: four moves between 1384 and 1398
— Pisa → Palermo (1385), Palermo → Pisa (1387), Pisa → Florence (1397), Florence → Pisa
(1398) — visible as four arrows whether you scrub the year slider or look at the static
career path.

A person's location in a given year is inferred from the **origin** of letters they
sent and the **destination** of letters addressed to them, both keyed on the departure
date. Undated letters can't be placed in time and are excluded from this mode (but
still count in every other view).

---

## Interaction

- **Click a city** to focus the map on just its routes — all other arcs hide, letting you
  isolate the correspondence subnet of Genoa, Avignon, Prato or any other city. A "× Clear"
  banner above the stats bar returns you to the full network.
- **Click any arc or city** to open a detail popup with letters sent/received, top senders,
  active years and (for seasonal arcs) a per-month travel-time chart. The sidebar's
  *Selected Feature* panel mirrors the popup and adds the **full** scrollable lists of
  every sender from that city and every recipient at it (the popup shows just the top 5).
- **Find a Correspondent** (sidebar search) — type any fragment of a name. The search
  matches against every recorded variant of every correspondent (so a query for `FRATELLI`
  finds the canonical entries whose merged alias forms include "… E FRATELLI"); rows
  surfaced via an alias are flagged *· via alias*. Click a result to open the ego network
  — or, if **Person Trajectory** mode is active, to start following that person on the map.
- **Click a name** in the *Top Senders* or *Top Recipients* list of any city popup to
  open that person's **ego network**: a D3 force-directed graph of every city they wrote
  from or to, with node size scaled by letter count. Edges are two-tone — gold for letters
  this person sent, teal for letters they received — so you can see incoming and outgoing
  flow on the same diagram. The modal header lists any *Also recorded as* variant forms
  that were folded into this canonical entry (see "Name normalisation" under Technical
  below). Clicking a city node closes the modal, focuses the map on it, and reopens its
  city popup. (The corpus is heavily Datini-centric: clicking `DATINI FRANCESCO DI MARCO`
  produces an ego network spanning ~200+ cities — a useful but unwieldy sanity check on
  the dataset's centre of gravity.)
- **Copy link to current view** — the URL hash captures mode, filters, map position, focus,
  the open popup and any open ego-network modal, so any link you share opens the explorer in
  the exact state you see.

---

## Further ideas

1. **Language choropleth** — colour cities by dominant letter language (Italian, Catalan, Latin)
2. **Bidirectional flow** — separate arcs for A→B and B→A to show asymmetric conservation
3. **Travel time distribution chart** — full inline histogram per route (the seasonal mode
   already shows monthly averages; raw distributions would echo the paper's scatterplots)
4. **Network centrality** — compute betweenness centrality per city and show as a heatmap
5. **Year-range filter across all modes** — currently the year slider only applies in
   Timeline mode
6. **Cross-name disambiguation** — the current normalisation only merges variants that
   share a "before-the-first-' E '" prefix. It does **not** merge cases where the same
   person is recorded with and without a surname (e.g. `FRANCESCO DI MARCO` and
   `DATINI FRANCESCO DI MARCO`), nor does it match across spelling variants. A second
   pass using string similarity or hand-curated synonyms could close those gaps

---

## Technical

### Data files

| File | Description |
|------|-------------|
| `data/processed/cities.geojson` | 285 geocoded cities with letter volumes, fondaco status, active year range |
| `data/processed/routes.geojson` | 963 origin→destination routes with letter counts and travel-time statistics |
| `data/processed/timeline.json` | Per-year letter counts by city (1368–1412), top 30 cities per year |
| `data/processed/senders_by_city.json` | Full ranked sender list per city of origin (every sender with ≥1 letter) |
| `data/processed/recipients_by_city.json` | Full ranked recipient list per city of destination |
| `data/processed/seasonal_travel.json` | Per-route monthly travel-time statistics powering the seasonal mode |
| `data/processed/correspondents.json` | Per-person ego-network edges (sent + received, with origin→destination counts) for every canonical name with ≥3 letters total. Each entry may carry an `aliases` array listing the merged variant forms (see *Name normalisation* below) and a `trajectory` array of `[year, city, count]` tuples powering the *Person Trajectory* mode. |

### Repository structure

```
/
├── index.html                        ← MapLibre interactive explorer (GitHub Pages root)
├── .nojekyll                         ← Disables Jekyll on GitHub Pages
├── data/
│   └── processed/                    ← GeoJSON / JSON consumed by the map
│       ├── cities.geojson
│       ├── routes.geojson
│       ├── timeline.json
│       ├── senders_by_city.json
│       ├── recipients_by_city.json
│       ├── seasonal_travel.json
│       └── correspondents.json
├── scripts/
│   └── build_correspondents.py       ← Rebuilds correspondents.json + senders_by_city.json + recipients_by_city.json from the raw CSV
└── README.md
```

The raw source data (ZIP archive, extracted CSVs, original PDF) are excluded via
`.gitignore` — only the processed files needed by the web app are committed.

### Name normalisation

The same person frequently appears under multiple name forms in the corpus that differ
only by partnership additions:

```
DATINI FRANCESCO DI MARCO
DATINI FRANCESCO DI MARCO E COMP.
DATINI FRANCESCO DI MARCO E LUCA DEL SERA E COMP.
DATINI FRANCESCO DI MARCO E STOLDO DI LORENZO DI SER BERIZO E COMP.
… 31 more variants
```

`build_correspondents.py` runs a normalisation pass that clusters variants by their
shared *core* — the substring before the first whole-word ` E ` (Italian *and*, the
near-universal partnership separator in the data). The bare core becomes the canonical
key in `correspondents.json`, and all merged variants are listed under `aliases` for
transparency. Letter counts, ego-network edges and per-city sender/recipient lists are
all re-aggregated against the canonical names.

To avoid false merges on common given-name roots (`ANTONIO E LORENZO DI FRANCESCO`,
`GIOVANNI E AGNOLO DI IACOPO` — likely different people in unrelated partnerships),
clustering is gated on prefix specificity:

- **3+ tokens in the core** (e.g. `BARZALONE DI SPEDALIERE`, `LUCA DEL SERA`) — always
  cluster.
- **2-token core** (e.g. `BENINI MATTEO`) — cluster only if the bare core itself
  appears as an attested entry in the data (so a real person anchors the merge).
- **1-token core** (e.g. `ANTONIO`) — never cluster.

On the current corpus this folds **707 variant names into 419 canonical entries**
(of which the largest cluster is the Datini firm itself, with 35 partnership variants
collapsed onto `DATINI FRANCESCO DI MARCO`). The frontend's "Find a Correspondent"
search matches against canonical *and* alias text, so a query for `FRATELLI` still
finds canonical entries whose merged variants include "… E FRATELLI"; results
surfaced via an alias are flagged in the dropdown.

### URL hash schema

Shared links encode UI state in the URL fragment. The page reads the hash on load,
applies it, and rewrites it on every UI change via `history.replaceState`, so the URL
is always a valid permalink.

```
#mode=<volume|traveltime|cities|temporal|seasonal|trajectory>
&min=<int>              ← min letters per route
&year=<int>             ← only in temporal mode
&month=<1–12>           ← only in seasonal mode
&map=<lng,lat,zoom>
&focus=<city_datini>    ← active city focus, if any
&person=<name>          ← open ego-network modal for this correspondent, if any
&track=<name>           ← only in trajectory mode: person being followed
&trackyear=<int>        ← only in trajectory mode: year selected on the slider
&sel=<city|route|seasonal>
&name=<...>             ← when sel=city
&from=<...>&to=<...>    ← when sel=route or sel=seasonal
```

### Deployment

This is a fully static site — `index.html` plus `data/processed/`. Push to any static host
or serve with `python3 -m http.server` for local development. The included `.nojekyll`
disables Jekyll processing on GitHub Pages so files starting with underscores are served as-is.
