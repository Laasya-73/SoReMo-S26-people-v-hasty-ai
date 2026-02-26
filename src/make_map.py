# ============================================
# src/make_map.py  (FULL UPDATED FILE)
# Exports:
#   1) illinois_datacenters_map.html (map only)
#   2) legends.html (legends only)
#   3) viewer.html (legends left + map right)
# ============================================

from __future__ import annotations

from pathlib import Path

import pandas as pd
import geopandas as gpd

from src.config import (
    IL_SITES_CSV,
    DEFAULT_OUTPUT_MAP,
    IL_COUNTY_BOUNDARIES_SHP,
    IL_COUNTY_STATS_ENHANCED_CSV,
)
from src.utils.io import read_csv, ensure_parent_dir, read_geographic_data
from src.mapping.build_map import build_illinois_map


# -----------------------------
# Viewer/Legend HTML writers
# -----------------------------
def _write_legends_html(legends: list[dict], out_path: Path) -> None:
    cards = []
    for item in legends:
        title = item.get("title", "")
        html = item.get("html", "")
        cards.append(
            f"""
            <div class="legend-card">
              <div class="legend-title">{title}</div>
              <div class="legend-body">{html}</div>
            </div>
            """
        )

    page = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <title>Map Legends</title>
      <style>
        body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 16px; }}
        .legend-card {{
          border: 1px solid rgba(0,0,0,0.12);
          border-radius: 10px;
          padding: 12px;
          margin-bottom: 12px;
          box-shadow: 0 1px 6px rgba(0,0,0,0.06);
          background: white;
        }}
        .legend-title {{ font-weight: 700; margin-bottom: 8px; }}
        .legend-body {{ overflow-x: auto; }}
      </style>
    </head>
    <body>
      <h2 style="margin-top:0;">Legends</h2>
      {''.join(cards) if cards else '<p>No legends available.</p>'}
    </body>
    </html>
    """
    out_path.write_text(page, encoding="utf-8")


def _write_viewer_html(map_file: Path, legends_file: Path, out_path: Path) -> None:
    page = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <title>Illinois Data Center Impact Map</title>
      <style>
        html, body {{ height: 100%; margin: 0; }}
        body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }}
        .wrap {{ display: flex; height: 100%; }}
        .left {{
          width: 360px;
          min-width: 320px;
          max-width: 420px;
          border-right: 1px solid rgba(0,0,0,0.12);
          overflow: auto;
          padding: 14px;
          background: #fafafa;
        }}
        .right {{ flex: 1; height: 100%; }}
        iframe {{ border: 0; width: 100%; height: 100%; }}
        .hint {{
          font-size: 12px; color: #444; margin-top: 6px; line-height: 1.35;
        }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="left">
          <h2 style="margin: 0 0 8px 0;">Legends</h2>
          <div class="hint">Toggle layers in the map (top-right). Legends here match the choropleth scales.</div>
          <iframe src="{legends_file.name}" style="height: calc(100% - 56px); margin-top: 10px;"></iframe>
        </div>
        <div class="right">
          <iframe src="{map_file.name}"></iframe>
        </div>
      </div>
    </body>
    </html>
    """
    out_path.write_text(page, encoding="utf-8")


# -----------------------------
# Data merge helpers (same as Streamlit)
# -----------------------------
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


def main():
    # Same raw data paths as Streamlit
    AQI_PATH = "data/raw/annual_aqi_by_county_2025.csv"
    LEAD_PATH = "data/raw/LEADTool_Data Counties.csv"
    ENERGY_XLSB_PATH = "data/raw/2016cityandcountyenergyprofiles.xlsb"

    # 1) Sites
    sites = read_csv(IL_SITES_CSV)

    # 2) Counties shapefile
    counties = read_geographic_data(IL_COUNTY_BOUNDARIES_SHP)

    # 3) Base county stats
    county_stats = pd.read_csv(IL_COUNTY_STATS_ENHANCED_CSV)

    # Normalize GEOID
    counties["GEOID"] = counties["GEOID"].astype(str).str.strip().str.zfill(5)
    county_stats["GEOID"] = (
        county_stats["GEOID"].astype(str).str.strip().str.replace(".0", "", regex=False).str.zfill(5)
    )

    # Simplify geometry (optional but good)
    try:
        counties = counties.to_crs(epsg=3857)
        counties["geometry"] = counties["geometry"].simplify(tolerance=150, preserve_topology=True)
        counties = counties.to_crs(epsg=4326)
    except Exception:
        pass

    counties_layer = counties.merge(county_stats, on="GEOID", how="left")
    counties_layer = _ensure_unique_gdf_columns(counties_layer)

    # NAME_clean for AQI merge
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

        counties_layer = counties_layer.merge(aqi_keep, left_on="NAME_clean", right_on="County_clean", how="left")
        counties_layer = _ensure_unique_gdf_columns(counties_layer)

        print(f"[OK] AQI merged (Illinois, Year={latest_year})")

    except Exception as e:
        print(f"[WARN] AQI not loaded from {AQI_PATH}. Error: {e}")

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

        print("[OK] LEAD energy merged")

    except Exception as e:
        print(f"[WARN] LEAD not loaded from {LEAD_PATH}. Error: {e}")

    # ---- ENERGY 2: XLSB profiles ----
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

        print("[OK] Energy profiles XLSB merged")

    except Exception as e:
        print(
            f"[WARN] Energy profiles XLSB not loaded from {ENERGY_XLSB_PATH}. "
            "If you see a pyxlsb error, run: pip install pyxlsb. "
            f"Error: {e}"
        )

    # ---- Build map + legends ----
    m, legends = build_illinois_map(
        sites=sites,
        counties_layer=counties_layer,
        center=[40.0, -89.2],
        zoom_start=7,
    )

    # Save files
    ensure_parent_dir(DEFAULT_OUTPUT_MAP)
    map_path = Path(DEFAULT_OUTPUT_MAP)

    m.save(str(map_path))

    legends_path = map_path.with_name("legends.html")
    viewer_path = map_path.with_name("viewer.html")

    _write_legends_html(legends, legends_path)
    _write_viewer_html(map_path, legends_path, viewer_path)

    print(f"[DONE] Saved map to: {map_path}")
    print(f"[DONE] Saved legends to: {legends_path}")
    print(f"[DONE] Open this for the neat layout: {viewer_path}")


if __name__ == "__main__":
    main()