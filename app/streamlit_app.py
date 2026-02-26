# ============================================
# app/streamlit_app.py  (FULL UPDATED FILE)
# ============================================
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


def _coerce_fips(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace(".0", "", regex=False)
    return s.str.zfill(5)


def _make_unique_columns(cols) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []

    for i, c in enumerate(cols):
        name = "" if c is None else str(c).strip()
        if name == "" or name.lower() == "nan":
            name = f"col_{i}"

        if name not in seen:
            seen[name] = 1
            out.append(name)
        else:
            seen[name] += 1
            out.append(f"{name}__{seen[name]}")

    return out


def _ensure_unique_gdf_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf.columns = _make_unique_columns(gdf.columns)
    return gdf


def _read_lead_county_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, skiprows=8)
    df.columns = _make_unique_columns(df.columns)
    return df


def _read_energy_profiles_xlsb_county(path: str) -> pd.DataFrame:
    try:
        from pyxlsb import open_workbook
    except Exception as e:
        raise ImportError("Missing dependency 'pyxlsb'. Install it with: pip install pyxlsb") from e

    rows = []
    with open_workbook(path) as wb:
        with wb.get_sheet("County") as sheet:
            for row in sheet.rows():
                rows.append([c.v for c in row])

    if len(rows) < 6:
        raise ValueError("XLSB County sheet looks empty or unreadable.")

    header_row_idx = 4
    header = _make_unique_columns(rows[header_row_idx])
    data = rows[header_row_idx + 1 :]

    df = pd.DataFrame(data, columns=header)
    df = df.dropna(axis=1, how="all")
    return df


def _find_col(df: pd.DataFrame, base_name: str) -> str | None:
    if base_name in df.columns:
        return base_name
    for c in df.columns:
        if c == base_name or c.startswith(base_name + "__"):
            return c
    return None


# Must be first Streamlit command
st.set_page_config(page_title="People v. Hasty AI Development Map", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem !important; padding-bottom: 1.5rem !important; }
      section[data-testid="stSidebar"] .block-container { padding-top: 1.2rem !important; }
      h1 { margin-bottom: 0.25rem !important; }
      .stCaption { margin-top: 0.25rem !important; }
      header[data-testid="stHeader"] { height: 0px !important; }
      header[data-testid="stHeader"] * { display: none !important; }
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
    "Show county context layers (poverty + minority + air quality + energy). Turning this on may slow zoom.",
    value=False
)

SITES_PATH = "data/processed/il_sites_enhanced.csv"
COUNTIES_SHP = "data/boundaries/IL_County_Boundaries.shp"
COUNTY_STATS = "data/processed/il_county_stats_enhanced.csv"

AQI_PATH = "data/raw/annual_aqi_by_county_2025.csv"

# Your energy files (exact names)
LEAD_PATH = "data/raw/LEADTool_Data Counties.csv"
ENERGY_XLSB_PATH = "data/raw/2016cityandcountyenergyprofiles.xlsb"

sites = pd.read_csv(SITES_PATH)

counties_layer = None
latest_year = None

if show_context_layers:
    counties = gpd.read_file(COUNTIES_SHP)
    county_stats = pd.read_csv(COUNTY_STATS)

    counties["GEOID"] = counties["GEOID"].astype(str).str.zfill(5)
    county_stats["GEOID"] = county_stats["GEOID"].astype(str).str.zfill(5)

    counties = counties.to_crs(epsg=3857)
    counties["geometry"] = counties["geometry"].simplify(tolerance=150, preserve_topology=True)
    counties = counties.to_crs(epsg=4326)

    counties_layer = counties.merge(county_stats, on="GEOID", how="left")
    counties_layer = _ensure_unique_gdf_columns(counties_layer)

    if "NAME" in counties_layer.columns:
        counties_layer["NAME_clean"] = counties_layer["NAME"].astype(str).str.strip().str.upper()
    else:
        counties_layer["NAME_clean"] = ""

    # ---- AQI ----
    try:
        aqi = pd.read_csv(AQI_PATH)

        aqi_il = aqi[aqi["State"].astype(str).str.strip().str.lower() == "illinois"].copy()
        aqi_il["Year"] = pd.to_numeric(aqi_il["Year"], errors="coerce")
        latest_year = int(aqi_il["Year"].max())
        aqi_il = aqi_il[aqi_il["Year"] == latest_year].copy()

        aqi_il["County_clean"] = (
            aqi_il["County"].astype(str).str.replace(" County", "", regex=False).str.strip().str.upper()
        )

        aqi_keep = aqi_il[
            ["County_clean", "90th Percentile AQI", "Median AQI", "Max AQI", "Days Ozone", "Days PM2.5", "Days with AQI"]
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

        counties_layer = counties_layer.merge(aqi_keep, left_on="NAME_clean", right_on="County_clean", how="left")
        counties_layer = _ensure_unique_gdf_columns(counties_layer)

        st.caption(f"Air quality layer uses annual county AQI summary for Illinois (Year = {latest_year}).")

    except Exception as e:
        st.warning(
            "AQI file not loaded. Make sure it exists at data/raw/annual_aqi_by_county_2025.csv "
            "and has columns like 'State', 'County', 'Year'.\n\n"
            f"Error: {e}"
        )

    # ---- ENERGY 1: LEAD Tool ----
    try:
        lead = _read_lead_county_csv(LEAD_PATH)

        if "Geography ID" not in lead.columns:
            raise ValueError("LEAD CSV missing 'Geography ID' column.")

        lead["GEOID"] = _coerce_fips(lead["Geography ID"])

        rename_map = {
            "Energy Burden (% income)": "Energy_Burden_PctIncome",
            "Avg. Annual Energy Cost ($)": "Avg_Annual_Energy_Cost_USD",
            "Total Households": "Total_Households",
            "Household Income": "Household_Income_USD",
        }

        keep_cols = ["GEOID"] + [c for c in rename_map.keys() if c in lead.columns]
        lead_keep = lead[keep_cols].copy().rename(columns=rename_map)

        counties_layer = counties_layer.merge(lead_keep, on="GEOID", how="left")
        counties_layer = _ensure_unique_gdf_columns(counties_layer)

        st.caption("Energy layer added: LEAD Tool energy burden and household cost.")

    except Exception as e:
        st.warning(f"LEAD file not loaded. Put it at: {LEAD_PATH}\n\nError: {e}")

    # ---- ENERGY 2: Energy Profiles XLSB ----
    try:
        ep = _read_energy_profiles_xlsb_county(ENERGY_XLSB_PATH)

        state_col = _find_col(ep, "state_abbr")
        county_col = _find_col(ep, "county_id")
        cons_col = _find_col(ep, "consumption (MWh/capita)")

        if state_col is None:
            raise ValueError("Energy profiles County sheet missing 'state_abbr'.")
        if county_col is None:
            raise ValueError("Energy profiles County sheet missing 'county_id'.")
        if cons_col is None:
            raise ValueError("Energy profiles County sheet missing 'consumption (MWh/capita)'.")

        ep_il = ep[ep[state_col].astype(str).str.upper() == "IL"].copy()
        ep_il["GEOID"] = _coerce_fips(ep_il[county_col])

        ep_keep = ep_il[["GEOID", cons_col]].copy().rename(columns={cons_col: "Elec_Consumption_MWh_perCapita"})

        counties_layer = counties_layer.merge(ep_keep, on="GEOID", how="left")
        counties_layer = _ensure_unique_gdf_columns(counties_layer)

        st.caption("Energy layer added: electricity consumption per capita (MWh/capita).")

    except Exception as e:
        st.warning(
            f"Energy profiles XLSB not loaded. Put it at: {ENERGY_XLSB_PATH}\n\n"
            "If you see a pyxlsb error, run: pip install pyxlsb\n\n"
            f"Error: {e}"
        )

# Build map + legends
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

st.markdown("<small>Illinois Institute of Technology • 2026</small>", unsafe_allow_html=True)