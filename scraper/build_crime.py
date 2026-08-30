"""Turn the NZ Police "Victimisations Time and Place" export into a tidy CSV.

The export comes out of Tableau as UTF-16 tab-separated, one row per recorded
victimisation rather than one per area — 67,398 rows for 4,408 distinct
area-month pairs. Every area name carries a trailing period ("Ormiston.")
which nothing else in this project uses.

Re-exporting it by hand:
  1. https://public.tableau.com/views/VictimisationsTimeandPlace/Summary
  2. Download tab -> set the Year Month range -> click the dataset row
  3. Download icon -> Data -> Full data -> Download

Usage:  python3 scraper/build_crime.py "~/Downloads/<export>.csv"
"""
import collections
import csv
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
OUT = os.path.join(DATA, "auckland_crime_by_area.csv")

# Tableau writes 1/07/2025 for July 2025 — the day is always 1.
MONTH = re.compile(r"^\d{1,2}/(\d{2})/(\d{4})$")


def main(src):
    rows = list(csv.DictReader(
        io.StringIO(open(os.path.expanduser(src), encoding="utf-16").read()),
        delimiter="\t"))

    counts = collections.defaultdict(collections.Counter)
    months = set()
    for r in rows:
        area = r["Area Unit"].rstrip(".").strip()
        m = MONTH.match(r["Year Month"].strip())
        if not m:
            raise SystemExit(f"unexpected Year Month: {r['Year Month']!r}")
        month = f"{m.group(2)}-{m.group(1)}"          # 2025-07
        months.add(month)
        counts[area][month] += int(r["Number of Victimisations"].replace(",", ""))

    months = sorted(months)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["area", "total"] + months)
        for area in sorted(counts):
            per = counts[area]
            w.writerow([area, sum(per.values())] + [per.get(m, 0) for m in months])

    total = sum(sum(c.values()) for c in counts.values())
    print(f"{os.path.relpath(OUT, REPO)}: {len(counts)} areas, "
          f"{total:,} victimisations, {months[0]} to {months[-1]}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
