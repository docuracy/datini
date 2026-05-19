#!/usr/bin/env python3
"""
Populate data/luoghi_overrides.csv from the WHG API for names that the main
geocoder (scripts/geocode_luoghi.py) couldn't resolve.

WHG's index includes GeoNames, Wikidata, OSM and OHM data, so Italian
exonyms like "Marsiglia", "Cadice", "Maiorca" should be reachable — they
just aren't the canonical names. This script generates candidate variations
for each unresolved name and probes WHG one by one (exact mode, country
hint from the source PDF where available), recording the first hit per
name. The CSV is the source of truth: re-runs preserve any row whose
`source` column does NOT start with "auto-", so hand-curation survives.

Variation strategies, tried in order until one resolves:

  1. Static Italian→local exonym table (Marsiglia→Marseille,
     Cadice→Cádiz, Maiorca→Mallorca, Gibilterra→Gibraltar, …).
  2. Strip parenthetical: "Pisa (porto fluviale)"     → "Pisa"
  3. Split on ";":         "Barcellona;n.s."           → "Barcellona"
  4. Strip " pressi":      "Maiorca pressi"            → "Maiorca"
  5. Drop locator prefix:  "Capo di Noli" / "Isola d'Elba" / "Foce d'Arno"
     / "Bocca di Magra" / "Costa di Catalogna" / "Costiera di Catalogna"
     / "Largo di Civitavecchia" / "Al largo della Gorgona"
     / "Stretto di Gibilterra" / "Golfo di Venezia"   → trailing toponym.
  6. Skip purely sea-area phrases ("Mari di X", "Mare del Nord", "Levante",
     "Ponente", "Mediterraneo", "n.s.") — these don't have a single point.

Each successful probe writes a row tagged with the variation source
("auto-exonym", "auto-strip-parens", …) so re-runs can re-suggest
just the auto rows without clobbering manual edits.

Writes:  data/luoghi_overrides.csv   (committable, hand-editable)
Cache:   data/processed/luoghi_variation_cache.json
"""
import csv
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_CSV   = ROOT / "data" / "extracted" / "luoghi.csv"
RECON_C   = ROOT / "data" / "processed" / "luoghi_whg_cache.json"
VAR_CACHE = ROOT / "data" / "processed" / "luoghi_variation_cache.json"
OVERRIDES = ROOT / "data" / "luoghi_overrides.csv"
ENV_FILE  = ROOT / ".env"

WHG_ENDPOINT = "https://whgazetteer.org/reconcile"
PROP_CENTROID = "whg:geometry_centroid"

PAUSE = 0.3
# fclasses + start/end deliberately omitted — see geocode_luoghi.py for
# rationale. tl;dr both filters silently drop the majority of valid hits
# (GeoNames/Wikidata/OSM rarely populate fclasses; dated OSM/GN records
# fall outside any medieval window even with undated=True).

OVERRIDE_FIELDS = ["name", "whg_id", "whg_name", "lng", "lat", "source", "notes"]

# ── Italian exonym → variants we'll try (in priority order) ─────────
# Keys are the names as they appear in luoghi.csv. The list is endonyms
# and well-known alternatives; the first that WHG knows wins.
EXONYMS = {
    "Alessandria d'Egitto": ["Alexandria", "El Iskandariya"],
    "Amalfi":           ["Amalfi"],
    "Bonifacio":        ["Bonifacio"],
    "Cherchel":         ["Cherchell", "Iol Caesarea"],
    "Citèra":           ["Kythira", "Cerigo", "Kithira"],
    "Feodosia":         ["Feodosiya", "Caffa", "Kaffa", "Theodosia"],
    "Fiandra":          ["Flanders", "Vlaanderen"],
    "Galizia":          ["Galicia"],
    "Gibilterra":       ["Gibraltar"],
    "Honaïne":          ["Honaine", "Hunayn"],
    "Ibiza":            ["Ibiza", "Eivissa"],
    "Maiorca":          ["Mallorca", "Majorca"],
    "Maiorca pressi":   ["Mallorca"],
    "Palma di Maiorca": ["Palma de Mallorca", "Palma"],
    "Marsiglia pressi": ["Marseille"],
    "Mare del Nord":    ["North Sea"],
    "Mitilene":         ["Mytilene", "Lesbos"],
    "Monte Argentario": ["Monte Argentario", "Argentario"],
    "Portofino":        ["Portofino"],
    "Sardegna":         ["Sardinia", "Sardegna"],
    "Stiges":           ["Sitges"],
    "Stretto di Gibilterra": ["Strait of Gibraltar", "Gibraltar"],
    "Tamigi":           ["Thames"],
    "Ventimiglia":      ["Ventimiglia"],
    "Zelanda":          ["Zeeland"],
    "Levante":          ["Levant"],
    "Manica (canale della)": ["English Channel", "La Manche"],
    "Barberia":         ["Barbary", "Maghreb", "Barbary Coast"],
    "Biscaglia":        ["Biscay", "Bay of Biscay"],
    "Mare del Nord":    ["North Sea"],
    "Talamone pressi":  ["Talamone"],
    "Southampton pressi": ["Southampton"],
    "Valenza pressi":   ["Valencia"],
    "Malaga pressi":    ["Málaga", "Malaga"],
    "Cabo de São Vicente": ["Cape Saint Vincent", "São Vicente", "Sagres"],
    "Cabo de Gata":     ["Cabo de Gata"],
    "Cap de Salou":     ["Salou"],
    "Belle Île":        ["Belle-Île-en-Mer", "Belle Île"],
    "Benidorm":         ["Benidorm"],
    "Berre-l'Étang":    ["Berre-l'Étang", "Berre"],
    "Canet-en Roussillon": ["Canet-en-Roussillon", "Canet"],
    "Port-de-Bouc":     ["Port-de-Bouc"],
    "Fort de Brégançon": ["Brégançon", "Bregançon"],
    "Hyères;Brégançon": ["Hyères"],
    "Pisa (porto fluviale)": ["Pisa"],
    "Barcellona;n.s.":  ["Barcelona"],
    "Romania;Levante":  ["Romania"],
    "Porto Alessandria d'Egitto": ["Alexandria"],
    "Arnhem (nei pressi di Anversa)": ["Antwerp", "Anvers"],
    "Riviera ligure":   ["Liguria"],
    "Varigotti":        ["Varigotti"],
    "Ripa di Roma":     ["Ripa Romea", "Rome"],
    "Foce d'Arno":      ["Arno"],
    "Bocca di Magra":   ["Bocca di Magra", "Magra"],
    "Golfo del Leone":  ["Gulf of Lion", "Golfe du Lion"],
    "Golfo di Narbona": ["Narbonne"],
    "Golfo di Venezia": ["Gulf of Venice", "Venice"],
    "Capo Otranto":     ["Otranto", "Capo d'Otranto"],
    "Capo di Campana":  ["Capo di Campana"],
    "Capo di Noli":     ["Noli"],
    "Capo di Pietra":   ["Capo di Pietra"],
    "Dragonera":        ["Sa Dragonera", "Dragonera"],
    "Dragonera pressi": ["Sa Dragonera"],
    "Isola S. Margherita": ["Île Sainte-Marguerite", "Sainte-Marguerite",
                             "Santa Margherita"],
    "Isola d'Albenga":  ["Gallinara", "Albenga"],
    "Isola d'Elba":     ["Elba"],
    "Isola di Marsiglia": ["Frioul", "If"],
    "Isole Medas":      ["Illes Medes", "Medes Islands"],
    "Largo di Civitavecchia": ["Civitavecchia"],
    "Al largo della Gorgona": ["Gorgona"],
    "Porto Pisano":     ["Porto Pisano", "Livorno"],
    "Amone":            ["Mahón", "Mahon"],
}

# Phrases that resolve to a sea area / abstract direction — don't probe.
# (We still emit a row to overrides.csv so the curator sees them, but with
# no coordinates and source="auto-skip".)
SEA_AREA_PATTERNS = [
    re.compile(r"^Mari? d[ie] "),    # "Mari di X" / "Mare di X"
    re.compile(r"^Costa d[ie] "),
    re.compile(r"^Costiera d[ie] "),
]
SEA_AREA_LITERALS = {
    "Mediterraneo", "Ponente", "Levante", "Mezzogiorno",
    "n.s.", "Mare del Nord",
    "Golfo del Leone",     # Gulf of Lion — sea area, no point centroid.
}


def slugify(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


def variation_candidates(name: str) -> list[tuple[str, str]]:
    """Yield (variation_string, source_tag) candidates for one name."""
    cands: list[tuple[str, str]] = []

    # 1. Exonym table
    for v in EXONYMS.get(name, []):
        cands.append((v, "auto-exonym"))

    # 2. Strip parenthetical
    stripped = re.sub(r"\s*\([^)]*\)\s*", " ", name).strip()
    if stripped and stripped != name:
        cands.append((stripped, "auto-strip-parens"))

    # 3. Split on ";"
    if ";" in name:
        head = name.split(";", 1)[0].strip()
        if head and head != name:
            cands.append((head, "auto-split-semicolon"))

    # 4. Strip " pressi" suffix
    if name.endswith(" pressi"):
        cands.append((name[: -len(" pressi")].strip(), "auto-strip-pressi"))

    # 5. Drop locator prefix
    prefix_re = re.compile(
        r"^(Capo d[ie] |Capo |Isola d[i']\s*|Isola |Foce d'?|Bocca d[ie] |"
        r"Costa d[ie] |Costiera d[ie] |Largo d[ie] |Al largo (?:della |del |dei )?|"
        r"Stretto d[ie] |Golfo d[ie] |Porto )",
        re.IGNORECASE,
    )
    m = prefix_re.match(name)
    if m:
        tail = name[m.end():].strip().lstrip("'").strip()
        if tail:
            cands.append((tail, f"auto-strip-{m.group(1).strip().lower().replace(' ', '-')}"))

    # Dedup while preserving order
    seen = set()
    out = []
    for v, tag in cands:
        v = slugify(v)
        if not v or v in seen:
            continue
        seen.add(v)
        out.append((v, tag))
    return out


def is_sea_area(name: str) -> bool:
    if name in SEA_AREA_LITERALS:
        return True
    return any(p.search(name) for p in SEA_AREA_PATTERNS)


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


def post_json(token: str, body: dict) -> dict:
    payload = json.dumps(body).encode("utf-8")
    for attempt in range(4):
        req = urllib.request.Request(
            WHG_ENDPOINT, data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
                "User-Agent":    "datini-viaggi-variation-probe/0.1",
                "Accept":        "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", errors="replace")[:200]
            if e.code not in (502, 503, 504):
                raise SystemExit(f"WHG HTTP {e.code}: {txt}") from e
            time.sleep(2 ** attempt)
        except urllib.error.URLError:
            time.sleep(2 ** attempt)
    raise SystemExit("WHG: gave up after 4 retries.")


_COUNTRY_DESC_RE = re.compile(r"Country:\s*([A-Z]{2})\b")


def _description_country(result: dict) -> str:
    """Pull the ISO country code from a WHG result's `description` field
    (format: "Country: XX"). Returns "" if not present."""
    desc = result.get("description") or ""
    m = _COUNTRY_DESC_RE.search(desc)
    return m.group(1) if m else ""


def best_result(results: list) -> dict | None:
    if not results:
        return None
    for r in results:
        if r.get("match"):
            return r
    return max(results, key=lambda r: r.get("score") or 0)


def parse_centroid(rows_block: dict, place_id: str):
    row = rows_block.get(place_id) or {}
    vals = row.get(PROP_CENTROID) or []
    if not vals:
        return None
    s = (vals[0] or {}).get("str", "")
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", s)
    if not m:
        return None
    return (float(m.group(2)), float(m.group(1)))


def probe_variation(token: str, variation: str, iso: str, kind: str,
                    cache: dict) -> dict | None:
    """Try one variation. Cache hit returns immediately. Returns:
        {"id": str, "name": str, "lng": float, "lat": float} or None.

    Two-pass: first probe with the country filter, then (if that's empty
    or the matched id has no geometry) re-probe without it. WHG's country
    metadata is inconsistent — e.g. Île Sainte-Marguerite (Cannes, FR) is
    reported as Country: IT — and the country filter discards otherwise
    perfect hits.
    """
    key = f"{variation}||{iso}||{kind}"
    if key in cache:
        return cache[key] or None

    def _query(with_country: bool) -> list:
        q = {"query": variation, "mode": "exact", "size": 3, "undated": True}
        if iso and with_country:
            q["countries"] = [iso]
        resp = post_json(token, {"queries": {"q0": q}})
        return (resp.get("q0") or {}).get("result") or []

    def _filter_by_country(results: list) -> list:
        # Reject hits whose own `description` field claims a different
        # country than expected. Protects against WHG entries with wrong
        # `countries` metadata (e.g. "Barbary Coast" tagged TN but
        # actually a San Francisco neighbourhood, score-100 match).
        if not iso:
            return results
        return [r for r in results
                if _description_country(r) in ("", iso)]

    results = _filter_by_country(_query(with_country=True))
    if not results and iso:
        results = _filter_by_country(_query(with_country=False))
    best = best_result(results)
    if not best:
        cache[key] = None
        VAR_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(PAUSE)
        return None

    pid = best.get("id")
    extend = post_json(token, {"extend": {
        "ids": [pid], "properties": [{"id": PROP_CENTROID}],
    }})
    coords = parse_centroid(extend.get("rows", {}), pid)
    if not coords:
        cache[key] = None
        VAR_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(PAUSE)
        return None

    out = {"id": pid, "name": best.get("name"), "lng": coords[0], "lat": coords[1]}
    cache[key] = out
    VAR_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    time.sleep(PAUSE)
    return out


def load_existing_overrides() -> dict[str, dict]:
    """Return existing overrides keyed by name. Manual rows (source not
    starting with 'auto-') are preserved verbatim and never overwritten.

    Legacy "auto-unresolved" rows are silently dropped — they originated
    from an earlier populator pass and would otherwise be re-loaded here,
    re-written verbatim, and then suppress the main script's match.
    """
    if not OVERRIDES.exists():
        return {}
    out = {}
    with OVERRIDES.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            n = (r.get("name") or "").strip()
            if not n:
                continue
            if (r.get("source") or "") == "auto-unresolved":
                continue
            out[n] = r
    return out


def main():
    env = load_env(ENV_FILE)
    token = env.get("WHG_API_TOKEN") or os.environ.get("WHG_API_TOKEN")
    if not token:
        raise SystemExit("WHG_API_TOKEN not found in .env or environment.")

    rows = list(csv.DictReader(SRC_CSV.open(encoding="utf-8")))
    by_name = {r["name"]: r for r in rows}

    # The main script's cache tells us which names need fixing.
    recon_cache = {}
    extend_cache = {}
    if RECON_C.exists():
        c = json.loads(RECON_C.read_text(encoding="utf-8"))
        recon_cache  = c.get("recon",  {})
        extend_cache = c.get("extend", {})

    # We use MAIN script's match-mode key prefix to find "what's missing".
    # The current default there is fuzzy. Two failure modes we need to fix:
    #   (a) no_match    — WHG returned no result for the name at all
    #   (b) no_geometry — WHG returned a place id but its extend response
    #                     carries no centroid (common for OSM relations
    #                     of well-known places like Portofino)
    # Both benefit from re-probing with a known-good local-language form.
    no_match_or_nogeom: list[str] = []
    for r in rows:
        if r["identifiable"] != "yes":
            continue
        key = f"fuzzy||{r['name']}||{r['country_iso']}||{r['kind']}"
        results = recon_cache.get(key, [])
        best = best_result(results)
        if not best:
            no_match_or_nogeom.append(r["name"])
            continue
        coords = parse_centroid(extend_cache, best.get("id", ""))
        if not coords:
            no_match_or_nogeom.append(r["name"])

    print(f"need overrides for {len(no_match_or_nogeom)} names "
          f"(no_match + no_geometry)")

    # Sea-area suppression must apply to EVERY identifiable name, not
    # just the no-match list — fuzzy-mode WHG will happily match "Mari
    # di Tripoli" to "JW Marriott Tripoli". Anything matching a sea-area
    # pattern always needs a skip marker, even if the main script
    # currently returns a bogus geocode for it.
    sea_area_names: list[str] = [
        r["name"] for r in rows
        if r["identifiable"] == "yes" and is_sea_area(r["name"])
    ]
    extra = [n for n in sea_area_names if n not in no_match_or_nogeom]
    if extra:
        print(f"  + {len(extra)} sea-area names also need skip markers")
        no_match_or_nogeom = list(no_match_or_nogeom) + extra

    var_cache = {}
    if VAR_CACHE.exists():
        var_cache = json.loads(VAR_CACHE.read_text(encoding="utf-8"))
    existing = load_existing_overrides()

    # Start from manual rows only. Auto-* rows are rebuilt from scratch
    # each run — otherwise yesterday's false-positive auto-exonym match
    # (e.g. "Bonifacio → Philippines" before we added the country sanity
    # check) survives indefinitely.
    out_rows: dict[str, dict] = {
        n: dict(r) for n, r in existing.items()
        if not (r.get("source") or "").startswith("auto-")
    }
    kept_manual = len(out_rows)
    print(f"preserving {kept_manual} manual override row(s); auto rows will be rebuilt")

    n_resolved = 0
    n_skipped = 0
    n_unresolved = 0
    for name in no_match_or_nogeom:
        existing_row = existing.get(name)
        if existing_row and not (existing_row.get("source") or "").startswith("auto-"):
            # Hand-edited — never re-probe.
            continue

        row_csv = by_name.get(name, {})
        iso = row_csv.get("country_iso", "")
        kind = row_csv.get("kind", "porto")

        if is_sea_area(name):
            n_skipped += 1
            out_rows[name] = {
                "name": name, "whg_id": "", "whg_name": "",
                "lng": "", "lat": "",
                "source": "auto-skip-sea-area",
                "notes": "Sea zone or abstract direction — no point geocoding.",
            }
            continue

        cands = variation_candidates(name)
        if not cands:
            n_unresolved += 1
            # Don't write a row — main script's direct match may still hit.
            continue

        hit = None; used_tag = ""; used_var = ""
        for variation, tag in cands:
            print(f"  {name!r:50s} → {variation!r:35s} ({tag})", end=" ", flush=True)
            hit = probe_variation(token, variation, iso, kind, var_cache)
            if hit:
                used_tag, used_var = tag, variation
                print("HIT", flush=True)
                break
            print("miss", flush=True)

        if hit:
            n_resolved += 1
            out_rows[name] = {
                "name":     name,
                "whg_id":   hit["id"],
                "whg_name": hit["name"],
                "lng":      hit["lng"],
                "lat":      hit["lat"],
                "source":   used_tag,
                "notes":    f"variation: {used_var}",
            }
        else:
            n_unresolved += 1
            # No row — main script's direct match wins if any.

    # Write overrides CSV, sorted by name
    OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
    with OVERRIDES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OVERRIDE_FIELDS)
        w.writeheader()
        for name in sorted(out_rows):
            r = out_rows[name]
            w.writerow({k: r.get(k, "") for k in OVERRIDE_FIELDS})

    print(f"\nwrote {OVERRIDES.relative_to(ROOT)}  ({len(out_rows)} rows)")
    print(f"  resolved via variations: {n_resolved}")
    print(f"  skipped (sea area):       {n_skipped}")
    print(f"  unresolved:               {n_unresolved}")
    print(f"  manual preserved:         {kept_manual}")


if __name__ == "__main__":
    main()
