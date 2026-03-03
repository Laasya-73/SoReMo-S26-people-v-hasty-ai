from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import pandas as pd
import geopandas as gpd
import streamlit as st
import streamlit.components.v1 as components

from src.mapping.build_map import DEFAULT_SCORING_WEIGHTS, build_illinois_map

try:
    from streamlit_folium import st_folium

    HAS_ST_FOLIUM = True
except Exception:
    HAS_ST_FOLIUM = False


SCENARIO_CURRENT = "Current footprint (existing only)"
SCENARIO_PLANNED = "With planned growth (existing + proposed + inventory + denied)"

COUNTY_LAYER_LABELS = {
    "impact": "Community Impact Score",
    "pressure": "Data Center Pressure Score",
    "economic": "Economic Vulnerability 2.0",
    "cumulative": "Cumulative Burden (Air + Energy)",
    "poverty": "County Poverty Rate (%)",
    "minority": "County Minority Population (%)",
    "aqi": "Air Quality (AQI P90)",
    "ozone": "Ozone Days",
    "pm25": "PM2.5 Days",
    "energy_burden": "Energy Burden (% income)",
    "avg_energy_cost": "Avg Annual Household Energy Cost ($)",
    "electricity_use": "Electricity Use (MWh per capita)",
}


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


@st.cache_data(show_spinner=False)
def _load_sites_cached(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def _build_counties_layer_cached(
    counties_shp: str,
    county_stats_csv: str,
    aqi_csv: str,
    lead_csv: str,
    energy_xlsb: str,
    simplify_tolerance: float,
) -> tuple[gpd.GeoDataFrame, int | None, list[str], list[str]]:
    warnings: list[str] = []
    info: list[str] = []
    latest_year: int | None = None

    counties = gpd.read_file(counties_shp)
    county_stats = pd.read_csv(county_stats_csv)

    counties["GEOID"] = counties["GEOID"].astype(str).str.zfill(5)
    county_stats["GEOID"] = county_stats["GEOID"].astype(str).str.zfill(5)

    counties = counties.to_crs(epsg=3857)
    counties["geometry"] = counties["geometry"].simplify(tolerance=simplify_tolerance, preserve_topology=True)
    counties = counties.to_crs(epsg=4326)

    counties_layer = counties.merge(county_stats, on="GEOID", how="left")
    counties_layer = _ensure_unique_gdf_columns(counties_layer)

    if "NAME" in counties_layer.columns:
        counties_layer["NAME_clean"] = counties_layer["NAME"].astype(str).str.strip().str.upper()
    else:
        counties_layer["NAME_clean"] = ""

    try:
        aqi = pd.read_csv(aqi_csv)

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
        info.append(f"AQI layer uses annual county summary for Illinois (Year = {latest_year}).")
    except Exception as e:
        warnings.append(
            "AQI file not loaded. Make sure it exists at data/raw/annual_aqi_by_county_2025.csv "
            "and has columns like 'State', 'County', 'Year'. "
            f"Error: {e}"
        )

    try:
        lead = _read_lead_county_csv(lead_csv)
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
        info.append("Energy layer added: LEAD Tool energy burden and household cost.")
    except Exception as e:
        warnings.append(f"LEAD file not loaded. Put it at: {lead_csv}. Error: {e}")

    try:
        ep = _read_energy_profiles_xlsb_county(energy_xlsb)
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
        info.append("Energy layer added: electricity consumption per capita (MWh/capita).")
    except Exception as e:
        warnings.append(
            f"Energy profiles XLSB not loaded. Put it at: {energy_xlsb}. "
            "If you see a pyxlsb error, run: pip install pyxlsb. "
            f"Error: {e}"
        )

    return counties_layer, latest_year, warnings, info


@st.cache_data(show_spinner=False)
def _build_map_html_cached(
    sites: pd.DataFrame,
    _counties_layer: gpd.GeoDataFrame | None,
    counties_layer_token: tuple,
    scoring_weights: dict,
    enabled_county_layers: tuple[str, ...],
    show_county_tooltips: bool,
    center: tuple[float, float],
    zoom_start: int,
) -> tuple[str, list[dict]]:
    # counties_layer_token is included only for cache invalidation.
    _ = counties_layer_token
    m, legends = build_illinois_map(
        sites=sites,
        counties_layer=_counties_layer,
        center=[center[0], center[1]],
        zoom_start=zoom_start,
        scoring_weights=scoring_weights,
        enabled_county_layers=list(enabled_county_layers),
        show_county_tooltips=show_county_tooltips,
    )
    return m.get_root().render(), legends


def _classify_sites(sites: pd.DataFrame) -> pd.DataFrame:
    s = sites.copy()
    layer_txt = s.get("layer", pd.Series("", index=s.index)).astype(str).str.strip().str.lower()
    site_id = s.get("site_id", pd.Series("", index=s.index)).astype(str).str.upper()
    is_inventory = (
        site_id.str.contains("INV", na=False)
        | layer_txt.str.contains("inventory", na=False)
        | layer_txt.str.contains("reserve", na=False)
        | layer_txt.str.contains("extra_inventory", na=False)
    )

    s["is_existing"] = (layer_txt == "existing") & (~is_inventory)
    s["is_denied"] = (layer_txt == "denied") & (~is_inventory)
    s["is_inventory"] = is_inventory
    s["is_proposed"] = (~s["is_existing"]) & (~s["is_denied"]) & (~s["is_inventory"])
    return s


def _filter_sites_for_scenario(sites: pd.DataFrame, scenario_mode: str) -> pd.DataFrame:
    s = _classify_sites(sites)
    if scenario_mode == SCENARIO_CURRENT:
        return s[s["is_existing"]].copy()
    return s.copy()


def _sanitize_weight_group(raw: dict[str, float], default_group: dict[str, float]) -> dict[str, float]:
    clean: dict[str, float] = {}
    for key, default_val in default_group.items():
        try:
            clean[key] = max(float(raw.get(key, default_val)), 0.0)
        except Exception:
            clean[key] = float(default_val)
    if sum(clean.values()) <= 0:
        return dict(default_group)
    return clean


def _build_scoring_weights() -> dict:
    st.sidebar.markdown("## Score Controls")
    with st.sidebar.expander("Adjust Weights", expanded=False):
        st.caption("Weights control the three composite layers. Defaults match current project settings.")

        pressure_raw = {
            "existing": st.slider(
                "Pressure: Existing weight",
                min_value=0.0,
                max_value=3.0,
                value=float(DEFAULT_SCORING_WEIGHTS["pressure"]["existing"]),
                step=0.05,
            ),
            "proposed": st.slider(
                "Pressure: Proposed weight",
                min_value=0.0,
                max_value=3.0,
                value=float(DEFAULT_SCORING_WEIGHTS["pressure"]["proposed"]),
                step=0.05,
            ),
            "denied": st.slider(
                "Pressure: Denied weight",
                min_value=0.0,
                max_value=3.0,
                value=float(DEFAULT_SCORING_WEIGHTS["pressure"]["denied"]),
                step=0.05,
            ),
            "inventory": st.slider(
                "Pressure: Inventory weight",
                min_value=0.0,
                max_value=3.0,
                value=float(DEFAULT_SCORING_WEIGHTS["pressure"]["inventory"]),
                step=0.05,
            ),
        }

        economic_raw = {
            "poverty": st.slider(
                "Economic: Poverty",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["economic"]["poverty"]),
                step=0.01,
            ),
            "minority": st.slider(
                "Economic: Minority %",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["economic"]["minority"]),
                step=0.01,
            ),
            "income": st.slider(
                "Economic: Inverse income",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["economic"]["income"]),
                step=0.01,
            ),
            "housing": st.slider(
                "Economic: Housing cost",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["economic"]["housing"]),
                step=0.01,
            ),
            "energy": st.slider(
                "Economic: Energy burden",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["economic"]["energy"]),
                step=0.01,
            ),
        }

        cumulative_raw = {
            "aqi": st.slider(
                "Cumulative: AQI P90",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["cumulative"]["aqi"]),
                step=0.01,
            ),
            "ozone": st.slider(
                "Cumulative: Ozone days",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["cumulative"]["ozone"]),
                step=0.01,
            ),
            "pm25": st.slider(
                "Cumulative: PM2.5 days",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["cumulative"]["pm25"]),
                step=0.01,
            ),
            "energy": st.slider(
                "Cumulative: Energy burden",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["cumulative"]["energy"]),
                step=0.01,
            ),
            "electricity": st.slider(
                "Cumulative: Electricity use",
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_SCORING_WEIGHTS["cumulative"]["electricity"]),
                step=0.01,
            ),
        }

    return {
        "pressure": _sanitize_weight_group(pressure_raw, DEFAULT_SCORING_WEIGHTS["pressure"]),
        "economic": _sanitize_weight_group(economic_raw, DEFAULT_SCORING_WEIGHTS["economic"]),
        "cumulative": _sanitize_weight_group(cumulative_raw, DEFAULT_SCORING_WEIGHTS["cumulative"]),
    }


def _pressure_by_county(sites: pd.DataFrame, pressure_weights: dict[str, float]) -> pd.DataFrame:
    s = _classify_sites(sites)
    if "GEOID" in s.columns:
        s["county_key"] = _coerce_fips(s["GEOID"])
        if "County_Name" in s.columns:
            s["county_name"] = s["County_Name"].astype(str)
        else:
            s["county_name"] = s["county_key"]
    elif "County_Name" in s.columns:
        s["county_key"] = s["County_Name"].astype(str).str.strip().str.upper()
        s["county_name"] = s["County_Name"].astype(str)
    else:
        return pd.DataFrame()

    s["ct_existing"] = s["is_existing"].astype(int)
    s["ct_proposed"] = s["is_proposed"].astype(int)
    s["ct_denied"] = s["is_denied"].astype(int)
    s["ct_inventory"] = s["is_inventory"].astype(int)

    grouped = (
        s.groupby("county_key", dropna=False)[["ct_existing", "ct_proposed", "ct_denied", "ct_inventory"]]
        .sum()
        .reset_index()
    )
    name_map = s.groupby("county_key", dropna=False)["county_name"].first().reset_index()
    grouped = grouped.merge(name_map, on="county_key", how="left")

    grouped["Pressure_Score"] = (
        grouped["ct_existing"] * pressure_weights["existing"]
        + grouped["ct_proposed"] * pressure_weights["proposed"]
        + grouped["ct_denied"] * pressure_weights["denied"]
        + grouped["ct_inventory"] * pressure_weights["inventory"]
    ).round(2)
    return grouped


def _render_transparency_panel(
    scenario_mode: str,
    sites_full: pd.DataFrame,
    sites_filtered: pd.DataFrame,
    scoring_weights: dict,
    latest_year: int | None,
    counties_layer: gpd.GeoDataFrame | None,
) -> None:
    with st.expander("Methodology and Data Transparency", expanded=False):
        st.markdown("**Scenario**")
        st.write(f"Mode: {scenario_mode}")
        st.write(f"Sites shown: {len(sites_filtered)} of {len(sites_full)} total records")

        st.markdown("**Scoring Formulas**")
        p = scoring_weights["pressure"]
        e = scoring_weights["economic"]
        c = scoring_weights["cumulative"]

        st.code(
            "Pressure_Score = "
            f"Existing*{p['existing']:.2f} + Proposed*{p['proposed']:.2f} + "
            f"Denied*{p['denied']:.2f} + Inventory*{p['inventory']:.2f}",
            language="text",
        )
        st.code(
            "Economic_Vulnerability_2_0 = weighted(minmax("
            f"Poverty*{e['poverty']:.2f}, Minority*{e['minority']:.2f}, "
            f"InverseIncome*{e['income']:.2f}, Housing*{e['housing']:.2f}, "
            f"EnergyBurden*{e['energy']:.2f}))",
            language="text",
        )
        st.code(
            "Cumulative_Burden = weighted(minmax("
            f"AQI_P90*{c['aqi']:.2f}, Ozone*{c['ozone']:.2f}, PM25*{c['pm25']:.2f}, "
            f"EnergyBurden*{c['energy']:.2f}, ElectricityUse*{c['electricity']:.2f}))",
            language="text",
        )

        st.markdown("**Data Vintage and Sources**")
        aqi_year_text = str(latest_year) if latest_year is not None else "Unavailable"
        st.write(f"AQI latest Illinois year detected: {aqi_year_text}")
        st.write("Sites: data/processed/il_sites_enhanced.csv")
        st.write("County stats: data/processed/il_county_stats_enhanced.csv")
        st.write("County boundaries: data/boundaries/IL_County_Boundaries.shp")
        st.write("AQI: data/raw/annual_aqi_by_county_2025.csv")
        st.write("LEAD: data/raw/LEADTool_Data Counties.csv")
        st.write("Energy profiles: data/raw/2016cityandcountyenergyprofiles.xlsb")

        st.markdown("**Pressure Delta (Planned - Current), Top Counties**")
        full_pressure = _pressure_by_county(sites_full, p)
        current_pressure = _pressure_by_county(_filter_sites_for_scenario(sites_full, SCENARIO_CURRENT), p)
        if not full_pressure.empty and not current_pressure.empty:
            delta = full_pressure.merge(
                current_pressure[["county_key", "Pressure_Score"]],
                on="county_key",
                how="left",
                suffixes=("_planned", "_current"),
            )
            delta["Pressure_Score_current"] = delta["Pressure_Score_current"].fillna(0.0)
            delta["Pressure_Delta"] = (delta["Pressure_Score_planned"] - delta["Pressure_Score_current"]).round(2)
            view = (
                delta.sort_values("Pressure_Delta", ascending=False)
                .head(10)[["county_name", "Pressure_Score_current", "Pressure_Score_planned", "Pressure_Delta"]]
                .rename(columns={"county_name": "County"})
            )
            st.dataframe(view, use_container_width=True, hide_index=True)
        else:
            st.write("County key not available in sites table; pressure delta table could not be computed.")

        if counties_layer is not None and not counties_layer.empty:
            st.markdown("**County Data Coverage**")
            coverage_fields = [
                ("Poverty_Rate_Percent", "Poverty rate"),
                ("Pct_Minority", "Minority population %"),
                ("Median_Household_Income", "Median household income"),
                ("Median_Monthly_Housing_Cost", "Median monthly housing cost"),
                ("AQI_P90", "AQI 90th percentile"),
                ("Ozone_Days", "Ozone days"),
                ("PM25_Days", "PM2.5 days"),
                ("Energy_Burden_PctIncome", "Energy burden % income"),
                ("Elec_Consumption_MWh_perCapita", "Electricity MWh/capita"),
            ]
            rows = []
            for field, label in coverage_fields:
                if field in counties_layer.columns:
                    pct = float(counties_layer[field].notna().mean() * 100.0)
                    rows.append({"Metric": label, "Coverage (%)": round(pct, 1)})
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


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
    unsafe_allow_html=True,
)

st.title("People v. Hasty AI Development - Illinois Data Center Impact Map")
st.caption(
    "Exploring environmental, community, and infrastructure implications "
    "of existing and proposed AI data centers in Illinois."
)

st.sidebar.markdown("## Scenario")
scenario_mode = st.sidebar.selectbox(
    "Scenario mode",
    options=[SCENARIO_PLANNED, SCENARIO_CURRENT],
    index=0,
)

show_context_layers = st.sidebar.checkbox(
    "Show county context layers (impact + pressure + economic vulnerability + air quality + energy).",
    value=False,
)

st.sidebar.markdown("## Performance")
performance_mode = st.sidebar.checkbox(
    "Performance mode (fewer county overlays + simpler geometry)",
    value=True,
)
geometry_tolerance = st.sidebar.slider(
    "County geometry simplification",
    min_value=100,
    max_value=800,
    value=300 if performance_mode else 150,
    step=50,
)

all_layer_keys = list(COUNTY_LAYER_LABELS.keys())
default_layer_keys = (
    ["impact", "pressure", "economic", "cumulative"]
    if performance_mode
    else all_layer_keys
)
enabled_county_layers = st.sidebar.multiselect(
    "County layers to render",
    options=all_layer_keys,
    default=default_layer_keys,
    format_func=lambda k: COUNTY_LAYER_LABELS.get(k, k),
)
show_county_tooltips = st.sidebar.checkbox(
    "Show county hover details",
    value=not performance_mode,
)
use_cached_map_html = st.sidebar.checkbox(
    "Cache rendered map HTML (fast redraw; disables st_folium interactions)",
    value=True,
)

scoring_weights = _build_scoring_weights()

SITES_PATH = "data/processed/il_sites_enhanced.csv"
COUNTIES_SHP = "data/boundaries/IL_County_Boundaries.shp"
COUNTY_STATS = "data/processed/il_county_stats_enhanced.csv"
AQI_PATH = "data/raw/annual_aqi_by_county_2025.csv"
LEAD_PATH = "data/raw/LEADTool_Data Counties.csv"
ENERGY_XLSB_PATH = "data/raw/2016cityandcountyenergyprofiles.xlsb"

sites_all = _load_sites_cached(SITES_PATH)
sites = _filter_sites_for_scenario(sites_all, scenario_mode)

if sites.empty:
    st.warning("No sites available for the selected scenario.")

counties_layer = None
latest_year = None

if show_context_layers:
    counties_layer, latest_year, load_warnings, load_info = _build_counties_layer_cached(
        counties_shp=COUNTIES_SHP,
        county_stats_csv=COUNTY_STATS,
        aqi_csv=AQI_PATH,
        lead_csv=LEAD_PATH,
        energy_xlsb=ENERGY_XLSB_PATH,
        simplify_tolerance=float(geometry_tolerance),
    )
    for msg in load_info:
        st.caption(msg)
    for msg in load_warnings:
        st.warning(msg)

layers_for_map = tuple(enabled_county_layers if show_context_layers else [])
tooltips_for_map = bool(show_county_tooltips and show_context_layers)
counties_layer_token = (
    bool(counties_layer is not None),
    int(len(counties_layer)) if counties_layer is not None else 0,
    tuple(sorted(counties_layer.columns)) if counties_layer is not None else (),
    float(geometry_tolerance),
    int(latest_year) if latest_year is not None else -1,
)

if use_cached_map_html:
    map_html, legends = _build_map_html_cached(
        sites=sites,
        _counties_layer=counties_layer,
        counties_layer_token=counties_layer_token,
        scoring_weights=scoring_weights,
        enabled_county_layers=layers_for_map,
        show_county_tooltips=tooltips_for_map,
        center=(40.0, -89.2),
        zoom_start=7,
    )
    m = None
else:
    m, legends = build_illinois_map(
        sites=sites,
        counties_layer=counties_layer,
        center=[40.0, -89.2],
        zoom_start=7,
        scoring_weights=scoring_weights,
        enabled_county_layers=list(layers_for_map),
        show_county_tooltips=tooltips_for_map,
    )

if show_context_layers and legends:
    st.sidebar.markdown("## Legends")
    st.sidebar.caption("These are the same scales as the map layers.")
    for item in legends:
        st.sidebar.markdown(f"**{item['title']}**")
        st.sidebar.markdown(item["html"], unsafe_allow_html=True)
        st.sidebar.markdown("---")

if use_cached_map_html:
    components.html(map_html, height=650, scrolling=True)
elif HAS_ST_FOLIUM:
    st_folium(m, use_container_width=True, height=620)
else:
    html = m.get_root().render()
    components.html(html, height=650, scrolling=True)

_render_transparency_panel(
    scenario_mode=scenario_mode,
    sites_full=sites_all,
    sites_filtered=sites,
    scoring_weights=scoring_weights,
    latest_year=latest_year,
    counties_layer=counties_layer,
)

st.markdown("<small>Illinois Institute of Technology | 2026</small>", unsafe_allow_html=True)
