from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import pandas as pd
import geopandas as gpd
import streamlit as st

from src.mapping.build_map import build_illinois_map

try:
    from streamlit_folium import st_folium
    HAS_ST_FOLIUM = True
except Exception:
    HAS_ST_FOLIUM = False

st.set_page_config(page_title="People v. Hasty AI Development Map", layout="wide")

st.title("People v. Hasty AI Development - Illinois Data Center Impact Map")
st.caption(
    "SoReMo Spring 2026 research project exploring environmental, community, and infrastructure implications "
    "of existing and proposed AI data centers in Illinois."
)

show_context_layers = st.checkbox(
    "Show county context layers (poverty + minority). Turning this on may slow zoom.",
    value=False
)

SITES_PATH = "data/processed/il_sites_enhanced.csv"
COUNTIES_SHP = "data/boundaries/IL_County_Boundaries.shp"
COUNTY_STATS = "data/processed/il_county_stats_enhanced.csv"

sites = pd.read_csv(SITES_PATH)

counties_layer = None
if show_context_layers:
    counties = gpd.read_file(COUNTIES_SHP)
    county_stats = pd.read_csv(COUNTY_STATS)

    counties["GEOID"] = counties["GEOID"].astype(str)
    county_stats["GEOID"] = county_stats["GEOID"].astype(str)

    # Simplify geometry (big performance win)
    counties = counties.to_crs(epsg=3857)
    counties["geometry"] = counties["geometry"].simplify(tolerance=150, preserve_topology=True)
    counties = counties.to_crs(epsg=4326)

    counties_layer = counties.merge(county_stats, on="GEOID", how="left")

m = build_illinois_map(
    sites=sites,
    counties_layer=counties_layer,
    center=[40.0, -89.2],
    zoom_start=7,
)

if HAS_ST_FOLIUM:
    st_folium(m, use_container_width=True, height=620)
else:
    html = m.get_root().render()
    st.components.v1.html(html, height=650, scrolling=True)

st.markdown(
    "<small>SoReMo Fellowship Project • Illinois Institute of Technology • 2026</small>",
    unsafe_allow_html=True,
)
