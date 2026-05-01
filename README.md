# Datini Letters — Geospatial Explorer

Interactive MapLibre GL JS visualisation of the **Datini merchant correspondence network**
(Francesco di Marco Datini, c. 1363–1412).

**Live demo:** `https://<your-username>.github.io/<repo-name>/`

**Data source:** Franklin-Lyons & Oleinikov (2025). *Datini Letter Collection Metadata.*
Digital Philology 14(2): 384–391. [OSF](https://osf.io/mt25a/)

---

## Deploying to GitHub Pages

1. Push this repository to GitHub.
2. Go to **Settings → Pages** and set the source to the `main` branch, root (`/`) folder.
3. GitHub Pages will serve `index.html` automatically.

The `.nojekyll` file at the root disables Jekyll processing, ensuring the
`data/processed/` directory is served as-is.

---

## Data files generated

| File | Description |
|------|-------------|
| `data/processed/cities.geojson` | 285 geocoded cities with letter volumes, fondaco status, active year range |
| `data/processed/routes.geojson` | 963 origin→destination routes with letter counts and travel-time statistics |
| `data/processed/timeline.json` | Per-year letter counts by city (1368–1412), top 30 cities per year |
| `data/processed/top_senders.json` | Top 5 senders per city of origin |

---

## Repository structure

```
/
├── index.html                        ← MapLibre interactive explorer (GitHub Pages root)
├── .nojekyll                         ← Disables Jekyll on GitHub Pages
├── data/
│   └── processed/                    ← GeoJSON / JSON consumed by the map
│       ├── cities.geojson
│       ├── routes.geojson
│       ├── timeline.json
│       └── top_senders.json
└── README.md
```

The raw source data (ZIP archive, extracted CSVs, original PDF) are excluded via
`.gitignore` — only the processed GeoJSON files needed by the web app are committed.

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
- 🔴 Red/magenta → very slow or variable (30+ days, e.g. sea routes Palma→Florence ~weeks)

This directly illustrates the paper's finding that sea routes had high travel-time variance
vs. the narrow, predictable land routes.

### 🏛 City Activity
City bubbles only (no arc lines), scaled by total letters sent+received. Good for seeing
the geographic distribution of the network at a glance.

### 📅 Timeline (1368–1412)
Drag the year slider to see which cities were generating correspondence in any given year.
The dramatic growth in the 1390s — when the Iberian offices opened — is immediately visible.

---

## Further visualisation ideas

1. **Seasonal heatmap** — filter routes by month to see winter vs. summer sea-lane activity
2. **Individual sender/receiver paths** — trace letters from a single person across the network
3. **Language choropleth** — colour cities by dominant letter language (Italian, Catalan, Latin)
4. **Bidirectional flow** — separate arcs for A→B and B→A to show asymmetric conservation
5. **Travel time distribution chart** — click a route arc to open an inline histogram of all
   delivery times for that pair (echoing the scatterplots in the paper)
6. **Network centrality** — compute betweenness centrality per city and show as a heatmap




