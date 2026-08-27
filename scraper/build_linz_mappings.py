"""Rebuild the source-area mapping tables against LINZ suburb names.

Writes data/rent_area_mapping_linz.csv and data/crime_area_mapping_linz.csv,
one row per source area, each carrying how it was resolved so nothing
disappears silently. Fuzzy matching is deliberately avoided; every rule here
is explicit and its name is recorded in the `via` column.
"""
import csv
import json
import os
import re
import sys
import unicodedata as ud

csv.field_size_limit(sys.maxsize)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")

# Decided by hand. Source areas that no rule resolves, but which clearly belong
# to a LINZ suburb. Balmoral and St Lukes are not LINZ suburbs at all — LINZ
# folds them into neighbours — so their rent and crime go to those neighbours.
MANUAL = {
    "Balmoral": "Mount Eden",
    "St Lukes": "Mount Albert",
    "St Lukes North": "Mount Albert",
    "Botany East": "Botany Downs",
    "Botany North": "Botany Downs",
    "Botany South": "Botany Downs",
    "Botany Junction": "Botany Downs",
    "Manukau Central": "Manukau City Centre",
    "Golfland": "Botany Downs",
    "Golflands": "Golflands",
    "Meadowland": "Botany Downs",
    "Millhouse": "Botany Downs",
    "Greenmount": "East Tāmaki",
    "Highbrook": "East Tāmaki",
    "Bledisloe Park": "East Tāmaki",
    "Ormiston": "Flat Bush",
    "Puhinui North": "Wiri",
    "Puhinui South": "Wiri",
}

DIRS = r"(north|south|east|west|central|upper|lower|nth|sth)"


def norm(s):
    s = ud.normalize("NFD", s)
    s = "".join(c for c in s if not ud.combining(c))
    s = s.lower().replace("mount ", "mt ").replace("saint ", "st ")
    return "".join(ch for ch in s if ch.isalnum())


def stems(s):
    """Progressively shorter forms of a source-area name, longest first.

    Order matters. `Te Atatu South-Central` must be tried as `Te Atatu South`
    before the direction strip reduces it to `Te Atatu`, which is not a suburb.
    Callers take the first form that matches, so a shorter stem is only reached
    when every longer one failed.
    """
    out = []
    t = re.sub(r"\s*\((auckland|akl)\)$", "", s, flags=re.I).strip()
    out.append(t)
    t = re.sub(r"[-–].*$", "", t).strip()              # `Te Atatu South-Central`
    out.append(t)
    for _ in range(2):                                 # `Mount Eden West`
        t = re.sub(r"\s+" + DIRS + r"\s*$", "", t, flags=re.I).strip()
        out.append(t)
    seen, uniq = set(), []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def build(source_names, old_path, out_path, linz):
    by_norm = {norm(n): n for n in linz}
    old = {r["source_area"]: r for r in csv.DictReader(open(old_path))}

    rows = []
    for name in sorted(source_names):
        target = via = None
        prev = old.get(name, {})
        if name in MANUAL:
            target, via = MANUAL[name], "manual"
        else:
            # The name's own stem wins over the previous table. `Mt Wellington
            # North` names its suburb outright; the old table sent it to Penrose
            # only because Mount Wellington was not on the 62-suburb list.
            for i, stem in enumerate(stems(name)):
                if norm(stem) in by_norm:
                    target = by_norm[norm(stem)]
                    via = "exact" if i == 0 else "stem"
                    break
            if not target and prev.get("status") == "mapped" \
                    and norm(prev["master_suburb"]) in by_norm:
                target, via = by_norm[norm(prev["master_suburb"])], "previous-mapping"

        if target:
            rows.append({"source_area": name, "linz_suburb": target,
                         "status": "mapped", "via": via, "reason_if_not_mapped": ""})
        else:
            reason = (prev.get("reason_if_not_mapped")
                      or "outside urban Auckland — no LINZ suburb covers it")
            rows.append({"source_area": name, "linz_suburb": "", "status": "not mapped",
                         "via": "", "reason_if_not_mapped": reason})

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["source_area", "linz_suburb", "status",
                                          "via", "reason_if_not_mapped"])
        w.writeheader()
        w.writerows(rows)
    return rows


def main():
    linz = [f["properties"]["name"] for f in
            json.load(open(os.path.join(DATA, "linz_suburbs.geojson")))["features"]]

    rent_src = {r["area"].strip() for r in
                csv.DictReader(open(os.path.join(DATA, "auckland_rent_sau_2026_06.csv")))}
    crime_src = {r["suburb"].strip() for r in
                 csv.DictReader(open(os.path.join(DATA,
                     "auckland_crime_by_suburb_2025_405.csv")))}

    from collections import Counter
    for label, src, old_name, out_name in [
            ("rent", rent_src, "rent_area_mapping_v2.csv", "rent_area_mapping_linz.csv"),
            ("crime", crime_src, "crime_area_mapping_v2.csv", "crime_area_mapping_linz.csv")]:
        rows = build(src, os.path.join(DATA, old_name),
                     os.path.join(DATA, out_name), linz)
        mapped = [r for r in rows if r["status"] == "mapped"]
        print(f"{label}: {len(mapped)}/{len(rows)} mapped -> {out_name}")
        for k, n in Counter(r["via"] for r in mapped).most_common():
            print(f"    {k:<18}{n:>4}")
        covered = len({r['linz_suburb'] for r in mapped})
        print(f"    reaches {covered} of {len(linz)} LINZ suburbs\n")


if __name__ == "__main__":
    main()
