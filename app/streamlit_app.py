from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import pandas as pd
import geopandas as gpd
import streamlit as st
import streamlit.components.v1 as components

from src.mapping.build_map import build_illinois_map

try:
    from streamlit_folium import st_folium
    HAS_ST_FOLIUM = True
except Exception:
    HAS_ST_FOLIUM = False


# Must be first Streamlit command
st.set_page_config(page_title="People v. Hasty AI Development Map", layout="wide")


st.markdown(
    """
    <style>
      /* Remove extra whitespace at the very top */
      .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 1.5rem !important;
      }

      /* Make sidebar start higher too */
      section[data-testid="stSidebar"] .block-container {
        padding-top: 1.2rem !important;
      }

      /* Optional: shrink gap under title/caption */
      h1 { margin-bottom: 0.25rem !important; }
      .stCaption { margin-top: 0.25rem !important; }

      /* Optional: if Streamlit header bar is creating visual space */
      header[data-testid="stHeader"] {
        height: 0px !important;
      }
      header[data-testid="stHeader"] * {
        display: none !important;
      }
    </style>
    """,
    unsafe_allow_html=True
)


st.title("People v. Hasty AI Development - Illinois Data Center Impact Map")
st.caption(
    "Exploring environmental, community, and infrastructure implications "
    "of existing and proposed AI data centers in Illinois."
)

show_context_layers = st.checkbox(
    "Show county context layers (poverty + minority + air quality). Turning this on may slow zoom.",
    value=False
)

SITES_PATH = "data/processed/il_sites_enhanced.csv"
COUNTIES_SHP = "data/boundaries/IL_County_Boundaries.shp"
COUNTY_STATS = "data/processed/il_county_stats_enhanced.csv"

# Put this file in your repo at: data/raw/annual_aqi_by_county_2025.csv
AQI_PATH = "data/raw/annual_aqi_by_county_2025.csv"

sites = pd.read_csv(SITES_PATH)

counties_layer = None
latest_year = None

if show_context_layers:
    counties = gpd.read_file(COUNTIES_SHP)
    county_stats = pd.read_csv(COUNTY_STATS)

    counties["GEOID"] = counties["GEOID"].astype(str)
    county_stats["GEOID"] = county_stats["GEOID"].astype(str)

    # Simplify geometry (big performance win)
    counties = counties.to_crs(epsg=3857)
    counties["geometry"] = counties["geometry"].simplify(tolerance=150, preserve_topology=True)
    counties = counties.to_crs(epsg=4326)

    # Merge your existing county stats first
    counties_layer = counties.merge(county_stats, on="GEOID", how="left")

    # ---- Merge AQI county data (latest year in file) ----
    try:
        aqi = pd.read_csv(AQI_PATH)

        # Illinois only
        aqi_il = aqi[aqi["State"].astype(str).str.strip().str.lower() == "illinois"].copy()

        # If multiple years exist, take latest
        aqi_il["Year"] = pd.to_numeric(aqi_il["Year"], errors="coerce")
        latest_year = int(aqi_il["Year"].max())
        aqi_il = aqi_il[aqi_il["Year"] == latest_year].copy()

        # Normalize county names for merge
        aqi_il["County_clean"] = (
            aqi_il["County"]
            .astype(str)
            .str.replace(" County", "", regex=False)
            .str.strip()
            .str.upper()
        )

        # Most county shapefiles use NAME like "Cook"
        if "NAME" in counties_layer.columns:
            counties_layer["NAME_clean"] = counties_layer["NAME"].astype(str).str.strip().str.upper()
        else:
            counties_layer["NAME_clean"] = ""

        # Keep and rename columns we care about
        aqi_keep = aqi_il[
            [
                "County_clean",
                "90th Percentile AQI",
                "Median AQI",
                "Max AQI",
                "Days Ozone",
                "Days PM2.5",
                "Days with AQI",
            ]
        ].copy()

        aqi_keep = aqi_keep.rename(
            columns={
                "90th Percentile AQI": "AQI_P90",
                "Median AQI": "AQI_Median",
                "Max AQI": "AQI_Max",
                "Days Ozone": "Ozone_Days",
                "Days PM2.5": "PM25_Days",
                "Days with AQI": "AQI_Days_Total",
            }
        )

        counties_layer = counties_layer.merge(
            aqi_keep,
            left_on="NAME_clean",
            right_on="County_clean",
            how="left",
        )

        st.caption(f"Air quality layer uses annual county AQI summary for Illinois (Year = {latest_year}).")

    except Exception as e:
        st.warning(
            "AQI file not loaded. Make sure it exists at data/raw/annual_aqi_by_county_2025.csv "
            "and has columns like 'State', 'County', 'Year'.\n\n"
            f"Error: {e}"
        )

# Build map + legends (legends are rendered in Streamlit sidebar, not on the map)
m, legends = build_illinois_map(
    sites=sites,
    counties_layer=counties_layer,
    center=[40.0, -89.2],
    zoom_start=7,
)

# Sidebar legends
if show_context_layers and legends:
    st.sidebar.markdown("## Legends")
    st.sidebar.caption("These are the same scales as the map layers.")
    for item in legends:
        st.sidebar.markdown(f"**{item['title']}**")
        st.sidebar.markdown(item["html"], unsafe_allow_html=True)
        st.sidebar.markdown("---")

# Render map
if HAS_ST_FOLIUM:
    st_folium(m, use_container_width=True, height=620)
else:
    html = m.get_root().render()
    components.html(html, height=650, scrolling=True)

st.markdown(
    "<small>Illinois Institute of Technology • 2026</small>",
    unsafe_allow_html=True,
)
