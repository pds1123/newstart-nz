# NewStart NZ

A housing and safety guide for immigrants and students arriving in Auckland, New Zealand.

Combines official rent data with police crime statistics on an interactive map, so newcomers
can weigh cost against safety when choosing where to live.

## What's here

| Path | Description |
| --- | --- |
| `frontend/prototype_v1.html` | Light-theme prototype — search, bedroom/dwelling filters, budget slider, top-10 leaderboard |
| `frontend/auckland_map.html` | Dark-theme suburb explorer — rent / crime / combined view modes |
| `frontend/rent_dashboard.html` | Plotly dashboard of 2025 market rent trends |
| `data/auckland_lb.geojson` | Auckland local board boundaries |
| `scraper/test_mbie_api.py` | MBIE Market Rent API client |

All frontend files are standalone HTML — open one in a browser, no build step.

## Data sources

- **Rent** — [MBIE Market Rent API v2](https://api.business.govt.nz/) (Tenancy Services).
  Statistical Area Unit level, 12 months ending December 2025. Values shown are medians.
- **Crime** — NZ Police victimisation statistics by suburb, 2025.

The two datasets use different geographic boundaries, so `rent_area_mapping_v2.csv` and
`crime_area_mapping_v2.csv` fold 556 rent source areas and 416 police source areas onto a
shared set of 63 Auckland suburbs. Coverage: 59/63 have rent figures, 61/63 have crime counts.

## Running the scraper

```bash
cd scraper
python3 -m venv venv && source venv/bin/activate
pip install requests python-dotenv
cp .env.example .env   # then add your MBIE key
python test_mbie_api.py
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — data pipeline, mapping layer, data model,
  frontend structure, and the full list of limitations
- [docs/DEVLOG.md](docs/DEVLOG.md) — 开发日志：踩过的坑和当时的决策理由

## Known gaps

- **Arch Hill** and **Flat Bush** have no rent or crime data — neither appears in the
  source datasets under a matching area name.
- Crime and rent boundaries only approximate each other; suburb-level figures are
  indicative rather than exact.
