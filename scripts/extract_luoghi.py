#!/usr/bin/env python3
"""
Extract the Melis-archive port/place gazetteer from luoghi.pdf into CSV.

Source PDF: data/luoghi.pdf (9 pages, tabular layout produced from places-dict.xlsx)
Columns in the PDF:
    nome luogo normalizzato | tipo | regione

where `tipo` is usually empty but is set to "regione" for entries that are
regions rather than ports (e.g. "Alemagna", "Bretagna", "Calabria"), and
`regione` is either of the form "<Sub-region>-<Country>" (sometimes with a
slash for cross-border entries like "Sardegna-Italia/Corsica-Francia") or
"Non identificabile".

Writes: data/extracted/luoghi.csv with columns:
    name, kind, region, country, country_iso, identifiable
"""
import csv
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
SRC  = ROOT / "data" / "luoghi.pdf"
OUT  = ROOT / "data" / "extracted" / "luoghi.csv"

# Italian country name → ISO 3166-1 alpha-2. The `regione` column tail is the
# country in Italian; we keep this map small and explicit so unrecognised
# countries are surfaced as a warning rather than silently dropped.
COUNTRY_ISO = {
    "Italia": "IT", "Francia": "FR", "Spagna": "ES", "Portogallo": "PT",
    "Belgio": "BE", "Paesi Bassi": "NL", "Olanda": "NL",
    "Germania": "DE", "Alemagna": "DE",
    "Regno Unito": "GB", "Inghilterra": "GB", "Scozia": "GB",
    "Irlanda": "IE", "Croazia": "HR",
    "Marocco": "MA", "Algeria": "DZ", "Tunisia": "TN", "Libia": "LY",
    "Egitto": "EG", "Israele": "IL", "Libano": "LB", "Siria": "SY",
    "Turchia": "TR", "Grecia": "GR", "Cipro": "CY",
    "Russia": "RU", "Ucraina": "UA",
    # Typos seen in the source PDF
    "Potogallo": "PT", "Aògeria": "DZ",
    # Cells where the country tail was omitted in the source — these
    # are all Italian regions and the country can be inferred.
    "Liguria": "IT", "Toscana": "IT", "Sicilia": "IT", "Sardegna": "IT",
    "Calabria": "IT", "Puglia": "IT", "Campania": "IT", "Lazio": "IT",
    "Marche": "IT", "Veneto": "IT", "Lombardia": "IT", "Emilia": "IT",
    # Ambiguous medieval cell — handled by leaving the country hint
    # blank in the geocoder (Cyprus disambiguates on name alone).
    "Grecia o Turchia": "",
}


def parse_region_cell(cell: str):
    """Return (sub_region, country, country_iso, identifiable)."""
    cell = (cell or "").strip()
    if not cell or cell.lower() == "non identificabile":
        return ("", "", "", False)
    # Cross-border entries use "/" between two "<region>-<country>" pairs.
    # Keep only the first pair for the canonical fields; the raw cell is
    # preserved in `region` for the cross-border case so nothing is lost.
    primary = cell.split("/")[0].strip()
    m = re.match(r"^(.*?)-([^-]+)$", primary)
    if not m:
        return (primary, "", "", True)
    sub, country = m.group(1).strip(), m.group(2).strip()
    return (sub, country, COUNTRY_ISO.get(country, ""), True)


def main():
    rows_out = []
    seen = set()
    unmapped_countries = set()

    with pdfplumber.open(SRC) as pdf:
        for page in pdf.pages:
            for r in page.extract_tables()[0]:
                name = (r[0] or "").strip()
                kind = (r[1] or "").strip()
                region_cell = (r[2] or "").strip()
                if not name or name == "nome luogo normalizzato":
                    continue
                key = (name, kind, region_cell)
                if key in seen:
                    continue
                seen.add(key)
                sub, country, iso, identifiable = parse_region_cell(region_cell)
                if country and country not in COUNTRY_ISO:
                    unmapped_countries.add(country)
                rows_out.append({
                    "name": name,
                    "kind": kind or "porto",
                    "region": region_cell,        # raw cell, preserves "/"
                    "sub_region": sub,
                    "country": country,
                    "country_iso": iso,
                    "identifiable": "yes" if identifiable else "no",
                })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "name", "kind", "region", "sub_region",
            "country", "country_iso", "identifiable",
        ])
        w.writeheader()
        w.writerows(rows_out)

    n_total = len(rows_out)
    n_ident = sum(1 for r in rows_out if r["identifiable"] == "yes")
    n_region = sum(1 for r in rows_out if r["kind"] == "regione")
    print(f"wrote {OUT.relative_to(ROOT)}  ({n_total} rows)")
    print(f"  identifiable: {n_ident}   non identificabile: {n_total - n_ident}")
    print(f"  kind=regione: {n_region}   kind=porto: {n_total - n_region}")
    if unmapped_countries:
        print(f"  ! country names with no ISO mapping: {sorted(unmapped_countries)}")


if __name__ == "__main__":
    main()