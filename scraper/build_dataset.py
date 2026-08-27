"""Fold the raw MBIE and NZ Police files onto LINZ suburbs and emit the JSON
the frontend inlines.

Writes:
  data/suburbs.json    172 LINZ suburbs — rent, sample, crime, population,
                       region, and a centroid computed from the real boundary
  data/raw_areas.json  the unaggregated source areas, for the raw-granularity views

Neither source dataset shares a geography with LINZ, so every source area is
resolved through an explicit mapping table (see build_linz_mappings.py).
Fuzzy matching is deliberately avoided: it fails silently, and four separate
outages were traced to it before the tables became exhaustive.

Usage:  python scraper/build_dataset.py [period-tag]   # default 2026_06
"""
import csv
import json
import os
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
TAG = sys.argv[1] if len(sys.argv) > 1 else "2026_06"

RENT_CSV = os.path.join(DATA, f"auckland_rent_sau_{TAG}.csv")
CRIME_CSV = os.path.join(DATA, "auckland_crime_by_suburb_2025_405.csv")
RENT_MAP = os.path.join(DATA, "rent_area_mapping_linz.csv")
CRIME_MAP = os.path.join(DATA, "crime_area_mapping_linz.csv")
SUBURBS_GEO = os.path.join(DATA, "linz_suburbs.geojson")

DWELLS = ["House", "Apartment", "Flat", "Room", "Boarding House"]
BEDS = ["1", "2", "3", "4", "All"]      # "All" is the source's nBedrms = "NA"


def load_mapping(path):
    out = defaultdict(list)
    for row in csv.DictReader(open(path)):
        if row["status"] == "mapped":
            out[row["linz_suburb"]].append(row["source_area"])
    return out


def parent_lookup(path):
    return {r["source_area"]: r["linz_suburb"]
            for r in csv.DictReader(open(path)) if r["status"] == "mapped"}


def main():
    rent_map = load_mapping(RENT_MAP)
    crime_map = load_mapping(CRIME_MAP)
    rent_rows = list(csv.DictReader(open(RENT_CSV)))
    crime_raw = {r["suburb"].strip(): int(r["total_crimes_2025"])
                 for r in csv.DictReader(open(CRIME_CSV))}

    geo = json.load(open(SUBURBS_GEO))

    def aggregate(suburb, dwell, bed):
        """Returns [median, lower quartile, upper quartile, bonds] or None.

        The quartiles are what a suburb median alone cannot say: how much the
        rents inside it actually vary. A wide spread is also a warning sign —
        Glen Innes runs $127 to $640 for the same dwelling because market and
        income-related social housing rents are pooled together.

        Each is an unweighted mean across the member source areas, which is a
        simplification: an area with 4 bonds counts as much as one with 400.
        """
        areas = rent_map.get(suburb, [])
        nbed = "NA" if bed == "All" else bed
        rows = [r for r in rent_rows
                if r["area"].strip() in areas and r["dwell"] == dwell
                and r["nBedrms"] == nbed and r["med"] not in ("", "NA")]
        if not rows:
            return None

        def avg(field):
            vals = [float(r[field]) for r in rows if r[field] not in ("", "NA")]
            return round(sum(vals) / len(vals)) if vals else None

        med = avg("med")
        n = sum(int(r["nCurr"]) for r in rows if r["nCurr"] not in ("", "NA"))
        return [med, avg("lq"), avg("uq"), n]

    suburbs = []
    for feat in geo["features"]:
        p = feat["properties"]
        name = p["name"]
        rent = {}
        for dwell in DWELLS:
            rent[dwell] = {}
            for bed in BEDS:
                cell = aggregate(name, dwell, bed)
                if cell and cell[0]:
                    rent[dwell][bed] = cell
        # Zero collapses to null so "no data" never reads as "no crime".
        crime = sum(crime_raw.get(a, 0) for a in crime_map.get(name, [])) or None
        suburbs.append({
            "suburb": name,
            "lat": p["lat"], "lng": p["lng"],
            "region": p["region"],
            "population": p["population"],
            "crime_2025": crime,
            "rent": rent,        # dwell -> bed -> [median, lq, uq, bonds]
        })

    json.dump(suburbs, open(os.path.join(DATA, "suburbs.json"), "w"),
              separators=(",", ":"), ensure_ascii=False)

    # Raw source areas for the Rent view / Safety view rankings. `s` is the
    # LINZ suburb an area folds into, used for cross-highlighting only — these
    # areas have no coordinates, so they cannot be drawn on the map.
    rent_parent = parent_lookup(RENT_MAP)
    crime_parent = parent_lookup(CRIME_MAP)

    by_area = defaultdict(lambda: defaultdict(dict))
    for r in rent_rows:
        if r["med"] in ("", "NA"):
            continue
        n = int(r["nCurr"]) if r["nCurr"] not in ("", "NA") else 0
        lq = int(float(r["lq"])) if r["lq"] not in ("", "NA") else None
        uq = int(float(r["uq"])) if r["uq"] not in ("", "NA") else None
        by_area[r["area"].strip()][r["dwell"]][r["nBedrms"]] = [int(float(r["med"])), lq, uq, n]

    raw = {
        "rent": {a: {"v": dict(v), "s": rent_parent.get(a)}
                 for a, v in sorted(by_area.items())},
        "crime": {a: {"v": c, "s": crime_parent.get(a)}
                  for a, c in sorted(crime_raw.items())},
    }
    json.dump(raw, open(os.path.join(DATA, "raw_areas.json"), "w"),
              separators=(",", ":"), ensure_ascii=False)

    have_rent = sum(1 for s in suburbs if any(s["rent"][d] for d in DWELLS))
    have_crime = sum(1 for s in suburbs if s["crime_2025"] is not None)
    have_pop = sum(1 for s in suburbs if s["population"])
    print(f"suburbs.json  : {len(suburbs)} suburbs "
          f"({have_rent} with rent, {have_crime} with crime, {have_pop} with population)")
    print(f"raw_areas.json: {len(raw['rent'])} rent areas, {len(raw['crime'])} police areas")


if __name__ == "__main__":
    main()
