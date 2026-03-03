# SoReMo S26 | The People v. Hasty AI

## Illinois Data Center Impact & Burden Mapping Platform

This repository contains the interactive mapping engine for the SoReMo research project  
**“The People v. Hasty AI Development.”**

The platform analyzes where AI-related data centers are concentrated in Illinois and evaluates which communities may carry higher environmental, economic, and energy burdens as infrastructure expands.

Rather than simply plotting sites, this project integrates:

- Site-level infrastructure data  
- County-level demographic indicators  
- Air quality exposure metrics  
- Energy burden and consumption data  
- Composite scoring models  
- Scenario-based footprint comparison  

The result is a transparent, adjustable, and research-oriented spatial decision-support tool.

---

## Project Goal

This map answers:

> Where are Illinois data centers concentrated, and which communities may carry higher environmental and economic burden today and under future growth?

It connects physical infrastructure to community vulnerability and environmental exposure patterns.

---

## What the Audience Sees

The interactive interface includes:

- Site markers (existing, proposed, denied, infrastructure context)  
- Toggleable county overlays  
- Sidebar legends  
- Scenario switch (current footprint vs planned growth)  
- Adjustable scoring weights  
- Transparency panel showing formulas and data coverage  
- Performance mode for smoother rendering  

---

## Core Data Inputs

**Sites**  
`data/processed/il_sites_enhanced.csv`

**County socioeconomic indicators**  
`data/processed/il_county_stats_enhanced.csv`

**Illinois county boundaries**  
`data/boundaries/IL_County_Boundaries.shp`

**Air quality**  
`data/raw/annual_aqi_by_county_2025.csv`

**Energy burden (LEAD Tool)**  
`data/raw/LEADTool_Data Counties.csv`

**Energy consumption profiles**  
`data/raw/2016cityandcountyenergyprofiles.xlsb`

---

## Site Layers (Point Markers)

- Existing Data Centers  
- Proposed / Under Development  
- Rejected or Withdrawn Proposals  
- Additional Infrastructure Context  

Each popup includes:

- Status classification  
- County context indicators  
- Surroundings snapshot  
- Community signals  
- Stressors  
- Source documentation  

---

## County Choropleth Layers

### Core Context Indicators

- Poverty rate  
- Minority population percentage  
- AQI 90th percentile  
- Ozone exposure days  
- PM2.5 exposure days  
- Energy burden  
- Average annual household energy cost  
- Electricity consumption per capita  

---

## Composite Scoring Layers

Three structured indices have been introduced to move beyond raw indicators.

### 1. Data Center Pressure Score

Measures infrastructure accumulation intensity per county.

Weighted counts of:

- Existing sites  
- Proposed sites  
- Denied projects  
- Inventory or contextual sites  

This helps identify concentration patterns.

### 2. Economic Vulnerability 2.0

Measures structural vulnerability.

Combines:

- Poverty rate  
- Minority population share  
- Inverse median income  
- Housing cost indicators  
- Energy burden  

This identifies counties already under socioeconomic strain.

### 3. Cumulative Burden Score

Measures combined environmental and energy stress.

Combines:

- AQI  
- Ozone days  
- PM2.5 days  
- Energy burden  
- Electricity intensity  

This layer connects environmental exposure and infrastructure energy dynamics.

---

## Scenario Mode

Two footprint modes are available:

### Current Footprint

Only existing data centers are counted.

### Planned Growth

Includes existing + proposed + denied + inventory context.

This enables comparison between:

- Present burden  
- Projected pressure under expansion  

A pressure delta table highlights counties with the largest projected change.

---

## Transparency Panel

The transparency panel displays:

- Exact composite score formulas  
- Current weight settings  
- Data vintage (e.g., latest AQI year detected automatically)  
- County metric coverage percentage  
- Top counties by projected pressure delta  

This ensures interpretability and research accountability.

---

## Performance Optimizations

Because multiple county overlays can slow rendering, the system includes:

- Cached site loading  
- Cached county-merge pipeline  
- Cached rendered map HTML  
- Adjustable geometry simplification  
- Optional disabling of county hover tooltips  
- Performance mode with reduced overlays  

These optimizations maintain usability while preserving analytical depth.

---

## Pipeline Overview

1. Streamlit app loads all datasets.  
2. County shapefiles are geometrically simplified.  
3. County datasets are merged and cleaned.  
4. Composite scores are computed.  
5. Folium layers are constructed.  
6. The interactive map is rendered in Streamlit.  
7. Legends are generated dynamically.  
8. Optional static HTML export is created.  

**Core logic files:**

- `app/streamlit_app.py` — application orchestration  
- `src/mapping/build_map.py` — map builder and scoring logic  
- `src/make_map.py` — static export engine  

---

## Tech stack used (so far)

**Language:** Python

**Libraries:**
- `pandas` for reading and managing the site dataset (CSV)
- `folium` for interactive mapping and layer controls
- `streamlit` for a simple interactive web UI
- `streamlit-folium` to embed Folium maps inside Streamlit
- `geopandas` for county boundaries and spatial joins
- `branca` for choropleth color scales and legend rendering

**Additional dependency:**
- pyxlsb (for reading energy profile XLSB datasets)

---

## Project structure

```text
SoReMo-S26-people-v-hasty-ai/
  app/
    streamlit_app.py             # Streamlit UI for the interactive map
  data/
    boundaries/                  # Illinois county shapefile (required for county overlays)
    raw/                         # reserved for downloaded datasets
    processed/                   # Datasets used by the app
  notebooks/
    01_build_map_folium.ipynb    # notebook version of map build + export
  outputs/
    maps/                        # exported HTML maps saved here
    figures/                     # exported tables/figures (optional)
  src/
    config.py                    # paths to key files
    make_map.py                  # script to generate the HTML map
    mapping/
      build_map.py               # main Folium map builder (layers + clusters)
    utils/
      io.py                      # CSV read + directory helpers
  requirements.txt
  .env.example
  .gitignore
  README.md
```

---

## How to run locally

#### Step 1: Clone the repo

```bash
git clone https://github.com/Laasya-73/SoReMo-S26-people-v-hasty-ai.git
cd SoReMo-S26-people-v-hasty-ai
```

#### Step 2: Create a virtual environment

##### Windows PowerShell:

```bash
python -m venv .venv
.venv\Scripts\activate
```

##### Mac/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

#### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Option A: Build the HTML map (fastest)

This generates an HTML file you can open in any browser.

```bash
python -m src.make_map
```
This produces:

- ```outputs/maps/illinois_datacenters_map.html``` → Interactive map only  
- ```outputs/maps/legends.html``` → Choropleth legends
- ```outputs/maps/viewer.html``` → Combined layout (legends on the left, map on the right)

Open ```viewer.html``` (by double clicking the file or dragging it into a browser) for the cleanest presentation.

### Option B: Run the Streamlit interactive app

This runs a local app in your browser with filters and jump views.

```bash
streamlit run app/streamlit_app.py
```

Streamlit will print a local URL, usually:

```http://localhost:8501```

---

## Common issues and fixes

### 1) ModuleNotFoundError: No module named `src`

This is already handled in `app/streamlit_app.py` by adding the repo root to the Python path.

If you ever recreate the file, make sure it includes:

```python
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))
```

### 2) Git line endings warning (LF will be replaced by CRLF)

This is normal on Windows and does not break the project.

---

## Research Direction

This tool is evolving toward a broader environmental and community impact analysis framework. Future directions include:

- Water usage overlays  
- Infrastructure capacity modeling  
- Zoning and permitting layers  
- Census tract-level environmental justice mapping  
- Policy scenario simulations  