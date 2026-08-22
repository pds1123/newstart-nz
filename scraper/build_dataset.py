"""Fold the raw MBIE and NZ Police files onto shared suburbs and emit the
JSON the frontend inlines.

Writes two files:
  data/suburbs.json    62 suburbs, rent and sample by dwelling x bedrooms
  data/raw_areas.json  the unaggregated source areas, for the raw-granularity views

Neither dataset shares a geography with the other or with the names people
actually use, so every source area is resolved through an explicit mapping
table. Fuzzy matching is deliberately avoided: it fails silently, and four
separate outages were traced to it (Mt/Mount, Beach Haven, Saint Heliers, and
Flat Bush appearing as Ormiston).

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
RENT_MAP = os.path.join(DATA, "rent_area_mapping_v2.csv")
CRIME_MAP = os.path.join(DATA, "crime_area_mapping_v2.csv")

DWELLS = ["House", "Apartment", "Flat", "Room", "Boarding House"]
BEDS = ["1", "2", "3", "4", "All"]      # "All" is the source's nBedrms = "NA"


def load_mapping(path):
    out = defaultdict(list)
    for row in csv.DictReader(open(path)):
        if row["status"] == "mapped":
            out[row["master_suburb"]].append(row["source_area"])
    return out


def parent_lookup(path):
    return {r["source_area"]: r["master_suburb"]
            for r in csv.DictReader(open(path)) if r["status"] == "mapped"}


def main():
    rent_map = load_mapping(RENT_MAP)
    crime_map = load_mapping(CRIME_MAP)
    rent_rows = list(csv.DictReader(open(RENT_CSV)))
    crime_raw = {r["suburb"].strip(): int(r["total_crimes_2025"])
                 for r in csv.DictReader(open(CRIME_CSV))}

    # Suburb list, coordinates and zone come from the previous build. They are
    # editorial choices, not derived from the source data.
    previous = json.load(open(os.path.join(DATA, "suburbs.json")))
    meta = {x["suburb"]: (x["lat"], x["lng"], x["zone"]) for x in previous}

    def aggregate(suburb, dwell, bed):
        """Unweighted mean of the member areas' medians, plus their total bonds.

        Unweighted is a simplification — a source area with 4 bonds counts as
        much as one with 400. Weighting by nCurr would be more defensible.
        """
        areas = rent_map.get(suburb, [])
        nbed = "NA" if bed == "All" else bed
        rows = [r for r in rent_rows
                if r["area"].strip() in areas and r["dwell"] == dwell
                and r["nBedrms"] == nbed and r["med"] not in ("", "NA")]
        if not rows:
            return None, None
        med = round(sum(float(r["med"]) for r in rows) / len(rows))
        n = sum(int(r["nCurr"]) for r in rows if r["nCurr"] not in ("", "NA"))
        return med, n

    suburbs = []
    for name, (lat, lng, zone) in meta.items():
        rent, sample = {}, {}
        for dwell in DWELLS:
            rent[dwell], sample[dwell] = {}, {}
            for bed in BEDS:
                med, n = aggregate(name, dwell, bed)
                if med:
                    rent[dwell][bed], sample[dwell][bed] = med, n
        # Zero collapses to null so "no data" never reads as "no crime".
        crime = sum(crime_raw.get(a, 0) for a in crime_map.get(name, [])) or None
        suburbs.append({"suburb": name, "lat": lat, "lng": lng, "zone": zone,
                        "crime_2025": crime, "rent": rent, "n": sample})

    json.dump(suburbs, open(os.path.join(DATA, "suburbs.json"), "w"),
              separators=(",", ":"))

    # Raw source areas for the Rent view / Safety view rankings. `s` is the
    # master suburb an area folds into, used for cross-highlighting only —
    # these areas have no coordinates, so they cannot be drawn on the map.
    rent_parent = parent_lookup(RENT_MAP)
    crime_parent = parent_lookup(CRIME_MAP)

    by_area = defaultdict(lambda: defaultdict(dict))
    for r in rent_rows:
        if r["med"] in ("", "NA"):
            continue
        n = int(r["nCurr"]) if r["nCurr"] not in ("", "NA") else 0
        by_area[r["area"].strip()][r["dwell"]][r["nBedrms"]] = [int(float(r["med"])), n]

    raw = {
        "rent": {a: {"v": dict(v), "s": rent_parent.get(a)}
                 for a, v in sorted(by_area.items())},
        "crime": {a: {"v": c, "s": crime_parent.get(a)}
                  for a, c in sorted(crime_raw.items())},
    }
    json.dump(raw, open(os.path.join(DATA, "raw_areas.json"), "w"),
              separators=(",", ":"))

    have_rent = sum(1 for s in suburbs if any(s["rent"][d] for d in DWELLS))
    have_crime = sum(1 for s in suburbs if s["crime_2025"] is not None)
    print(f"suburbs.json  : {len(suburbs)} suburbs "
          f"({have_rent} with rent, {have_crime} with crime)")
    print(f"raw_areas.json: {len(raw['rent'])} rent areas, {len(raw['crime'])} police areas")
    print("\nNext: inline the JSON into the frontend with")
    print("  python scraper/inline_data.py")


if __name__ == "__main__":
    main()
