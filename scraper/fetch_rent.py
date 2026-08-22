"""Pull Auckland rent statistics from the MBIE Market Rent API into data/.

Run this when a newer period becomes available. The API window moves: periods
that 500 today may work later, and older ones stop working, so check what the
probe in test_mbie_api.py reports before changing PERIOD.

Usage:  python scraper/fetch_rent.py [period-ending]   # default 2026-06
"""
import csv
import os
import sys

import requests
from dotenv import load_dotenv

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO, "scraper", ".env"))

BASE = "https://api.business.govt.nz/gateway/tenancy-services/market-rent/v2"
HEADERS = {
    "Ocp-Apim-Subscription-Key": os.environ["MBIE_API_KEY"],
    "Accept": "application/json",
}

PERIOD = sys.argv[1] if len(sys.argv) > 1 else "2026-06"
MONTHS = 12

# The 13 Auckland wards as ward-2019 names them. These are wards, not the 21
# local boards — different names, different boundaries.
AUCKLAND_WARDS = {
    "Albany Ward", "Albert-Eden-Roskill Ward", "Franklin Ward", "Howick Ward",
    "Manukau Ward", "Manurewa-Papakura Ward", "Maungakiekie-Tamaki Ward",
    "North Shore Ward", "Orakei Ward", "Rodney Ward", "Waitakere Ward",
    "Waitemata and Gulf Ward", "Whau Ward",
}

COLUMNS = ["area", "dwell", "nBedrms", "nLodged", "nClosed", "nCurr",
           "mean", "lq", "med", "uq", "sd", "brr", "lmean", "lsd", "slq", "suq"]


def fetch(area_definition):
    """Returns (rows, periodCovered). SAU-level calls take about a minute."""
    r = requests.get(
        f"{BASE}/statistics",
        headers=HEADERS,
        params={"period-ending": PERIOD, "num-months": MONTHS,
                "area-definition": area_definition},
        timeout=300,
    )
    r.raise_for_status()
    payload = r.json()
    return payload["items"], payload.get("periodCovered")


def write(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    tag = PERIOD.replace("-", "_")

    ward_rows, covered = fetch("ward-2019")
    akl_ward = [r for r in ward_rows if r["area"] in AUCKLAND_WARDS]
    write(akl_ward, os.path.join(REPO, "data", f"auckland_rent_ward_{tag}.csv"))
    print(f"ward : {len(akl_ward):>6,} rows  (national {len(ward_rows):,})  covering {covered}")

    # Only keep source areas the mapping table already knows about.
    mapping = os.path.join(REPO, "data", "rent_area_mapping_v2.csv")
    known = {r["source_area"] for r in csv.DictReader(open(mapping))}
    sau_rows, covered = fetch("statistical-area-unit-2019")
    akl_sau = [r for r in sau_rows if r["area"].strip() in known]
    write(akl_sau, os.path.join(REPO, "data", f"auckland_rent_sau_{tag}.csv"))
    print(f"SAU  : {len(akl_sau):>6,} rows  (national {len(sau_rows):,})  covering {covered}")
    print(f"       {len({r['area'].strip() for r in akl_sau})} source areas of {len(known)} listed")


if __name__ == "__main__":
    main()
