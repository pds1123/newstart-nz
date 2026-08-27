# NewStart NZ

A housing and safety guide for immigrants and students arriving in Auckland, New Zealand.

Combines official rent data with police crime statistics on an interactive map, so newcomers
can weigh cost against safety when choosing where to live.

## What's here

| Path | Description |
| --- | --- |
| `frontend/prototype_v1.html` | Main dashboard — a board of tiles: map, rent and safety rankings, spread, region comparison, scatter |
| `frontend/auckland_map.html` | Dark-theme suburb explorer — rent / crime / combined view modes |
| `frontend/rent_dashboard.html` | Plotly dashboard of 2025 market rent trends |
| `data/linz_suburbs.geojson` | LINZ suburb polygons, population and regions |
| `scraper/build_linz_suburbs.py` | Builds that file from the LINZ export |
| `scraper/build_linz_mappings.py` | Rebuilds the source-area mapping tables against LINZ names |
| `scraper/fetch_rent.py` | Pulls SAU and ward rent data from the MBIE API into `data/` |
| `scraper/build_dataset.py` | Folds source areas onto the LINZ suburbs, writes `suburbs.json`, `source_areas.json` (the fold, per suburb) and `raw_areas.json` |
| `scraper/inline_data.py` | Inlines the built JSON into the standalone HTML pages |
| `scraper/test_mbie_api.py` | Probe for what the API currently serves |

All frontend files are standalone HTML — open one in a browser, no build step.

## Data sources

**Rent** — [MBIE Market Rent API v2](https://api.business.govt.nz/) (Tenancy Services),
pulled by `scraper/fetch_rent.py`. Statistical area unit and ward level, 12 months ending
June 2026 (covers 2025-07-01 to 2026-06-30). Both the median and the mean are
carried, along with the lower and upper quartiles and the active bond count.

**Crime** — NZ Police [*Victimisations Time and Place*](https://public.tableau.com/views/VictimisationsTimeandPlace/Summary),
exported by hand at area-unit level for calendar 2025. The export has a few traps in it —
see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#refreshing-the-crime-data) before repeating it.

**Boundaries and population** — LINZ
[NZ Suburbs and Localities](https://data.linz.govt.nz/layer/113764-nz-suburbs-and-localities/),
CC BY 4.0. Supplies the suburb list itself, polygon boundaries, centroids and Stats NZ
population estimates. *Sourced from the LINZ Data Service and licensed for reuse under
CC BY 4.0.*

The three datasets use different geographic boundaries, so `rent_area_mapping_linz.csv` and
`crime_area_mapping_linz.csv` fold 548 rent source areas and 405 police source areas onto
the 172 LINZ suburbs of urban Auckland. Coverage: 153/172 have rent figures, 123/172 have
crime counts, 170/172 have population. Suburbs with no data are shown as such rather than
dropped.

Those folds are not tidy, so the page lets you open one up. Picking a suburb and then a
dataset turns that dataset's ranking into a list of the source areas behind the suburb's
figure: Glen Innes reads $517 for a 2-bedroom
house, which is $194 in one MBIE area and $618 in the other. The two datasets have to be
viewed one at a time, because 74 of the 123 suburbs carrying both are built from a
different *number* of source areas on each side — there is no row that could honestly hold
a rent figure and a crime figure together.

## Running the scraper

```bash
cd scraper
python3 -m venv venv && source venv/bin/activate
pip install requests python-dotenv
cp .env.example .env   # then add your MBIE key
```

Rebuild the dataset end to end (from the repo root):

```bash
python3 scraper/fetch_rent.py 2026-06 && python3 scraper/build_dataset.py 2026_06 && python3 scraper/inline_data.py
```

`fetch_rent.py` takes about a minute — the SAU request is large. The available
period window moves, so run `python3 scraper/test_mbie_api.py` first to see what
the API currently serves.
