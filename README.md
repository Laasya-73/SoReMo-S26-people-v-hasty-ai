# SoReMo '26 | The People v. Hasty AI Development

## Illinois Data Center Impact Platform

This project maps Illinois data center growth and contextualizes it with community, environmental, and energy-burden signals.

It is now fully web-based using a JavaScript mapping stack (no Streamlit/Folium runtime).

## What This Platform Includes

Single app entry:

- `/` Home workspace launcher

Main workspaces:

- `/map` Illinois Map
- `/briefing` County Intelligence Briefing
- `/studio` Impact Scenario Studio
- `/registry` Data Center Registry Explorer (US + global)

## Tech Stack

- Frontend: Svelte + Vite
- Mapping/rendering: MapLibre GL + deck.gl (`GeoJsonLayer`, `ScatterplotLayer`)
- Data export pipeline: Python (`pandas`, `geopandas`, `pyxlsb`)
- Exports: Markdown + PDF (`jspdf`)

## Current Features

### 1) Illinois Map (`/map`)

- Scenario toggle:
  - `Planned buildout (existing + proposed + inventory + denied)`
  - `Current footprint (existing only)`
- County layer selector with dedicated color scales:
  - Community Impact Score
  - Data Center Pressure Score
  - Economic Vulnerability 2.0
  - Cumulative Burden (Air + Energy)
  - Social & Environmental Justice Index (EPA EJScreen + CDC SVI)
  - Poverty Rate
  - Minority Population
  - AQI P90
  - Ozone Days
  - PM2.5 Days
  - Energy Burden
  - Avg Annual Energy Cost
  - Electricity Use (MWh per capita)
  - Water Stress Index / Aqueduct water-risk layers
  - Grid clean/fossil share + carbon intensity layers
  - Heat + Climate Stress layers (NOAA + FEMA NRI)
  - Noise + Community Impact layers (FAA + Chicago 311 + EPA TRI)
  - Land Use + Zoning layers:
    - Land cover (Urban/Built-up, Agricultural, Forested, Wetland)
    - Zoning Allowance Index
    - Zoning Annoyance Threshold Index
    - Sites Near Residential Zoning (500m share)
- Basemap switcher (Light / Color / Dark)
- Layer controls:
  - Existing, Proposed, Denied, Inventory, County outlines
  - Layer opacity and point size
- County explorer:
  - Zoom-to-county selector
  - Named jump views (Illinois, Chicago, Elk Grove, DeKalb, Naperville)
- Rich county/site interaction:
  - Selected county card
  - Top indicators
  - Data quality/confidence
  - Watchlist flag when thresholds are triggered
- URL state persistence for map controls (shareable state via query params)

### 2) County Intelligence Briefing (`/briefing`)

- Generates county-specific brief content from selected scenario + focus lens.
- Focus lenses:
  - Balanced overview
  - Environmental stress
  - Economic vulnerability
  - Public hearing prep
- Includes:
  - Executive summary metrics
  - Key signal cards
  - Decision prompts
  - Statewide benchmark cards (percentile context)
  - Data quality + confidence section
  - Peer county comparison
  - Pressure formula explanation + contribution breakdown
  - Watchlist alerts (when applicable)
- Export:
  - `Download Brief (.md)`
  - `Download Brief (.pdf)`

### 3) Impact Scenario Studio (`/studio`)

- Runs what-if simulations for a selected county.
- Inputs:
  - Retire existing
  - Add proposed
  - Cancel proposed
  - Add inventory
  - Remove inventory
  - Add denied
- Outputs:
  - Baseline vs projected pressure
  - Pressure delta
  - Standing shift vs statewide benchmark
  - Data quality + confidence
  - Peer comparison
  - Formula decomposition (baseline vs projected)
  - Watchlist alerting
- Export:
  - `Download Note (.md)`
  - `Download Note (.pdf)`

### 4) Data Center Registry Explorer (`/registry`)

- Separate workspace for broad infrastructure lookup (not mixed into county brief/studio narrative flow).
- Global registry table with:
  - scope filters (World / US / Illinois)
  - provider-family filter
  - text search
  - top countries/operators snapshots
- Uses external registry data for broader coverage while map pressure/scenario logic still uses your project scoring model.

## Scoring Model (Core Formulas)

Shared defaults are defined in `src/scoring.py`.

### Pressure Score

Pressure Score =  
`(Existing x 1.0) + (Proposed x 1.5) + (Inventory x 0.75) + (Denied x 0.5)`

Rationale:

- Existing: baseline active footprint
- Proposed: weighted higher for near-term expansion pressure
- Inventory: medium uncertainty pipeline signal
- Denied: low residual planning pressure

### Economic Vulnerability 2.0 (Composite)

Weighted normalized mix of:

- Poverty rate (0.30)
- Minority population (0.25)
- Median household income (0.20, inverse direction)
- Median monthly housing cost (0.10)
- Energy burden % income (0.15)

### Cumulative Burden (Air + Energy) (Composite)

Weighted normalized mix of:

- AQI P90 (0.30)
- Ozone days (0.20)
- PM2.5 days (0.20)
- Energy burden % income (0.20)
- Electricity use per capita (0.10)

## Data Inputs

Core input files:

- `data/processed/il_sites_enhanced.csv`
- `data/processed/il_county_stats_enhanced.csv`
- `data/boundaries/IL_County_Boundaries.shp`
- `data/raw/annual_aqi_by_county_2025.csv`
- `data/raw/LEADTool_Data Counties.csv`
- `data/raw/2016cityandcountyenergyprofiles.xlsb`
- `data/raw/water/aqueduct-4-0/...`
- `data/raw/egrid/...`
- `data/raw/heat_climate/...`
- `data/raw/noise/faa_il_airports.geojson`
- `data/raw/noise/chicago_311_noise_annual.csv`
- `data/raw/noise/chicago_311_noise_by_community_area.csv`
- `data/raw/noise/epa_tri_il_facilities.csv`
- `data/raw/noise/chicago_311_industrial_annual.csv`
- `data/raw/justice/epa_ejscreen_il_raw.csv`
- `data/raw/justice/cdc_svi2020_il_county_raw.csv`
- `data/raw/land_use_zoning/chicago_zoning_districts.geojson`
- `data/raw/land_use_zoning/landcover_counties/*.htm`
- `data/raw/datacenters/peeringdb_facilities_raw.json`
- `data/raw/datacenters/osm_il_datacenters_raw.json`
- `data/processed/il_county_water_stress.csv`
- `data/processed/il_county_grid_emissions.csv`
- `data/processed/il_county_heat_climate.csv`
- `data/processed/il_county_noise_community.csv`
- `data/processed/il_county_justice.csv`
- `data/processed/il_county_land_use_zoning.csv`
- `data/processed/global_datacenters_registry.csv`
- `data/processed/il_datacenters_registry.csv`

Generated web data:

- `web/public/data/il_counties.geojson`
- `web/public/data/il_sites.geojson`
- `web/public/data/global_datacenters_registry.geojson`
- `web/public/data/il_datacenters_registry.geojson`
- `web/public/data/map_metadata.json`

## Repository Structure

```text
SoReMo-S26-people-v-hasty-ai/
  data/
    boundaries/
    raw/
    processed/
  src/
    export_web_data.py           # Python exporter -> GeoJSON + metadata for web app
    build_water_layer.py         # Aqueduct county water layer builder
    build_energy_emissions_layer.py # eGRID county grid/emissions layer builder
    build_heat_climate_layer.py  # NOAA + FEMA county heat/climate layer builder
    build_noise_community_layer.py # FAA + Chicago 311 + EPA TRI county noise/community layer builder
    build_justice_layer.py       # EPA EJScreen + CDC SVI county justice layer builder
    build_land_use_zoning_layer.py # Illinois land-cover + Chicago zoning county layer builder
    build_datacenter_registry.py # PeeringDB + OSM + curated registry builder (Illinois + global)
    scoring.py                   # Shared scoring weights
  web/
    src/
      App.svelte                 # Main app (home/map/briefing/studio routing + map)
      components/
        MetricBenchmarkCard.svelte
      workspaces/
        BriefWorkspace.svelte
        StudioWorkspace.svelte
        RegistryWorkspace.svelte
    public/data/                 # Exported runtime data
    package.json
    vite.config.js
  requirements.txt
  README.md
```

## Run Locally

### 1) Python environment

Windows PowerShell:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Build web data from source datasets

```bash
python -m src.build_water_layer
python -m src.build_energy_emissions_layer
python -m src.build_heat_climate_layer
python -m src.build_noise_community_layer
python -m src.build_justice_layer
python -m src.build_land_use_zoning_layer
python -m src.build_datacenter_registry
python -m src.export_web_data
```

### 3) Start web app

```bash
cd web
npm install
npm run dev
```

Open:

- `http://localhost:5173/`

### 4) Production build (optional)

```bash
cd web
npm run build
npm run preview
```

## Refreshing Data

When any raw/processed dataset changes:

1. Re-run `python -m src.export_web_data`
2. Refresh or restart `npm run dev`

## Notes

- Pressure layer handles zero-heavy county distributions explicitly to avoid misleading quantile legends.
- Scenario and focus selections now produce distinct outputs in Briefing/Studio.
- County confidence indicators are based on coverage of available county metrics.
- Legacy Streamlit/Folium runtime is no longer used in the active app.
