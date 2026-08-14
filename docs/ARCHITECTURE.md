# Architecture

Technical reference for NewStart NZ. For the narrative of how it got this way — and the
mistakes along the route — see [DEVLOG.md](DEVLOG.md).

---

## Overview

A static dashboard that puts official rent data and police crime statistics on the same
map of Auckland. There is no backend and no build step: a Python aggregation runs offline,
emits a JSON blob, and that blob is inlined into standalone HTML files.

```
MBIE Market Rent API ──┐
                       ├──> mapping layer ──> aggregation ──> suburbs.json ──> inlined into HTML
NZ Police statistics ──┘
        (offline, run by hand)                                    (browser, zero deps beyond Leaflet)
```

The mapping layer is the substance of the project. Everything else is presentation.

---

## Data sources

### Rent — MBIE Market Rent API v2

```
Base:  https://api.business.govt.nz/gateway/tenancy-services/market-rent/v2
Auth:  Ocp-Apim-Subscription-Key: <key>     # from scraper/.env, never committed
```

| Parameter | Value used | Notes |
| --- | --- | --- |
| `area-definition` | `statistical-area-unit-2019` | Finest grain available. Territorial-authority level is far too coarse. |
| `period-ending` | `2025-12` | Latest that works at SAU grain. `2026-03` returns 500 at this grain. |
| `num-months` | `12` | Rolling 12-month window. ~8,843 rows, 1.7 MB, ~120 s to fetch. |

Fields consumed: `area`, `dwell`, `nBedrms`, `med`, `nCurr`. The file checked in
(`data/auckland_rent_sau_2025_annual.csv`) is the Auckland subset — 3,183 rows across
556 distinct source areas.

`med` (median) is used rather than `mean`. Means are dragged upward by high-end listings
and answer the wrong question for someone asking what they can actually rent.

### Crime — NZ Police

`data/auckland_crime_by_suburb_2025_405.csv` — 405 police areas, 2025 victimisation counts,
two columns (`suburb`, `total_crimes_2025`). Absolute counts, not rates. See
[Limitations](#limitations).

---

## The mapping layer

The two datasets do not share a geography, and neither shares one with the names people
actually use. Reconciliation is done by two exhaustive lookup tables:

| File | Rows | Mapped |
| --- | --- | --- |
| `data/rent_area_mapping_v2.csv` | 556 | 207 |
| `data/crime_area_mapping_v2.csv` | 416 | 220 |

Schema:

```csv
source_area,master_suburb,status,reason_if_not_mapped
Mount Eden East,Mt Eden,mapped,
Saint Heliers North,St Heliers,mapped,
Snells Beach,,not mapped,outer Auckland — outside coverage area
```

Every source area appears exactly once, with `status` either `mapped` or `not mapped` and,
when unmapped, a stated reason. Rows never silently disappear.

**Fuzzy matching is deliberately not used.** It fails silently — a suburb simply comes out
empty and nobody notices until they eyeball the map. Four separate outages traced to this
before the tables became exhaustive (`Mt`/`Mount`, `Beachhaven`/`Beach Haven`,
`St`/`Saint Heliers`, and Flat Bush being called `Ormiston` in the source).

Of the 220 mapped crime areas, 219 match a row in the crime CSV; the mapping file lists
11 areas that do not appear in the data at all.

---

## Aggregation

Offline Python, run by hand when a source file changes. Per master suburb:

- **Rent** — collect every mapped source area's rows for a given `dwell` × `nBedrms`,
  then take the mean of their medians. (An unweighted mean of medians is a simplification;
  weighting by `nCurr` would be more correct and is not currently done.)
- **Sample** — sum `nCurr` over the same rows.
- **Crime** — sum `total_crimes_2025` over mapped police areas. Zero collapses to `null`,
  so "no data" is never confused with "no crime".

Output is `data/suburbs.json` (~16 KB, 62 suburbs) and is inlined into the HTML at the
`const SUBURB_DATA = …` assignment.

### Data model

```jsonc
{
  "suburb": "Mt Eden",
  "lat": -36.883, "lng": 174.753,
  "zone": "inner",              // "inner" (36) | "suburban" (26)
  "crime_2025": 510,            // null when unmapped
  "rent": {                     // weekly median, NZD
    "House":     { "1": 523, "2": 667, "3": 809, "4": 1051, "All": 805 },
    "Apartment": { "1": 500, "2": 623, "3": 1190 }
  },
  "n": {                        // bonds currently active, same shape as rent
    "House":     { "1": 87, "2": 198, "3": 246, "4": 174, "All": 135 },
    "Apartment": { "1": 258, "2": 225, "3": 21 }
  }
}
```

Bedroom keys are `"1"`–`"4"` plus `"All"`. A key is absent when the source has no row —
never zero-filled. `"All"` maps to the source's `nBedrms = "NA"` aggregate row.

---

## Frontend

`frontend/prototype_v1.html` is the current dashboard — a single self-contained file,
Leaflet from CDN, everything else hand-written.

### Layout

```
nav                                    fixed, 52px
└── workspace                          100vh − nav
    ├── sidebar        280px           search · bedrooms · dwelling · budget · quadrant legend
    └── panels         flex, 50/50
        ├── scatter                    hand-built SVG
        └── map                        Leaflet + KPI bar overlay
└── recommend          full width      sortable table, below the fold
```

Below 1100px the two panels stack vertically.

### State

```js
let currentBed   = '2';          // '1' | '2' | '3' | '4'
let currentDwell = 'Apartment';  // 'All' | 'House' | 'Apartment'
let currentBudget = 650;         // dims markers above this
let mapMode = 'quadrant';        // 'quadrant' | 'rent' | 'safety'
let sortKey = 'score', sortDir = -1;
let selected = null;             // suburb name, drives cross-panel highlight
```

`refresh()` is the single entry point after any filter change:

```
computeMedians() → buildMarkers() → drawScatter() → updateKPI() → updateQuadLegend() → renderTable()
```

`'All'` dwelling averages House and Apartment for the selected bedroom count; `getSample`
sums rather than averages over the same pair.

### Quadrant model

Suburbs are classified against the **median rent and median crime of the currently
filtered slice**, recomputed on every filter change:

| Rent | Safety | Class | Colour |
| --- | --- | --- | --- |
| below median | below median crime | Best value | `#1D9E75` |
| at/above median | below median crime | Premium | `#5B8DEF` |
| below median | at/above median crime | Budget | `#EF9F27` |
| at/above median | at/above median crime | Not recommended | `#E24B4A` |
| missing either | — | No data | `#C9C6BE` |

Because the medians move with the filter, a class is a **relative position within the
current price bracket**, not an absolute verdict. Switching from 2-bed to 4-bed reshuffles
the whole board.

`Rent view` and `Safety view` replace quadrant colours with single-metric ramps — linear
$400–$1,100 for rent, log-scaled for crime (the range spans 25 to 5,599, so a linear ramp
would collapse almost everything into one band).

### Scatter plot

Hand-built SVG, no charting library — the project is zero-build, and generating the plot
directly costs about 80 lines.

- **X** — weekly rent, linear, snapped to $50 bounds
- **Y** — crime on a log scale, inverted so upward means safer
- **Radius** — `4 + sqrt(n / nMax) * 9`, area-proportional to bonds lodged
- Quadrant tints at 4.5% opacity, dashed median split lines, corner labels

### Cross-panel linking

`highlightDot()` and `highlightMarker()` mirror hover state between scatter and map;
`selectSuburb(name, panMap)` sets `selected`, optionally flies the map, and re-renders all
three views. Dots carry `data-suburb` and are looked up with `CSS.escape` (suburb names
contain spaces).

### Recommendation scoring

```js
score = ((N − rentRank + 1) + (N − safeRank + 1)) / 2
```

Both ranks ascend from 1 (cheapest, safest), so the cheapest and safest suburb scores
highest on both terms. Suburbs missing either metric are excluded outright and the count
is surfaced in the subheading rather than hidden.

---

## Limitations

1. **Crime is absolute, not per capita.** The single biggest threat to the conclusions.
   Auckland Central logs 4,914 incidents and Glendowie 25, but their populations and
   footfall differ by orders of magnitude, so dense suburbs are systematically penalised
   and Auckland Central can never leave the "Not recommended" quadrant. Fixing this needs
   suburb population figures.

2. **The 4 bed+ × Apartment slice is not trustworthy.** Only two suburbs carry a value —
   $240/wk (Onehunga, n=12) and $269/wk (Auckland Central, n=39). Four-bedroom apartments
   do not rent for $240, and n=39 rules out small-sample noise; these look like
   room-by-room lettings mis-categorised at source. Left unfiltered rather than quietly
   discarded.

3. **Boundaries only approximate each other.** SAU and police areas are differently shaped,
   so folding both onto one suburb necessarily introduces error. Figures are indicative.

4. **Coverage is 70%.** The 62 suburbs account for 55,970 of Auckland's 79,812 incidents.
   The remainder sits in outer areas (Papakura, Pukekohe, Waiheke) that are out of scope.

5. **Flat Bush has no crime figure.** Rent arrives via Ormiston, but the police mapping
   assigns Ormiston to Botany. Moving it would distort Botany, and a single police area
   would understate Flat Bush badly enough to render it falsely "safe". Left null.

6. **Rent aggregation is an unweighted mean of medians.** A source area with 4 bonds counts
   as much as one with 400. Weighting by `nCurr` would be more defensible.

---

## Reproducing

```bash
cd scraper
python3 -m venv venv && source venv/bin/activate
pip install requests python-dotenv
cp .env.example .env    # add your MBIE subscription key
python test_mbie_api.py
```

The frontend needs no server — open any file in `frontend/` directly in a browser.
To preview over HTTP instead:

```bash
python3 -m http.server 8777
```

Then visit `http://localhost:8777/frontend/prototype_v1.html`.
