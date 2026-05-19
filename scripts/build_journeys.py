#!/usr/bin/env python3
"""
Build data/processed/journeys.geojson from the Melis-archive voyages CSV.

Source:  data/ViaggiJourney.csv  (3,736 rows, 1379–1492)
Gazetteer:  data/processed/luoghi.geojson    (Point per place)
Vessel types:  data/processed/vessel_types.json

One Feature per voyage row that has at least a departure and an arrival
both resolvable to gazetteer points. The geometry is a 2-point LineString
(departure → arrival); the UI renders curved arcs from it client-side.

Filter-ready properties:

  id                    int           — N° Id from source
  departure_place       str           — gazetteer key
  arrival_place         str
  departure_iso         str|null      — YYYY-MM-DD or null
  arrival_iso           str|null
  has_dates             bool          — true iff BOTH dates present
                                        (this is the "filterable" flag)
  duration_days         int|null      — arrival − departure, only when
                                        has_dates and ≥ 0; null otherwise
  ship_types_it         [str, ...]    — atomic tokens from the source
  ship_types_en         [str, ...]    — translated via vessel_types.json
  ship_name             str
  ship_nationality      str
  portcall_places       [str, ...]    — gazetteer-matched only
  articles              str           — Merce
  source                str           — Fonte
  persons               str           — Persona

Place resolution: direct gazetteer hit → accent-stripped → strip
parenthetical "X (…)" → fail. Skip-marker entries (Mari di X, Levante,
etc.) intentionally have no coordinates and therefore filter the
journey out — that's correct, those don't have a point geometry.

Writes alongside the geojson a CSV of unresolvable place strings so the
curator can extend luoghi_overrides.csv if needed.
"""
import csv
import json
import re
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_CSV   = ROOT / "data" / "ViaggiJourney.csv"
GAZ_GEO   = ROOT / "data" / "processed" / "luoghi.geojson"
VESSEL_J  = ROOT / "data" / "processed" / "vessel_types.json"
OUT_GEO   = ROOT / "data" / "processed" / "journeys.geojson"
OUT_MISS  = ROOT / "data" / "processed" / "journeys_unresolved.csv"

DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def strip_accents(s: str) -> str:
    """Drop diacritics so 'Palamós' / 'Palamos' both look up the same."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def parse_date(s: str):
    """Return (datetime.date, iso_string) or (None, None)."""
    s = (s or "").strip()
    m = DATE_RE.match(s)
    if not m:
        return None, None
    try:
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None, None
    return d, d.isoformat()


def split_places(s: str) -> list[str]:
    """Source uses ';', ',' or '/' to combine portcall places."""
    return [p.strip() for p in re.split(r"[;,/]", s or "") if p.strip()]


def split_ship_types(s: str) -> list[str]:
    """Source comma-separates composite types like 'galea, galeotta'."""
    return [t.strip() for t in re.split(r"\s*,\s*", s or "") if t.strip()]


def build_resolver(gaz_features: list):
    """Return a function name → (lng, lat) or None.

    Three-step lookup: exact, accent-stripped, parens-stripped.
    """
    by_name: dict[str, list] = {}
    by_norm: dict[str, list] = {}
    for f in gaz_features:
        name = f["properties"]["name"]
        coords = f["geometry"]["coordinates"]
        by_name[name] = coords
        by_norm[strip_accents(name).lower()] = coords

    def resolve(name: str):
        if not name:
            return None
        if name in by_name:
            return by_name[name]
        norm = strip_accents(name).lower()
        if norm in by_norm:
            return by_norm[norm]
        # Strip "X (parenthetical)" and retry.
        bare = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
        if bare and bare != name:
            if bare in by_name:
                return by_name[bare]
            bnorm = strip_accents(bare).lower()
            if bnorm in by_norm:
                return by_norm[bnorm]
        return None

    return resolve


def main():
    gaz = json.loads(GAZ_GEO.read_text(encoding="utf-8"))
    resolve = build_resolver(gaz["features"])
    vessel = json.loads(VESSEL_J.read_text(encoding="utf-8"))["translations"]
    print(f"loaded {len(gaz['features'])} gazetteer points, "
          f"{len(vessel)} vessel-type entries")

    features = []
    unresolved = Counter()
    n_no_dep = n_no_arr = n_no_either = 0
    n_dated = n_undated_kept = 0
    n_self_loop = 0
    n_negative_duration = 0

    # utf-8-sig strips the BOM that prefixes the first column header
    # in this Excel-exported source — without it `row["N° Id"]` resolves
    # to None because the actual key is "﻿N° Id".
    with SRC_CSV.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        dep_raw = (row.get("Porto Partenza Departure Place") or "").strip()
        arr_raw = (row.get("Porto Arrivo Arrival Place")    or "").strip()
        dep_list = split_places(dep_raw)
        arr_list = split_places(arr_raw)
        # Use the FIRST listed place per endpoint — composites like
        # "Hyères;Brégançon" name two adjacent points; the canonical
        # luoghi.pdf normalisation chose one of them, so we follow suit.
        dep_name = dep_list[0] if dep_list else ""
        arr_name = arr_list[0] if arr_list else ""
        dep_coords = resolve(dep_name)
        arr_coords = resolve(arr_name)

        if not dep_coords:
            n_no_dep += 1
            if dep_name:
                unresolved[dep_name] += 1
        if not arr_coords:
            n_no_arr += 1
            if arr_name:
                unresolved[arr_name] += 1
        if not (dep_coords and arr_coords):
            if not (dep_coords or arr_coords):
                n_no_either += 1
            continue

        if dep_name == arr_name:
            # A row whose departure and arrival are the same place — could
            # be a round-trip captured at one port. We keep the row but
            # use a tiny offset so the LineString isn't degenerate; the
            # UI can detect this via the same dep/arr names.
            n_self_loop += 1

        dep_d, dep_iso = parse_date(row.get("Partenza Departure", ""))
        arr_d, arr_iso = parse_date(row.get("Arrivo Arrival",    ""))
        has_dates = bool(dep_d and arr_d)
        duration = None
        if has_dates:
            d = (arr_d - dep_d).days
            if d < 0:
                # Negative durations indicate transcription / OCR errors
                # (~10 in practice). Surface the flag but blank the value
                # so UI bins don't include them.
                n_negative_duration += 1
            else:
                duration = d
            n_dated += 1
        else:
            n_undated_kept += 1

        ship_raw = (row.get("Tipo Imbarcazioni Ship Type") or "").strip()
        ship_it = split_ship_types(ship_raw)
        ship_en = [vessel.get(t, t) for t in ship_it]

        portcalls = [p for p in split_places(row.get("Porto Scalo Portcall Place", ""))
                     if resolve(p)]

        properties = {
            "id":               int(row["N° Id"]) if row.get("N° Id", "").isdigit() else row.get("N° Id"),
            "departure_place":  dep_name,
            "arrival_place":    arr_name,
            "departure_iso":    dep_iso,
            "arrival_iso":      arr_iso,
            "has_dates":        has_dates,
            "duration_days":    duration,
            "ship_types_it":    ship_it,
            "ship_types_en":    ship_en,
            "ship_name":        (row.get("Nomi Imbarcazioni Ship Name") or "").strip(),
            "ship_nationality": (row.get("Naz. Imbarcazioni Ship Nationality") or "").strip(),
            "portcall_places":  portcalls,
            "articles":         (row.get("Merce Articles") or "").strip(),
            "source":           (row.get("Fonte Sources")  or "").strip(),
            "persons":          (row.get("Persona People Info") or "").strip(),
        }
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [dep_coords, arr_coords],
            },
            "properties": properties,
        })

    OUT_GEO.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEO.write_text(
        json.dumps({"type": "FeatureCollection", "features": features},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    # Write the unresolved-places report — descending count so the most
    # impactful gaps are first.
    with OUT_MISS.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["count", "place_string"])
        for name, n in unresolved.most_common():
            w.writerow([n, name])

    # Date-span sanity
    if features:
        years = sorted(int(p["properties"]["departure_iso"][:4])
                       for p in features
                       if p["properties"]["departure_iso"])
        year_span = f"{years[0]}–{years[-1]}" if years else "—"
    else:
        year_span = "—"

    print(f"\nwrote {OUT_GEO.relative_to(ROOT)}  ({len(features)} journey features)")
    print(f"wrote {OUT_MISS.relative_to(ROOT)}  ({len(unresolved)} distinct unresolved place strings)")
    print(f"  total source rows:           {len(rows)}")
    print(f"  features written:            {len(features)}")
    print(f"    with both dates:           {n_dated}")
    print(f"    undated but routed:        {n_undated_kept}")
    print(f"    self-loops kept:           {n_self_loop}")
    print(f"    negative duration (kept, value blanked): {n_negative_duration}")
    print(f"  dropped — no departure:      {n_no_dep}")
    print(f"  dropped — no arrival:        {n_no_arr}")
    print(f"  dropped — neither endpoint:  {n_no_either}")
    print(f"  date span of routed voyages: {year_span}")


if __name__ == "__main__":
    main()
