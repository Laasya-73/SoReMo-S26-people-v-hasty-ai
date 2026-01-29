import sys
from pathlib import Path

# Add repo root to Python path so `src` can be imported
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

import streamlit as st
from streamlit_folium import st_folium

from src.config import IL_SITES_CSV
from src.utils.io import read_csv
from src.mapping.build_map import build_illinois_map

st.set_page_config(page_title="SoReMo Illinois Data Center Map", layout="wide")
st.title("SoReMo Illinois Data Center Map")

sites = read_csv(IL_SITES_CSV)

# View presets (these are your zoom buttons)
VIEWS = {
    "Illinois (full view)": {"center": [40.0, -89.2], "zoom": 7},
    "Chicago core": {"center": [41.864, -87.631], "zoom": 12},
    "Elk Grove cluster": {"center": [42.000, -87.970], "zoom": 12},
    "DeKalb cluster": {"center": [41.865, -88.751], "zoom": 12},
    "Naperville (Denied site)": {"center": [41.812, -88.170], "zoom": 13},
}

col1, col2 = st.columns([1, 2])

with col1:
    view_choice = st.radio("Jump to view", list(VIEWS.keys()), index=0)

with col2:
    status_filter = st.multiselect(
        "Filter by layer",
        options=["existing", "proposed", "denied"],
        default=["existing", "proposed", "denied"]
    )

if status_filter:
    sites = sites[sites["layer"].isin(status_filter)]

preset = VIEWS[view_choice]
m = build_illinois_map(sites, center=preset["center"], zoom_start=preset["zoom"])
st_folium(m, width=1200, height=650)
