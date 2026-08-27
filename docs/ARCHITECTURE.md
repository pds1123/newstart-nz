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
two columns (`suburb`, `total_crimes_2025`).

The counts are absolute, so the frontend divides by LINZ population to get **victimisations
per 1,000 residents**, and every ranking, colour and quadrant uses the rate. Absolute counts
are not comparable across areas of wildly different size — a region holding one suburb posts
the lowest total by construction, which is what made the CBD read as Auckland's safest area.
The raw count is still shown alongside the rate in the tooltip.

### Boundaries and population — LINZ

[NZ Suburbs and Localities](https://data.linz.govt.nz/layer/113764-nz-suburbs-and-localities/),
CC BY 4.0. *Sourced from the LINZ Data Service and licensed for reuse under CC BY 4.0.*

This dataset defines the suburb list itself — the names people write on addresses, which is
what the audience uses — plus polygon boundaries and Stats NZ population estimates. Filtering
to `type = Suburb` and `major_name = Auckland` gives the 172 urban suburbs; the rest of the
export is coastal bays, islands, lakes and outer localities.

`scraper/build_linz_suburbs.py` writes `data/linz_suburbs.geojson`. LINZ captures urban
boundaries at 0.1–1 m, which inlines at 12 MB, so rings are thinned with Douglas-Peucker to
about 22 m and rounded to four decimal places — 306 KB, and invisible at the zoom levels this
map uses. Centroids are computed from the full-precision rings before thinning.

### Refreshing the crime data

The crime file is exported by hand from the Tableau report; there is no API. Set **Region**
to `Auckland Region`, **Territorial Authority** to `Auckland`, and **Boundary to display**
to `Area Unit` — the mapping table is built against area units, so no other boundary joins.

Take the **Data** download, not Crosstab. Crosstab exports the table as displayed, which on
this dashboard is an hour-by-weekday grid containing no geography at all. Select the
**Table ST** worksheet, open its data window, switch to the **Full Data** tab and download
from there. A correct export is named `Table ST_..._data.csv` with three columns:
`Area Unit`, `Year Month`, `Number of Victimisations`.

Three things about that file will silently break a join:

| Trap | Fix |
| --- | --- |
| UTF-16, tab-separated | Decode as `utf-16`, split on `\t` — not UTF-8 CSV |
| Area names carry a trailing full stop (`Inlet-Waitemata Harbour.`) | `rstrip('.')` before matching |
| Summing yields 416 areas, 11 of them water or islands | Drop the `Inlet-*`, `Tidal-*`, `Oceanic-*`, marina and Waiheke entries |

Aggregate to `suburb,total_crimes_2025`. Reconstructing this from the committed file
reproduced all 405 rows exactly, so the procedure is known-good rather than inferred.

---

## The mapping layer

The two datasets do not share a geography, and neither shares one with the names people
actually use. Reconciliation is done by two exhaustive lookup tables:

| File | Rows | Mapped |
| --- | --- | --- |
| `data/rent_area_mapping_linz.csv` | 548 | 348 |
| `data/crime_area_mapping_linz.csv` | 405 | 248 |

`scraper/build_linz_mappings.py` resolves each source area by four explicit rules, recording
which one fired in a `via` column so nothing resolves silently:

| via | Rule | Rent | Crime |
| --- | --- | --- | --- |
| `exact` | Name matches a LINZ suburb once macrons and Mt/Saint are folded | 55 | 63 |
| `previous-mapping` | Carried through the earlier 62-suburb table | 179 | 159 |
| `strip-direction` | `Mount Eden West` → `Mount Eden` | 106 | 13 |
| `manual` | Decided by hand, listed in the script | 8 | 13 |

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

Unmapped rows are outer or rural areas that no LINZ urban suburb covers. Coverage reaches
149 of 172 suburbs for rent and 114 for crime; the remainder render as "no data" rather than
being dropped.

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
  "suburb": "Mount Eden",
  "lat": -36.87671, "lng": 174.7615,   // centroid of the LINZ boundary
  "region": "Central",                 // compass grouping
  "population": 26947,                 // Stats NZ estimate via LINZ
  "crime_2025": 510,                   // absolute; the UI divides by population
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
let currentBed   = '2';     // '1' | '2' | '3' | '4'
let currentDwell = 'All';   // 'All' | 'House' | 'Apartment' | 'Flat' | 'Room' | 'Boarding House'
let currentBudget = 650;    // dims markers above this
let mapMode = 'quadrant';   // 'quadrant' | 'rent' | 'safety'

let granularity = 'region'; // 'region' | 'suburb' | 'raw'
let GRAN_STOPS = [...];     // stops the current view offers; the raw stop is
                            // added only in the ranking views
let scope = null;           // parent unit drilled into; narrows the level below
let UNITS = [];             // whatever the active granularity renders
let selected = null;        // drives cross-panel highlight at the finest stop
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

A slider switches granularity; regions are the default. `units()` returns whichever set is
active, and all rendering — map, chart, KPIs, quadrant counts, search — reads from it.
Switching refits the map to the active set, since six centroids sit far wider apart than
62 suburb markers.

The stops depend on the view:

| View | Stops |
| --- | --- |
| Quadrant | Regions (6) · Suburbs (62) |
| Rent view | Regions (6) · Suburbs (62) · Raw (548 statistical areas) |
| Safety view | Regions (6) · Suburbs (62) · Raw (405 police areas) |

The quadrant scatter has no raw stop because a point needs both a rent and a crime value,
and the two datasets' raw areas are different geographies — there is nothing to join on.
`GRAN_STOPS` holds the active list, and asking for a stop the current view does not offer
falls back to suburbs. At the raw stop the map stays on suburbs, since source areas have
no coordinates; a banner says so.

The regions are CBD plus five compass groupings — Central, East, South, West, North —
covering all 62 suburbs with no overlaps or gaps. CBD holds Auckland Central alone, which
already aggregates the whole city centre (Queen Street, Britomart, Viaduct, Wynyard,
Shortland Street, Victoria Park, Hobson Ridge, Freemans Bay). They are **not** council wards or local boards. Those
are real boundaries with their own names, and an earlier attempt to use them conflated the
two systems (13 wards vs 21 local boards, different names, different lines). Official
ward-level rent from the API is kept in `data/auckland_rent_ward_2026_06.csv` for reference
but is not what the UI groups by.

Region figures are aggregated from member suburbs:

- **Rent** — `nCurr`-weighted mean of member medians, per dwelling × bedroom combination
- **Crime** — plain sum of member counts
- **Position** — mean of member coordinates (the map draws centroid bubbles, not polygons)

Both metrics therefore cover exactly the same 62 suburbs.

### Drilling

Clicking any unit steps down one stop and narrows to what was clicked, tracked in `scope`:

```
Regions ──click East──> Suburbs (East's 16) ──click Howick──> Raw (Howick's 3 areas)
```

At the finest stop a click only selects, since there is nowhere further to go. `scope`
filters the chart, the map and the KPIs together, so the numbers describe the drilled-into
area rather than all of Auckland. Dragging the slider clears it, as does the *Show all*
button on the scope bar. At the raw stop the map holds the single scoped suburb — the
source areas themselves cannot be drawn.

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

Ordered by how much they threaten the conclusions.

1. **Crime is absolute, not per capita.** The single biggest threat. Auckland Central logs
   4,914 incidents and Glendowie 25, but their populations and footfall differ by orders of
   magnitude, so dense areas are systematically penalised. Fixing this needs suburb
   population figures.

2. **Region crime is a plain sum, so regions of different sizes are not comparable.** A
   direct consequence of the point above, and CBD makes it visible: holding one suburb, it
   posts the lowest regional total (4,914) and therefore reads as *safest*, while Auckland
   Central ranks second-highest for incidents among all 62 suburbs. Per member suburb it is
   the worst region by a factor of three.

   | Region | Suburbs | Crime total | Per suburb |
   | --- | --- | --- | --- |
   | CBD | 1 | 4,914 | **4,914** |
   | Central | 11 | 6,758 | 614 |
   | East | 16 | 7,672 | 480 |
   | South | 12 | 18,864 | 1,572 |

3. **Social housing depresses some medians.** Glen Innes East-Wai O Taiki Bay reports
   $194/wk for a 2-bedroom house on 219 bonds, with a lower quartile of $127. These are
   Kāinga Ora tenancies on income-related rent (25% of income), not market listings. Only
   four source areas show the pattern and three fall outside coverage, but Glen Innes lands
   at $404 — the mean of $194 and $615 — which is not obtainable privately. Left as-is:
   MBIE carries no field distinguishing social from private tenancies.

4. **Suburb coordinates are hand-placed.** The `lat`/`lng` in `suburbs.json` come from a
   hardcoded dictionary, not from any authoritative source — decimal precision varies from
   two to four places. Every marker lands somewhere plausible, but these are eyeballed
   positions, not centroids. LINZ's NZ Suburbs and Localities dataset would fix this and
   simultaneously unlock choropleth polygons and point-in-polygon address lookup.

5. **Sparse filter combinations still produce implausible figures.** 4 bed+ × Apartment is
   the clearest case — Auckland Central reports $302/wk on 15 bonds, which looks like
   room-by-room lettings mis-categorised at source. No sample-size floor is applied; the
   tooltip shows `nCurr` so the reader can judge, but a low count carries no visual flag.

6. **Boundaries only approximate each other.** SAU and police areas are differently shaped,
   so folding both onto one suburb necessarily introduces error. Figures are indicative.

7. **Coverage is 70%.** The 62 suburbs account for 55,970 of Auckland's 79,812 incidents.
   The remainder sits in outer areas (Papakura, Pukekohe, Waiheke) that are out of scope.

8. **Flat Bush has no crime figure.** Rent arrives via Ormiston, but the police mapping
   assigns Ormiston to Botany. Moving it would distort Botany, and a single police area
   would understate Flat Bush badly enough to render it falsely "safe". Left null.

9. **Rent aggregation is an unweighted mean of medians.** A source area with 4 bonds counts
   as much as one with 400. Weighting by `nCurr` would be more defensible. Region-level
   aggregation *does* weight by `nCurr`; suburb-level does not.

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
