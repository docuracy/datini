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

---

## Interaction

- **Click a city** to focus the map on just its routes — all other arcs hide, letting you
  isolate the correspondence subnet of Genoa, Avignon, Prato or any other city. A "× Clear"
  banner above the stats bar returns you to the full network.
- **Click any arc or city** to open a detail popup with letters sent/received, top senders,
  active years and (for seasonal arcs) a per-month travel-time chart.
- **Copy link to current view** — the URL hash captures mode, filters, map position, focus
  and the open popup, so any link you share opens the explorer in the exact state you see.

---

## Further ideas

1. **Individual sender/receiver paths** — trace letters from a single person across the network
2. **Language choropleth** — colour cities by dominant letter language (Italian, Catalan, Latin)
3. **Bidirectional flow** — separate arcs for A→B and B→A to show asymmetric conservation
4. **Travel time distribution chart** — full inline histogram per route (the seasonal mode
   already shows monthly averages; raw distributions would echo the paper's scatterplots)
5. **Network centrality** — compute betweenness centrality per city and show as a heatmap
6. **Year-range filter across all modes** — currently the year slider only applies in
   Timeline mode

---

## Technical

### Data files

| File | Description |
|------|-------------|
| `data/processed/cities.geojson` | 285 geocoded cities with letter volumes, fondaco status, active year range |
| `data/processed/routes.geojson` | 963 origin→destination routes with letter counts and travel-time statistics |
| `data/processed/timeline.json` | Per-year letter counts by city (1368–1412), top 30 cities per year |
| `data/processed/top_senders.json` | Top 5 senders per city of origin |
| `data/processed/seasonal_travel.json` | Per-route monthly travel-time statistics powering the seasonal mode |

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
│       ├── top_senders.json
│       └── seasonal_travel.json
└── README.md
```

The raw source data (ZIP archive, extracted CSVs, original PDF) are excluded via
`.gitignore` — only the processed files needed by the web app are committed.

### URL hash schema

Shared links encode UI state in the URL fragment. The page reads the hash on load,
applies it, and rewrites it on every UI change via `history.replaceState`, so the URL
is always a valid permalink.

```
#mode=<volume|traveltime|cities|temporal|seasonal>
&min=<int>              ← min letters per route
&year=<int>             ← only in temporal mode
&month=<1–12>           ← only in seasonal mode
&map=<lng,lat,zoom>
&focus=<city_datini>    ← active city focus, if any
&sel=<city|route|seasonal>
&name=<...>             ← when sel=city
&from=<...>&to=<...>    ← when sel=route or sel=seasonal
```

### Deployment

This is a fully static site — `index.html` plus `data/processed/`. Push to any static host
or serve with `python3 -m http.server` for local development. The included `.nojekyll`
disables Jekyll processing on GitHub Pages so files starting with underscores are served as-is.
