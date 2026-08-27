# NewStart NZ

A housing and safety guide for immigrants and students arriving in Auckland, New Zealand.

Combines official rent data with police crime statistics on an interactive map, so newcomers
can weigh cost against safety when choosing where to live.

## What's here

| Path | Description |
| --- | --- |
| `frontend/prototype_v1.html` | Main dashboard — ward/suburb granularity, quadrant scatter, rent & safety rankings |
| `frontend/auckland_map.html` | Dark-theme suburb explorer — rent / crime / combined view modes |
| `frontend/rent_dashboard.html` | Plotly dashboard of 2025 market rent trends |
| `data/auckland_lb.geojson` | Auckland local board boundaries |
| `scraper/fetch_rent.py` | Pulls SAU and ward rent data from the MBIE API into `data/` |
| `scraper/build_dataset.py` | Folds source areas onto 62 suburbs, writes `suburbs.json` + `raw_areas.json` |
| `scraper/inline_data.py` | Inlines the built JSON into the standalone HTML pages |
| `scraper/test_mbie_api.py` | Probe for what the API currently serves |

All frontend files are standalone HTML — open one in a browser, no build step.

## Data sources

**Rent** — [MBIE Market Rent API v2](https://api.business.govt.nz/) (Tenancy Services),
pulled by `scraper/fetch_rent.py`. Statistical area unit and ward level, 12 months ending
June 2026 (covers 2025-07-01 to 2026-06-30). Values shown are medians.

**Crime** — NZ Police [*Victimisations Time and Place*](https://public.tableau.com/views/VictimisationsTimeandPlace/Summary),
exported by hand at area-unit level for calendar 2025. The export has a few traps in it —
see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#refreshing-the-crime-data) before repeating it.

The two datasets use different geographic boundaries, so `rent_area_mapping_v2.csv` and
`crime_area_mapping_v2.csv` fold 556 rent source areas and 416 police source areas onto a
shared set of 62 Auckland suburbs. Coverage: 62/62 have rent figures, 61/62 have crime counts.

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

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — data pipeline, mapping layer, data model,
  frontend structure, and the full list of limitations
- [docs/DEVLOG.md](docs/DEVLOG.md) — 开发日志：踩过的坑和当时的决策理由

## Known gaps

- **Arch Hill** and **Flat Bush** have no rent or crime data — neither appears in the
  source datasets under a matching area name.
- Crime and rent boundaries only approximate each other; suburb-level figures are
  indicative rather than exact.
