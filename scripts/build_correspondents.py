#!/usr/bin/env python3
"""
Build per-correspondent ego-network data from the Datini correspondence metadata.

Each "correspondent" is a name string that appears as a `mittente` (sender) and/or
`destinatario` (recipient). For each name we record both the routes they sent on
and the routes on which they were addressed, so the ego-network modal can show
incoming and outgoing flow side-by-side.

Reads:  data/extracted/Datini Correspondence Complete Metadata.csv
        data/processed/cities.geojson           (for city name validation)
Writes: data/processed/correspondents.json
        data/processed/senders_by_city.json
        data/processed/recipients_by_city.json

correspondents.json schema (object keyed by canonical name):
    {
      "<NAME>": {
        "sent_total":     <int>,        # letters sent by this person
        "received_total": <int>,        # letters this person received
        "year_first":     <int|null>,
        "year_last":      <int|null>,
        "aliases":        [<name>, ...] # variant forms merged into this entry (optional)
        "sent":     [{"from": ORIG, "to": DEST, "count": N}, ...],
        "received": [{"from": ORIG, "to": DEST, "count": N}, ...]
      }
    }

senders_by_city.json / recipients_by_city.json schema (object keyed by city):
    {
      "<CITY>": [{"name": "...", "count": N}, ...]   # full list, sorted by count desc
    }

Names with fewer than MIN_TOTAL letters (sent + received) are dropped from
correspondents.json to keep the file compact. Per-city lists keep every name.

The same person often appears under multiple variants ("DATINI FRANCESCO DI
MARCO", "... E COMP.", "... E LUCA DEL SERA E COMP."). A normalisation pass
clusters them by their pre-" E " prefix; the bare prefix becomes the canonical
key, and the merged variants are recorded under "aliases" for transparency.
The clustering is gated on prefix specificity (≥3 tokens, or the prefix is
itself an attested name) to avoid false merges on common given-name roots.
"""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_CSV     = ROOT / "data" / "extracted" / "Datini Correspondence Complete Metadata.csv"
CITIES_FILE = ROOT / "data" / "processed" / "cities.geojson"
OUT_PEOPLE  = ROOT / "data" / "processed" / "correspondents.json"
OUT_SENDERS = ROOT / "data" / "processed" / "senders_by_city.json"
OUT_RECIP   = ROOT / "data" / "processed" / "recipients_by_city.json"

MIN_TOTAL = 3        # drop people with fewer than this many letters total

YEAR_RE = re.compile(r"\b(13\d{2}|14\d{2})\b")


def parse_year(s: str):
    if not s:
        return None
    m = YEAR_RE.search(s)
    return int(m.group(1)) if m else None


def main():
    with CITIES_FILE.open(encoding="utf-8") as f:
        cities = json.load(f)
    valid_cities = {feat["properties"]["name_datini"] for feat in cities["features"]}

    sent_edges:     dict[tuple[str, str, str], int] = defaultdict(int)
    received_edges: dict[tuple[str, str, str], int] = defaultdict(int)
    sent_totals:     dict[str, int] = defaultdict(int)
    received_totals: dict[str, int] = defaultdict(int)
    years_first: dict[str, int] = {}
    years_last:  dict[str, int] = {}
    senders_by_city:    dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    recipients_by_city: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    # Per-person, per-year, per-city presence counts (powers Trajectory mode):
    #   sender wrote from origin   → presence at origin in that year
    #   recipient received at dest → presence at dest   in that year
    trajectory_counts: dict[tuple[str, int, str], int] = defaultdict(int)

    skipped_unknown_city = 0
    skipped_missing_field = 0

    with SRC_CSV.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sender    = (row.get("mittente") or "").strip()
            recipient = (row.get("destinatario") or "").strip()
            origin    = (row.get("provenienza") or "").strip()
            dest      = (row.get("destinazione") or "").strip()
            if not (origin and dest):
                skipped_missing_field += 1
                continue
            if origin not in valid_cities or dest not in valid_cities:
                skipped_unknown_city += 1
                continue
            year = parse_year(row.get("data di partenza") or "")

            if sender:
                sent_edges[(sender, origin, dest)] += 1
                sent_totals[sender] += 1
                senders_by_city[origin][sender] += 1
                if year:
                    trajectory_counts[(sender, year, origin)] += 1
                    if sender not in years_first or year < years_first[sender]:
                        years_first[sender] = year
                    if sender not in years_last or year > years_last[sender]:
                        years_last[sender] = year

            if recipient:
                received_edges[(recipient, origin, dest)] += 1
                received_totals[recipient] += 1
                recipients_by_city[dest][recipient] += 1
                if year:
                    trajectory_counts[(recipient, year, dest)] += 1
                    if recipient not in years_first or year < years_first[recipient]:
                        years_first[recipient] = year
                    if recipient not in years_last or year > years_last[recipient]:
                        years_last[recipient] = year

    # ── Name normalisation ───────────────────────────────────────────────
    # Many people appear under multiple variants that differ only by partnership
    # additions: "DATINI FRANCESCO DI MARCO", "... E COMP.", "... E LUCA DEL
    # SERA E COMP.". We treat the substring before the first whole-word " E "
    # as the variant's "core" and cluster names by that core.
    #
    # Guard against false merges on common given names ("ANTONIO E ...",
    # "GIOVANNI E ..."): only cluster if the core has at least 3 tokens, OR
    # the core itself appears as an attested name in the data. That keeps
    # surname-led roots like "BARZALONE DI SPEDALIERE" or attested 2-token
    # bare forms like "BENINI MATTEO", and rejects 1-token first-name roots.
    all_names = set(sent_totals) | set(received_totals)

    def core_of(name):
        return re.split(r"\s+E\s+", name, maxsplit=1)[0].strip()

    raw_groups: dict[str, set[str]] = defaultdict(set)
    for n in all_names:
        raw_groups[core_of(n)].add(n)

    canonical_for: dict[str, str] = {}
    aliases_of:    dict[str, list[str]] = defaultdict(list)
    n_clusters_merged = 0
    n_names_merged    = 0
    for core, members in raw_groups.items():
        if len(members) == 1:
            only = next(iter(members))
            canonical_for[only] = only
            continue
        tokens = core.split()
        # Require at least 2 tokens (rejects bare given names like "ANTONIO");
        # 2-token cores must additionally be attested as a real entry (rejects
        # speculative "DAL POZZO" merges where the bare surname never appears).
        safe = len(tokens) >= 3 or (len(tokens) >= 2 and core in members)
        if not safe:
            for m in members:
                canonical_for[m] = m
            continue
        canonical = core    # may be synthetic if not itself an attested variant
        n_clusters_merged += 1
        for m in members:
            canonical_for[m] = canonical
            if m != canonical:
                aliases_of[canonical].append(m)
                n_names_merged += 1

    # Re-aggregate by canonical
    canon_sent_edges:    dict[tuple[str, str, str], int] = defaultdict(int)
    canon_recv_edges:    dict[tuple[str, str, str], int] = defaultdict(int)
    canon_sent_totals:   dict[str, int] = defaultdict(int)
    canon_recv_totals:   dict[str, int] = defaultdict(int)
    canon_yfirst:        dict[str, int] = {}
    canon_ylast:         dict[str, int] = {}
    for (n, o, d), c in sent_edges.items():
        canon_sent_edges[(canonical_for[n], o, d)] += c
        canon_sent_totals[canonical_for[n]] += c
    for (n, o, d), c in received_edges.items():
        canon_recv_edges[(canonical_for[n], o, d)] += c
        canon_recv_totals[canonical_for[n]] += c
    for name, y in years_first.items():
        c = canonical_for[name]
        if c not in canon_yfirst or y < canon_yfirst[c]:
            canon_yfirst[c] = y
    for name, y in years_last.items():
        c = canonical_for[name]
        if c not in canon_ylast or y > canon_ylast[c]:
            canon_ylast[c] = y

    canon_senders_by_city:    dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    canon_recipients_by_city: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for city, ns in senders_by_city.items():
        for name, c in ns.items():
            canon_senders_by_city[city][canonical_for[name]] += c
    for city, ns in recipients_by_city.items():
        for name, c in ns.items():
            canon_recipients_by_city[city][canonical_for[name]] += c

    canon_trajectory: dict[str, dict[tuple[int, str], int]] = defaultdict(lambda: defaultdict(int))
    for (n, y, city), cnt in trajectory_counts.items():
        canon_trajectory[canonical_for[n]][(y, city)] += cnt

    # Build correspondents.json (keyed by canonical name)
    people: dict[str, dict] = {}
    canonical_names = set(canon_sent_totals) | set(canon_recv_totals)
    for cname in canonical_names:
        s_total = canon_sent_totals.get(cname, 0)
        r_total = canon_recv_totals.get(cname, 0)
        if s_total + r_total < MIN_TOTAL:
            continue
        sent_list = sorted(
            ({"from": o, "to": d, "count": c}
             for (n, o, d), c in canon_sent_edges.items() if n == cname),
            key=lambda e: -e["count"],
        )
        recv_list = sorted(
            ({"from": o, "to": d, "count": c}
             for (n, o, d), c in canon_recv_edges.items() if n == cname),
            key=lambda e: -e["count"],
        )
        entry = {
            "sent_total":     s_total,
            "received_total": r_total,
            "year_first":     canon_yfirst.get(cname),
            "year_last":      canon_ylast.get(cname),
            "sent":     sent_list,
            "received": recv_list,
        }
        a = sorted(aliases_of[cname])
        if a:
            entry["aliases"] = a
        traj = canon_trajectory.get(cname)
        if traj:
            # Sort by (year asc, count desc) so the per-year top city is first.
            entry["trajectory"] = [
                [y, c, n] for (y, c), n in sorted(traj.items(), key=lambda kv: (kv[0][0], -kv[1]))
            ]
        people[cname] = entry

    # Build full per-city lists (sorted desc by count)
    def by_city(d):
        return {
            city: [{"name": n, "count": c}
                   for n, c in sorted(rs.items(), key=lambda kv: -kv[1])]
            for city, rs in d.items()
        }
    senders_out    = by_city(canon_senders_by_city)
    recipients_out = by_city(canon_recipients_by_city)

    OUT_PEOPLE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PEOPLE.open("w", encoding="utf-8") as f:
        json.dump(people, f, ensure_ascii=False, separators=(",", ":"))
    with OUT_SENDERS.open("w", encoding="utf-8") as f:
        json.dump(senders_out, f, ensure_ascii=False, separators=(",", ":"))
    with OUT_RECIP.open("w", encoding="utf-8") as f:
        json.dump(recipients_out, f, ensure_ascii=False, separators=(",", ":"))

    print(f"wrote {OUT_PEOPLE.relative_to(ROOT)}  ({OUT_PEOPLE.stat().st_size / 1024:.1f} KB)")
    print(f"  correspondents kept (>= {MIN_TOTAL} letters): {len(people)}")
    print(f"  name clusters merged: {n_clusters_merged}  (absorbing {n_names_merged} variant names)")
    print(f"wrote {OUT_SENDERS.relative_to(ROOT)}  ({OUT_SENDERS.stat().st_size / 1024:.1f} KB)")
    print(f"  cities with sender data:    {len(senders_out)}")
    print(f"wrote {OUT_RECIP.relative_to(ROOT)}  ({OUT_RECIP.stat().st_size / 1024:.1f} KB)")
    print(f"  cities with recipient data: {len(recipients_out)}")
    print(f"  skipped rows (unknown city):       {skipped_unknown_city}")
    print(f"  skipped rows (missing origin/dest): {skipped_missing_field}")


if __name__ == "__main__":
    main()
