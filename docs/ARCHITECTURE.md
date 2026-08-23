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
| `period-ending` | `2026-06` | Latest available. The window moves: `2025-06` now 500s at this grain while `2026-03` and `2026-06`, which used to fail, succeed. |
| `num-months` | `12` | Rolling window — `periodCovered` reports 2025-07-01/2026-06-30. ~8,347 rows nationally, ~50 s to fetch. |

Fields consumed: `area`, `dwell`, `nBedrms`, `med`, `nCurr`. The file checked in
(`data/auckland_rent_sau_2026_06.csv`) is the Auckland subset — 3,050 rows across 548
source areas. Ward-level figures live in `data/auckland_rent_ward_2026_06.csv`.

`dwell` carries five values, all of which are surfaced: **House**, **Apartment**, **Flat**,
**Room**, and **Boarding House**. The last three matter disproportionately for this
audience — a room runs about $370/wk against $600+ for a house — and excluding them
would hide roughly 13% of active bonds and most of what a student can actually afford.

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

`scraper/build_dataset.py`, run by hand when a source file changes. Per master suburb:

- **Rent** — collect every mapped source area's rows for a given `dwell` × `nBedrms`,
  then take the mean of their medians. (An unweighted mean of medians is a simplification;
  weighting by `nCurr` would be more correct and is not currently done.)
- **Sample** — sum `nCurr` over the same rows.
- **Crime** — sum `total_crimes_2025` over mapped police areas. Zero collapses to `null`,
  so "no data" is never confused with "no crime".

Output is `data/suburbs.json` (~16 KB, 62 suburbs) plus `data/raw_areas.json` (~85 KB, the
unaggregated source areas). `scraper/inline_data.py` writes both into the HTML at the
`const SUBURB_DATA = …` and `const RAW_AREAS = …` assignments — there is no build step, so
the data lives in the file.

The full pipeline is three scripts:

```bash
python3 scraper/fetch_rent.py 2026-06      # API  -> data/auckland_rent_{sau,ward}_2026_06.csv
python3 scraper/build_dataset.py 2026_06   # CSVs -> data/suburbs.json + data/raw_areas.json
python3 scraper/inline_data.py             # JSON -> frontend/*.html
```

### Data model

```jsonc
{
  "suburb": "Mt Eden",
  "lat": -36.883, "lng": 174.753,
  "zone": "inner",              // "inner" (36) | "suburban" (26)
  "crime_2025": 510,            // null when unmapped
  "rent": {                     // weekly median, NZD — five dwelling types
    "House":     { "1": 646, "2": 666, "3": 811, "4": 1081, "All": 847 },
    "Apartment": { "1": 489, "2": 628, "3": 1260, "All": 660 },
    "Flat":      { "1": 460, "2": 571 },
    "Room":      { "1": 245 },
    "Boarding House": {}
  },
  "n": {                        // bonds currently active, same shape as rent
    "House":     { "1": 207, "2": 165, "3": 240, "4": 165, "All": 111 },
    "Apartment": { "1": 243, "2": 243, "3": 24, "All": 6 },
    "Flat":      { "1": 327, "2": 300 },
    "Room":      { "1": 15 },
    "Boarding House": {}
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
    └── panels-col     flex
        ├── toolbar    full width      Quadrant / Rent view / Safety view
        └── panels     flex
            ├── chart  35%             scatter (quadrant) or bar chart (rent/safety)
            └── map    65%             Leaflet + KPI bar overlay
```

Below 1100px the two panels stack vertically.

### State

```js
let currentBed   = '2';   // '1' | '2' | '3' | '4'
let currentDwell = 'All'; // 'All' | 'House' | 'Apartment' | 'Flat' | 'Room' | 'Boarding House'
let currentBudget = 650;  // dims markers above this
let mapMode = 'quadrant'; // 'quadrant' | 'rent' | 'safety'
let selected = null;      // suburb name, drives cross-panel highlight
```

`refresh()` is the single entry point after any filter change:

```
computeMedians() → buildMarkers() → drawChart() → updateKPI() → updateQuadLegend()
```

`drawChart()` dispatches on `mapMode`: the quadrant scatter, or a horizontal bar chart
ranked cheapest-first (rent) or safest-first (safety). Bars scroll inside the panel.

`'All'` spans **whole dwellings only** — House, Apartment, Flat. Room and Boarding House
are priced per room, so folding them into the same median would understate what a place
costs. Selecting either also forces the bedroom filter to 1 and disables the rest, since
shared listings only ever carry a 1-bedroom figure.

### Granularity

A two-stop slider switches every view between **5 regions** and **62 suburbs**; regions are
the default. `units()` returns whichever set is active, and all rendering — map, chart,
KPIs, quadrant counts, search — reads from it. Switching refits the map to the active set,
since five centroids sit far wider apart than 62 suburb markers.

The regions are plain compass groupings — Central, East, South, West, North — covering all
62 suburbs with no overlaps or gaps. They are **not** council wards or local boards. Those
are real boundaries with their own names, and an earlier attempt to use them conflated the
two systems (13 wards vs 21 local boards, different names, different lines). Official
ward-level rent from the API is kept in `data/auckland_rent_ward_2026_06.csv` for reference
but is not what the UI groups by.

Region figures are aggregated from member suburbs:

- **Rent** — `nCurr`-weighted mean of member medians, per dwelling × bedroom combination
- **Crime** — plain sum of member counts
- **Position** — mean of member coordinates (the map draws centroid bubbles, not polygons)

Both metrics therefore cover exactly the same 62 suburbs. Clicking a region drills into
suburb granularity and flies the map to it.

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

The split is strict (`rent < median`), so with an odd number of units the median item falls
on the "not cheap" side, and likewise for crime. Across 62 suburbs this is noise. Across 5
regions it is not: two of the five get pushed off their good side by exactly one place, and
Best value can come out empty. The quadrant view is coarse at region granularity.

`Rent view` and `Safety view` replace quadrant colours with single-metric ramps. Both
stretch across the **filtered range** rather than fixed bounds — a 2-bed slice spanning
$494–$900 rendered as one flat shade under the old fixed $400–$1,100 window. Crime stays
log-scaled (25 to 5,599 would otherwise collapse into a single band). The toolbar states
that the scale is relative so the colours are not read as absolute.

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

---

## Limitations

1. **Crime is absolute, not per capita.** The single biggest threat to the conclusions.
   Auckland Central logs 4,914 incidents and Glendowie 25, but their populations and
   footfall differ by orders of magnitude, so dense suburbs are systematically penalised
   and Auckland Central can never leave the "Not recommended" quadrant. Fixing this needs
   suburb population figures.

2. **Thin slices still produce implausible figures.** The 4 bed+ × Apartment combination
   is the clearest case — Auckland Central reports $302/wk on 15 bonds, which is not what a
   four-bedroom apartment costs and looks like room-by-room lettings mis-categorised at
   source. No sample-size floor is applied; the tooltip shows `nCurr` so the reader can
   judge, but a low count is not yet flagged visually.

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
