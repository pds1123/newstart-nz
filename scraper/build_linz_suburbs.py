"""Build the suburb list, boundaries and regions from LINZ NZ Suburbs and Localities.

Replaces the earlier hand-curated 62-suburb list. Emits:
  data/linz_suburbs.geojson   polygons + population, one feature per suburb
  data/linz_regions.json      suburb -> compass region

Source: https://data.linz.govt.nz/layer/113764-nz-suburbs-and-localities/
        CC BY 4.0, exported as CSV (WKT geometry) clipped to Auckland.
"""
import csv
import json
import os
import re
import sys
import unicodedata as ud

csv.field_size_limit(sys.maxsize)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.expanduser(
    "~/Downloads/lds-nz-suburbs-and-localities-CSV/nz-suburbs-and-localities.csv")

# Only urban Auckland: major_name filters out Pukekohe, Waiheke, Warkworth etc.
MAJOR = "Auckland"


def norm(s):
    """Fold macrons and Mt/Mount, St/Saint so old names match LINZ spellings."""
    s = ud.normalize("NFD", s)
    s = "".join(c for c in s if not ud.combining(c))
    s = s.lower().replace("mount ", "mt ").replace("saint ", "st ")
    return "".join(ch for ch in s if ch.isalnum())


def rings(wkt):
    """WKT MULTIPOLYGON/POLYGON -> list of rings, each a list of [lng, lat]."""
    out = []
    for ring in re.findall(r"\(([-\d\.,\s]+)\)", wkt):
        pts = [[float(a), float(b)] for a, b in
               re.findall(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", ring)]
        if len(pts) >= 4:
            out.append(pts)
    return out


# LINZ captures urban boundaries at 0.1-1m. A city map needs nothing like that,
# and the raw geometry inlines at 12 MB, so rings are thinned with
# Douglas-Peucker to roughly 22 m before being rounded to 4 decimal places.
SIMPLIFY_TOLERANCE = 0.0002


def _perp(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return ((x - (x1 + t * dx)) ** 2 + (y - (y1 + t * dy)) ** 2) ** 0.5


def _dp(pts, tol):
    if len(pts) < 3:
        return pts
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        d = _perp(pts[i], pts[0], pts[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > tol:
        return _dp(pts[:idx + 1], tol)[:-1] + _dp(pts[idx:], tol)
    return [pts[0], pts[-1]]


def simplify(rs, tol=SIMPLIFY_TOLERANCE):
    out = []
    for ring in rs:
        s = [[round(x, 4), round(y, 4)] for x, y in _dp(ring, tol)]
        dedup = [s[0]]
        for pt in s[1:]:
            if pt != dedup[-1]:
                dedup.append(pt)
        if len(dedup) >= 4:
            out.append(dedup)
    return out


def centroid(rs):
    pts = [p for r in rs for p in r]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def load_previous_regions():
    """Seed regions from the hand-made assignments already in the frontend."""
    html = open(os.path.join(REPO, "frontend", "index.html")).read()
    blk = re.search(r"const REGION_SUBURBS = \{(.*?)\n\};", html, re.S).group(1)
    out = {}
    for m in re.finditer(r"'([^']+)':\s*\[(.*?)\]", blk, re.S):
        for s in re.findall(r"'([^']+)'", m.group(2)):
            out[norm(s)] = m.group(1)
    return out


def main():
    rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))
            if r["type"] == "Suburb" and r["major_name"] == MAJOR]

    for r in rows:
        full = rings(r["WKT"])
        r["lng"], r["lat"] = centroid(full)   # centroid off the full-precision ring
        r["rings"] = simplify(full)

    old = load_previous_regions()
    seed = [r for r in rows if norm(r["name"]) in old]
    for r in seed:
        r["region"] = old[norm(r["name"])]

    # Everything else inherits from its nearest already-classified neighbour.
    # Longitude is scaled because a degree of it is shorter than a degree of
    # latitude at this distance from the equator.
    for r in rows:
        if "region" in r:
            continue
        near = min(seed, key=lambda s: (s["lat"] - r["lat"]) ** 2
                   + ((s["lng"] - r["lng"]) * 0.8) ** 2)
        r["region"] = "Central" if near["region"] == "CBD" else near["region"]

    # Nearest-neighbour drags far South Auckland into East, because Flat Bush
    # sits in East and is the closest anchor to all of it. Latitude overrides.
    for r in rows:
        if r["lat"] < -36.97 and r["region"] == "East":
            r["region"] = "South"

    features = []
    for r in sorted(rows, key=lambda r: r["name"]):
        pop = r["population_estimate"]
        features.append({
            "type": "Feature",
            "properties": {
                "name": r["name"],
                "region": r["region"],
                "population": int(pop) if pop else None,
                "lat": round(r["lat"], 5),
                "lng": round(r["lng"], 5),
            },
            "geometry": {"type": "MultiPolygon",
                         "coordinates": [[ring] for ring in r["rings"]]},
        })

    geo = {"type": "FeatureCollection", "features": features}
    with open(os.path.join(REPO, "data", "linz_suburbs.geojson"), "w") as f:
        json.dump(geo, f, separators=(",", ":"))

    regions = {r["name"]: r["region"] for r in sorted(rows, key=lambda r: r["name"])}
    with open(os.path.join(REPO, "data", "linz_regions.json"), "w") as f:
        json.dump(regions, f, ensure_ascii=False, indent=1)

    from collections import Counter
    print(f"{len(rows)} suburbs")
    for k, n in Counter(r["region"] for r in rows).most_common():
        print(f"  {k:<9}{n:>4}")
    pts = sum(len(ring) for r in rows for ring in r["rings"])
    kb = os.path.getsize(os.path.join(REPO, "data", "linz_suburbs.geojson")) / 1024
    print(f"\npopulation total {sum(int(r['population_estimate'] or 0) for r in rows):,}")
    print(f"geometry {pts:,} points, {kb:.0f} KB after simplification")


if __name__ == "__main__":
    main()
