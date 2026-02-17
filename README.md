# SoReMo S26 | The People v. Hasty AI
## Illinois Data Center Map (v1)

This repo contains the initial technical build for the SoReMo project **The People v. Hasty AI**.

Right now, the project focuses on an **interactive Illinois map** that helps us visualize existing and proposed data centers and quickly see what communities and impact signals are “at stake”. This is meant to support both:
- the written report narrative
- the interactive visualization tool we will demo and expand over time

---

## What is implemented (current status)

### 1) Interactive Illinois map (Folium)
We generate an interactive map using OpenStreetMap as the base layer.

**Layers you can toggle on/off:**
- **Existing** data centers
- **Proposed / Under Dev** (proposed, under development, under construction)
- **Denied** (Naperville Lucent site)
- **Clusters** (dashed circle overlays to highlight concentration zones)

Each site has a popup that includes:
- operator
- location
- surroundings snapshot
- community and consent signals
- likely “annoyance threshold” stressors
- sources (links)

The map can be exported as an HTML file.

### 2) Streamlit web app
A small Streamlit app displays the same map interactively and adds:
- a **filter** by layer (existing, proposed, denied)
- **jump views** (Illinois, Chicago core, Elk Grove cluster, DeKalb cluster, Naperville denied site)

### 3) County context and environmental overlays
The map now includes optional contextual layers to help interpret potential community impact:

County-level overlays (toggleable):

- Community Impact Score (poverty + minority composite index)
- County poverty rate (%)
- Minority population (%)
- Air quality hotspot indicators
- AQI 90th percentile
- Ozone days per year
- PM2.5 days per year

These layers allow early exploratory analysis of possible environmental justice patterns around data center locations.

Hovering over counties displays detailed contextual metrics.

### 4) Sidebar legends instead of map legends (NEW)
Map legends are now rendered in the Streamlit sidebar instead of directly on the map. This improves readability and prevents legends from covering map regions.

The sidebar legends correspond exactly to the active choropleth layers.

### 5) AQI data integration

County air quality data is now automatically merged from:

```bash
data/raw/annual_aqi_by_county_2025.csv
```

Latest available year is detected dynamically if multiple years exist.

Metrics currently used:
- AQI 90th percentile
- Median AQI
- Max AQI
- Ozone days
- PM2.5 days
- Total AQI reporting days

This helps contextualize environmental exposure near proposed infrastructure.


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

Planned later:
- census tract overlays
- environmental justice datasets
- infrastructure proximity analysis

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

### Step 1: Clone the repo

```bash
git clone https://github.com/Laasya-73/SoReMo-S26-people-v-hasty-ai.git
cd SoReMo-S26-people-v-hasty-ai
```

### Step 2: Create a virtual environment

#### Windows PowerShell:

```bash
python -m venv .venv
.venv\Scripts\activate
```

#### Mac/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

## Option A: Build the HTML map (fastest)

This generates an HTML file you can open in any browser.

```bash
python -m src.make_map
```
Output:

```outputs/maps/illinois_datacenters_map.html```

Open it by double clicking the file or dragging it into a browser.

## Option B: Run the Streamlit interactive app

This runs a local app in your browser with filters and jump views.

```bash
streamlit run app/streamlit_app.py
```

Streamlit will print a local URL, usually:

```http://localhost:8501```


## Notebook option
If you prefer running in Jupyter:

Open:

```notebooks/01_build_map_folium.ipynb```

This notebook:

- loads the CSV
- validates schema
- builds the map inline
- exports the HTML

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
