#!/usr/bin/env python3
"""
Reconcile the Melis-archive port/place names against the World Historical
Gazetteer (https://docs.whgazetteer.org/content/technical/apis.html).

Two-pass workflow against the same /reconcile endpoint:

  1. Reconciliation pass — POST {"queries": {...}} to identify the best WHG
     place id for each name. Where the source PDF gives us a country tail
     ("Sicilia-Italia" → IT) we pass it as a `countries` filter, which
     materially improves disambiguation for short or generic names. The
     departure/arrival window of the journeys CSV (1379–1492) sets the
     `start`/`end` temporal hint; `undated=True` keeps records lacking
     date metadata eligible too (most WHG places have none).
  2. Extension pass — POST {"extend": {"ids": [...], "properties": [...]}}
     to fetch the geometry centroid for each matched id. WHG returns
     `{"rows": {id: {"whg:geometry_centroid": [{"str": "lat, lng"}]}}}`,
     which we parse into a Point.

Both passes are cached under data/processed/luoghi_whg_cache.json so reruns
don't re-hit the API. Two outputs are produced:

  data/processed/luoghi.geojson     — one Point feature per resolved place.
  data/processed/luoghi_review.csv  — every row (resolved or not) with the
                                       top match, score, and id, sorted so
                                       low-confidence and unresolved cases
                                       float to the top for manual review.

Requires WHG_API_TOKEN in .env (or in the process environment). Reads .env
with a tiny ad-hoc parser to avoid pulling in python-dotenv.
"""
import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_CSV    = ROOT / "data" / "extracted"  / "luoghi.csv"
OVERRIDES  = ROOT / "data" / "luoghi_overrides.csv"
CACHE      = ROOT / "data" / "processed"  / "luoghi_whg_cache.json"
OUT_GEO    = ROOT / "data" / "processed"  / "luoghi.geojson"
OUT_REVIEW = ROOT / "data" / "processed"  / "luoghi_review.csv"
ENV_FILE   = ROOT / ".env"

WHG_ENDPOINT = "https://whgazetteer.org/reconcile"

# NOTE: we pass neither `fclasses` nor `start/end` temporal filters.
#   * fclasses: GeoNames/Wikidata/OSM/OHM ingestion often leaves this
#     unset, so filtering eliminates the majority of valid matches
#     ("Sardinia" with fclasses=A returns zero results, three without).
#   * start/end: WHG's `undated` flag only governs records *lacking*
#     temporal metadata. Records that DO carry a date (e.g. a modern
#     OSM entry) are still hard-excluded when their dates fall outside
#     the window — and "modern" covers nearly every GeoNames/OSM hit.
#     Empirically: "Portofino" returns 0 hits with start=1350,end=1500
#     even though three valid entries exist.
# Disambiguation is therefore done post-hoc via the country hint
# (`countries`) and score.

BATCH_SIZE = 10                # queries bundled per HTTP request
PAUSE_BETWEEN_BATCHES = 0.5    # seconds — light politeness throttle
MAX_RETRIES = 4                # retry transient 5xx / network errors

# Match mode. WHG supports "exact" | "fuzzy" | "starts" | "in".
# Fuzzy is the right default: WHG's "exact" mode matches only on the
# canonical toponym, so Italian exonyms (Marsiglia, Lisbona, Anversa…)
# come back as no_match even though the underlying GeoNames/Wikidata
# alt-names cover them. Fuzzy hits the alt-name index too. The review
# CSV preserves the WHG score so any speculative match still surfaces.
MATCH_MODE = "fuzzy"

PROP_CENTROID = "whg:geometry_centroid"
PROP_CANON    = "whg:names_canonical"


def load_env(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def build_query(row: dict) -> dict:
    q: dict = {
        "query":   row["name"],
        "mode":    MATCH_MODE,
        "size":    5,
        "undated": True,
    }
    iso = row.get("country_iso", "").strip()
    if iso:
        q["countries"] = [iso]
    return q


def post_json(token: str, body: dict) -> dict:
    payload = json.dumps(body).encode("utf-8")
    last_err = ""
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            WHG_ENDPOINT,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
                "User-Agent":    "datini-viaggi-reconciler/0.1 (+local script)",
                "Accept":        "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", errors="replace")[:300]
            last_err = f"HTTP {e.code}: {body_txt}"
            # Retry on transient upstream errors only; 4xx is a client bug.
            if e.code not in (502, 503, 504):
                raise SystemExit(f"WHG {last_err}") from e
        except urllib.error.URLError as e:
            last_err = f"network error: {e.reason}"
        backoff = min(2 ** attempt, 16)
        print(f"[retry {attempt}/{MAX_RETRIES} in {backoff}s — {last_err[:80]}]",
              end=" ", flush=True)
        time.sleep(backoff)
    raise SystemExit(f"WHG failed after {MAX_RETRIES} retries: {last_err}")


def best_result(results: list) -> dict | None:
    """Pick the best match. WHG marks one result as `match: true` when
    confident; otherwise fall back to highest score. Scores are 0–100."""
    if not results:
        return None
    for r in results:
        if r.get("match"):
            return r
    return max(results, key=lambda r: r.get("score") or 0)


def ranked_results(results: list) -> list:
    """Order results: confident matches first, then by score descending.

    WHG reconciliation often returns several entries for the same place
    from different upstream namespaces (`place:NNN`, `place:gn:NNN`,
    `place:osm:rNNN`, `place:wd:QNNN`). The WHG-native abstract record
    is preferred for identity but frequently lacks its own geometry; we
    fall through to the source-namespace records to recover coordinates
    for the same toponym.
    """
    if not results:
        return []
    confident = [r for r in results if r.get("match")]
    rest      = [r for r in results if not r.get("match")]
    rest.sort(key=lambda r: -(r.get("score") or 0))
    return confident + rest


def parse_centroid(rows_block: dict, place_id: str):
    """Return (lng, lat) tuple or None from an /extend rows entry."""
    row = rows_block.get(place_id) or {}
    vals = row.get(PROP_CENTROID) or []
    if not vals:
        return None
    s = (vals[0] or {}).get("str", "")
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", s)
    if not m:
        return None
    # WHG centroid string is "lat, lng" — invert to (lng, lat) for GeoJSON.
    return (float(m.group(2)), float(m.group(1)))


def load_overrides(path: Path) -> tuple[dict, set]:
    """Read data/luoghi_overrides.csv if present.

    Returns (overrides_with_coords, skip_set):
      * `overrides_with_coords` maps name → row dict (with `_lng`/`_lat`
        floats) for rows that carry usable coordinates. These win over
        the API result.
      * `skip_set` is the set of names where the curator (or the
        variation populator) recorded that NO point geocoding applies —
        sea areas like "Mari di Tripoli", abstract directions like
        "Levante", or names that exhaust their candidate list. For
        these we suppress the API result so a junk match doesn't end
        up in the geojson; they still appear in the review CSV.
    Conventions on the `source` column:
      "auto-skip-*"  → skip (no point geocoding applies)
      anything else (with lng/lat populated) → use as override.
    Rows with empty coords and any other source (or no source) are
    ignored, so the main script falls back to its own API result.
    """
    overrides: dict = {}
    skips: set = set()
    if not path.exists():
        return overrides, skips
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("name") or "").strip()
            if not name:
                continue
            source = (r.get("source") or "").strip()
            lng, lat = (r.get("lng") or "").strip(), (r.get("lat") or "").strip()
            if lng and lat:
                try:
                    overrides[name] = {**r, "_lng": float(lng), "_lat": float(lat)}
                    continue
                except ValueError:
                    pass
            # Empty coords + an explicit skip marker = suppress API match.
            # "auto-unresolved" is NOT a skip — it just means the populator
            # exhausted its variation list, but the main script's looser
            # fuzzy match may still find something useful.
            if source.startswith("auto-skip"):
                skips.add(name)
    return overrides, skips


def main():
    env = load_env(ENV_FILE)
    token = env.get("WHG_API_TOKEN") or os.environ.get("WHG_API_TOKEN")
    if not token:
        raise SystemExit("WHG_API_TOKEN not found in .env or environment.")

    rows = list(csv.DictReader(SRC_CSV.open(encoding="utf-8")))
    targets = [r for r in rows if r["identifiable"] == "yes"]
    overrides, skips = load_overrides(OVERRIDES)
    print(f"reconciling {len(targets)} identifiable places "
          f"({len(rows) - len(targets)} skipped as 'Non identificabile')")
    if overrides or skips:
        print(f"loaded {len(overrides)} overrides and {len(skips)} skip markers "
              f"from {OVERRIDES.relative_to(ROOT)}")

    cache: dict = {"recon": {}, "extend": {}}
    if CACHE.exists():
        loaded = json.loads(CACHE.read_text(encoding="utf-8"))
        # tolerate older single-pass cache shape
        if "recon" in loaded:
            cache = loaded
        else:
            cache["recon"] = loaded
        print(f"loaded cache: {len(cache['recon'])} recon, "
              f"{len(cache['extend'])} extend")

    def save_cache():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    def recon_key(row):
        # Include the bits of the query that affect results so a changed
        # country hint, kind, or match mode forces a refetch (and lets us
        # keep results from a previous mode in cache for comparison).
        return f"{MATCH_MODE}||{row['name']}||{row['country_iso']}||{row['kind']}"

    # ── Pass 1: reconciliation ──────────────────────────────────────
    todo = [r for r in targets if recon_key(r) not in cache["recon"]]
    print(f"recon: {len(todo)} to fetch, {len(targets) - len(todo)} cached")
    for i in range(0, len(todo), BATCH_SIZE):
        chunk = todo[i:i + BATCH_SIZE]
        batch = {f"q{i+j}": build_query(r) for j, r in enumerate(chunk)}
        print(f"  recon batch {i // BATCH_SIZE + 1}: {len(batch)} queries…",
              end=" ", flush=True)
        resp = post_json(token, {"queries": batch})
        for j, r in enumerate(chunk):
            qid = f"q{i+j}"
            block = resp.get(qid) or {}
            results = block.get("result") if isinstance(block, dict) else block
            cache["recon"][recon_key(r)] = results or []
        print("ok")
        save_cache()
        time.sleep(PAUSE_BETWEEN_BATCHES)

    # ── Pass 2: extension to fetch coordinates ──────────────────────
    # Fetch coords for every recon result, not just the top one — WHG-native
    # records often lack their own geometry but the gn/osm/wd siblings in
    # the same result list usually carry it.
    needed_ids = []
    for r in targets:
        for hit in cache["recon"].get(recon_key(r), []) or []:
            pid = hit.get("id")
            if pid and pid not in cache["extend"]:
                needed_ids.append(pid)
    # dedupe while preserving order
    seen = set(); needed_ids = [x for x in needed_ids if not (x in seen or seen.add(x))]
    print(f"extend: {len(needed_ids)} ids to fetch, "
          f"{len(cache['extend'])} cached")
    for i in range(0, len(needed_ids), BATCH_SIZE):
        chunk = needed_ids[i:i + BATCH_SIZE]
        print(f"  extend batch {i // BATCH_SIZE + 1}: {len(chunk)} ids…",
              end=" ", flush=True)
        resp = post_json(token, {"extend": {
            "ids": chunk,
            "properties": [{"id": PROP_CENTROID}, {"id": PROP_CANON}],
        }})
        rows_block = resp.get("rows", {})
        for pid in chunk:
            cache["extend"][pid] = rows_block.get(pid) or {}
        print("ok")
        save_cache()
        time.sleep(PAUSE_BETWEEN_BATCHES)

    # ── Build outputs ───────────────────────────────────────────────
    features = []
    review_rows = []
    n_matched = n_unmatched = n_nogeom = 0

    n_override = n_skipped = 0
    for r in rows:
        # 1. Skip marker — the curator (or variation populator) recorded
        #    that no point geocoding applies (sea area, abstract direction,
        #    or exhausted candidate list). Suppress any API result so a
        #    junk match doesn't reach the geojson.
        if r["name"] in skips:
            n_skipped += 1
            review_rows.append({
                "status": "skip", "name": r["name"], "kind": r["kind"],
                "country_iso": r["country_iso"],
                "match_name": "", "match_id": "", "score": "",
                "lng": "", "lat": "",
            })
            continue

        # 2. Manual override always wins, even for "non identificabile" rows —
        #    the curator may have located it themselves.
        ov = overrides.get(r["name"])
        if ov:
            n_override += 1
            n_matched += 1
            coords = (ov["_lng"], ov["_lat"])
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": list(coords)},
                "properties": {
                    "name":        r["name"],
                    "kind":        r["kind"],
                    "region":      r["region"],
                    "country":     r["country"],
                    "country_iso": r["country_iso"],
                    "whg_id":      ov.get("whg_id") or None,
                    "whg_name":    ov.get("whg_name") or r["name"],
                    "whg_score":   None,
                    "whg_match":   False,
                    "override":    ov.get("source") or "manual",
                },
            })
            review_rows.append({
                "status": "override", "name": r["name"], "kind": r["kind"],
                "country_iso": r["country_iso"],
                "match_name": ov.get("whg_name", ""),
                "match_id":   ov.get("whg_id", ""),
                "score":      ov.get("source", ""),
                "lng": coords[0], "lat": coords[1],
            })
            continue

        if r["identifiable"] != "yes":
            review_rows.append({
                "status": "non identificabile", "name": r["name"],
                "kind": r["kind"], "country_iso": r["country_iso"],
                "match_name": "", "match_id": "", "score": "",
                "lng": "", "lat": "",
            })
            continue
        recon_hits = ranked_results(cache["recon"].get(recon_key(r), []))
        if not recon_hits:
            n_unmatched += 1
            review_rows.append({
                "status": "no_match", "name": r["name"],
                "kind": r["kind"], "country_iso": r["country_iso"],
                "match_name": "", "match_id": "", "score": "",
                "lng": "", "lat": "",
            })
            continue

        # Walk results in priority order; first one with a centroid wins.
        # The selected hit may differ from the top hit when WHG-native
        # records lack geometry — we report the canonical top hit's
        # identity but use the fallback's coords.
        top = recon_hits[0]
        coords = None
        used = top
        for hit in recon_hits:
            cs = parse_centroid(cache["extend"], hit.get("id", ""))
            if cs:
                coords = cs
                used = hit
                break

        status = "matched" if top.get("match") else "best_guess"
        if not coords:
            n_nogeom += 1
            status = "no_geometry"
        review_rows.append({
            "status": status, "name": r["name"], "kind": r["kind"],
            "country_iso": r["country_iso"],
            "match_name": top.get("name", ""),
            "match_id":   used.get("id", ""),
            "score":      top.get("score", ""),
            "lng": coords[0] if coords else "",
            "lat": coords[1] if coords else "",
        })
        if coords:
            n_matched += 1
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": list(coords)},
                "properties": {
                    "name":        r["name"],
                    "kind":        r["kind"],
                    "region":      r["region"],
                    "country":     r["country"],
                    "country_iso": r["country_iso"],
                    "whg_id":      used.get("id"),
                    "whg_name":    top.get("name"),
                    "whg_score":   top.get("score"),
                    "whg_match":   bool(top.get("match")),
                },
            })

    OUT_GEO.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEO.write_text(
        json.dumps({"type": "FeatureCollection", "features": features},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    # Sort review so problems float to the top.
    status_order = {
        "no_match": 0, "no_geometry": 1,
        "non identificabile": 2, "skip": 3,
        "best_guess": 4, "matched": 5, "override": 6,
    }
    def _score_key(s):
        try:
            return -float(s)
        except (TypeError, ValueError):
            return 0
    review_rows.sort(key=lambda r: (
        status_order.get(r["status"], 99),
        _score_key(r.get("score")),
        r["name"],
    ))
    with OUT_REVIEW.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "status", "name", "kind", "country_iso",
            "match_name", "match_id", "score", "lng", "lat",
        ])
        w.writeheader()
        w.writerows(review_rows)

    print(f"\nwrote {OUT_GEO.relative_to(ROOT)}  ({n_matched} features)")
    print(f"wrote {OUT_REVIEW.relative_to(ROOT)}  ({len(review_rows)} rows)")
    print(f"  matched (with geometry): {n_matched}  (incl. {n_override} via overrides)")
    print(f"  no match:                {n_unmatched}")
    print(f"  matched but no geometry: {n_nogeom}")
    print(f"  skip-marker suppressed:  {n_skipped}")
    print(f"  non identificabile:      {len(rows) - len(targets)}")


if __name__ == "__main__":
    main()
