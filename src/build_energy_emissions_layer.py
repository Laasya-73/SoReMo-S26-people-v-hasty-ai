from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

COUNTY_SHP = ROOT / "data/boundaries/IL_County_Boundaries.shp"
RAW_DIR = ROOT / "data/raw/egrid"
PLANTS_CSV = RAW_DIR / "egrid2023_plants_selected.csv"
SUBREGIONS_GEOJSON = RAW_DIR / "egrid2023_subregions.geojson"
OUT_CSV = ROOT / "data/processed/il_county_grid_emissions.csv"

EGRID_PLANTS_QUERY_URL = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/eGRID2023/FeatureServer/0/query"
)
EGRID_SUBREGIONS_QUERY_URL = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/eGRID2023_Subregions/FeatureServer/0/query"
)


def _coerce_fips(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace(".0", "", regex=False)
    return s.str.zfill(5)


def _fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode(params, doseq=True)
    full_url = f"{url}?{query}"
    with urlopen(full_url, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"ArcGIS API error: {payload['error']}")
    return payload


def _download_subregions_geojson() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    data = _fetch_json(
        EGRID_SUBREGIONS_QUERY_URL,
        {
            "where": "1=1",
            "outFields": "Subregion",
            "outSR": 4326,
            "f": "geojson",
        },
    )
    SUBREGIONS_GEOJSON.write_text(json.dumps(data), encoding="utf-8")


def _download_plants_table() -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    out_fields = [
        "FID",
        "Data_Year",
        "eGRID_subregion_acronym",
        "Plant_annual_net_generation__MW",
        "Plant_annual_CO2_emissions__ton",
        "Plant_annual_coal_net_generatio",
        "Plant_annual_oil_net_generation",
        "Plant_annual_gas_net_generation",
        "Plant_annual_other_fossil_net_g",
        "Plant_annual_nuclear_net_genera",
        "Plant_annual_hydro_net_generati",
        "Plant_annual_biomass_net_genera",
        "Plant_annual_wind_net_generatio",
        "Plant_annual_solar_net_generati",
    ]

    count_payload = _fetch_json(
        EGRID_PLANTS_QUERY_URL,
        {
            "where": "1=1",
            "returnCountOnly": "true",
            "f": "json",
        },
    )
    total_count = int(count_payload.get("count", 0))
    page_size = 2000

    rows: list[dict[str, Any]] = []
    offset = 0
    while offset < total_count:
        page = _fetch_json(
            EGRID_PLANTS_QUERY_URL,
            {
                "where": "1=1",
                "outFields": ",".join(out_fields),
                "returnGeometry": "false",
                "orderByFields": "FID",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "json",
            },
        )
        features = page.get("features", [])
        if not features:
            break
        rows.extend((f.get("attributes") or {}) for f in features)
        offset += len(features)

    plants = pd.DataFrame(rows)
    plants.to_csv(PLANTS_CSV, index=False)
    return plants


def _as_nonnegative(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    return s.where(s >= 0)


def _weighted_mean(df: pd.DataFrame, value_col: str, weight_col: str) -> float | None:
    v = pd.to_numeric(df[value_col], errors="coerce")
    w = pd.to_numeric(df[weight_col], errors="coerce")
    mask = v.notna() & w.notna() & (w > 0)
    if not mask.any():
        return None
    return float((v[mask] * w[mask]).sum() / w[mask].sum())


def _build_subregion_stats(plants: pd.DataFrame) -> pd.DataFrame:
    if plants.empty:
        return pd.DataFrame()

    df = plants.copy()
    df["eGRID_subregion_acronym"] = df["eGRID_subregion_acronym"].astype(str).str.strip()
    df = df[df["eGRID_subregion_acronym"] != ""].copy()
    if df.empty:
        return pd.DataFrame()

    net_col = "Plant_annual_net_generation__MW"
    co2_col = "Plant_annual_CO2_emissions__ton"
    fossil_cols = [
        "Plant_annual_coal_net_generatio",
        "Plant_annual_oil_net_generation",
        "Plant_annual_gas_net_generation",
        "Plant_annual_other_fossil_net_g",
    ]
    clean_cols = [
        "Plant_annual_nuclear_net_genera",
        "Plant_annual_hydro_net_generati",
        "Plant_annual_biomass_net_genera",
        "Plant_annual_wind_net_generatio",
        "Plant_annual_solar_net_generati",
    ]

    df["net_generation_mwh"] = _as_nonnegative(df[net_col])
    df["co2_tons"] = _as_nonnegative(df[co2_col])

    for col in fossil_cols + clean_cols:
        df[col] = _as_nonnegative(df[col]).fillna(0)

    df["fossil_generation_mwh"] = df[fossil_cols].sum(axis=1)
    df["clean_generation_mwh"] = df[clean_cols].sum(axis=1)
    df["known_generation_mwh"] = df["fossil_generation_mwh"] + df["clean_generation_mwh"]
    df["generation_for_rate_mwh"] = df["net_generation_mwh"].where(df["net_generation_mwh"] > 0, df["known_generation_mwh"])

    grouped = (
        df.groupby("eGRID_subregion_acronym", dropna=False)
        .agg(
            eGRID_Subregion_Plant_Count=("FID", "count"),
            Grid_Fossil_Generation_MWh=("fossil_generation_mwh", "sum"),
            Grid_Clean_Generation_MWh=("clean_generation_mwh", "sum"),
            Grid_Total_Generation_MWh=("generation_for_rate_mwh", "sum"),
            Grid_CO2_Total_tons=("co2_tons", "sum"),
            eGRID_Data_Year=("Data_Year", "max"),
        )
        .reset_index()
        .rename(columns={"eGRID_subregion_acronym": "eGRID_Subregion"})
    )

    total_known = grouped["Grid_Fossil_Generation_MWh"] + grouped["Grid_Clean_Generation_MWh"]
    grouped["Grid_Fossil_Share_Pct"] = (grouped["Grid_Fossil_Generation_MWh"] / total_known * 100.0).where(
        total_known > 0
    )
    grouped["Grid_Clean_Share_Pct"] = (grouped["Grid_Clean_Generation_MWh"] / total_known * 100.0).where(
        total_known > 0
    )
    grouped["Grid_Carbon_Intensity_lb_per_MWh"] = (
        grouped["Grid_CO2_Total_tons"] * 2000.0 / grouped["Grid_Total_Generation_MWh"]
    ).where(grouped["Grid_Total_Generation_MWh"] > 0)
    grouped["Grid_Carbon_Intensity_kg_per_MWh"] = grouped["Grid_Carbon_Intensity_lb_per_MWh"] * 0.45359237
    grouped["Grid_Est_CO2_kt_per_100MWyr"] = (
        grouped["Grid_Carbon_Intensity_lb_per_MWh"] * 8760.0 * 100.0 / 2000.0 / 1000.0
    )

    for col in [
        "Grid_Fossil_Share_Pct",
        "Grid_Clean_Share_Pct",
        "Grid_Carbon_Intensity_lb_per_MWh",
        "Grid_Carbon_Intensity_kg_per_MWh",
        "Grid_Est_CO2_kt_per_100MWyr",
    ]:
        grouped[col] = pd.to_numeric(grouped[col], errors="coerce")

    return grouped


def _build_county_layer(subregion_stats: pd.DataFrame) -> pd.DataFrame:
    if not SUBREGIONS_GEOJSON.exists():
        raise FileNotFoundError(f"Missing subregions GeoJSON: {SUBREGIONS_GEOJSON}")

    if subregion_stats.empty:
        return pd.DataFrame()

    counties = gpd.read_file(COUNTY_SHP)[["GEOID", "NAME", "geometry"]].copy()
    counties["GEOID"] = _coerce_fips(counties["GEOID"])
    counties["County_Name"] = counties["NAME"].astype(str).str.strip() + " County"
    counties = counties.to_crs(epsg=4326)
    counties["geometry"] = counties.geometry.buffer(0)

    subregions = gpd.read_file(SUBREGIONS_GEOJSON)[["Subregion", "geometry"]].copy()
    subregions = subregions.to_crs(epsg=4326)
    subregions["geometry"] = subregions.geometry.buffer(0)
    subregions = subregions.merge(subregion_stats, left_on="Subregion", right_on="eGRID_Subregion", how="left")

    counties_m = counties.to_crs(epsg=5070)
    subregions_m = subregions.to_crs(epsg=5070)

    intersections = gpd.overlay(
        counties_m[["GEOID", "County_Name", "geometry"]],
        subregions_m[
            [
                "Subregion",
                "Grid_Clean_Share_Pct",
                "Grid_Fossil_Share_Pct",
                "Grid_Carbon_Intensity_lb_per_MWh",
                "Grid_Carbon_Intensity_kg_per_MWh",
                "Grid_Est_CO2_kt_per_100MWyr",
                "eGRID_Data_Year",
                "geometry",
            ]
        ],
        how="intersection",
    )
    intersections["part_area_m2"] = intersections.geometry.area

    county_area = counties_m.copy()
    county_area["county_area_m2"] = county_area.geometry.area
    intersections = intersections.merge(county_area[["GEOID", "county_area_m2"]], on="GEOID", how="left")

    rows: list[dict[str, Any]] = []
    for geoid, grp in intersections.groupby("GEOID"):
        county_name = grp["County_Name"].iloc[0]
        county_area_m2 = float(grp["county_area_m2"].iloc[0]) if len(grp) else 0.0
        covered_area = float(grp["part_area_m2"].sum())
        coverage_pct = (covered_area / county_area_m2 * 100.0) if county_area_m2 > 0 else None

        primary = grp.sort_values("part_area_m2", ascending=False).iloc[0]
        primary_subregion = primary.get("Subregion")
        primary_subregion_area_pct = (
            float(primary.get("part_area_m2", 0)) / county_area_m2 * 100.0 if county_area_m2 > 0 else None
        )

        rows.append(
            {
                "GEOID": geoid,
                "County_Name": county_name,
                "Grid_Primary_Subregion": primary_subregion,
                "Grid_Primary_Subregion_Area_Pct": round(primary_subregion_area_pct, 1)
                if primary_subregion_area_pct is not None
                else None,
                "Grid_Subregion_Coverage_Pct": round(coverage_pct, 1) if coverage_pct is not None else None,
                "Grid_Clean_Share_Pct": _weighted_mean(grp, "Grid_Clean_Share_Pct", "part_area_m2"),
                "Grid_Fossil_Share_Pct": _weighted_mean(grp, "Grid_Fossil_Share_Pct", "part_area_m2"),
                "Grid_Carbon_Intensity_lb_per_MWh": _weighted_mean(grp, "Grid_Carbon_Intensity_lb_per_MWh", "part_area_m2"),
                "Grid_Carbon_Intensity_kg_per_MWh": _weighted_mean(grp, "Grid_Carbon_Intensity_kg_per_MWh", "part_area_m2"),
                "Grid_Est_CO2_kt_per_100MWyr": _weighted_mean(grp, "Grid_Est_CO2_kt_per_100MWyr", "part_area_m2"),
                "eGRID_Data_Year": pd.to_numeric(grp["eGRID_Data_Year"], errors="coerce").max(),
                "Grid_Source": "EPA eGRID 2023 (Subregions + PLNT23 via ArcGIS Feature Services)",
            }
        )

    out = pd.DataFrame(rows).sort_values("GEOID").reset_index(drop=True)
    for col in [
        "Grid_Clean_Share_Pct",
        "Grid_Fossil_Share_Pct",
        "Grid_Carbon_Intensity_lb_per_MWh",
        "Grid_Carbon_Intensity_kg_per_MWh",
        "Grid_Est_CO2_kt_per_100MWyr",
    ]:
        out[col] = pd.to_numeric(out[col], errors="coerce").round(2)
    return out


def build_il_energy_grid_emissions_layer(download_raw: bool = True) -> pd.DataFrame:
    if download_raw:
        _download_subregions_geojson()
        plants = _download_plants_table()
    else:
        if not PLANTS_CSV.exists():
            raise FileNotFoundError(f"Missing plants CSV: {PLANTS_CSV}")
        plants = pd.read_csv(PLANTS_CSV)
        if not SUBREGIONS_GEOJSON.exists():
            raise FileNotFoundError(f"Missing subregions GeoJSON: {SUBREGIONS_GEOJSON}")

    subregion_stats = _build_subregion_stats(plants)
    county = _build_county_layer(subregion_stats)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    county.to_csv(OUT_CSV, index=False)
    return county


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Illinois county energy-grid and emissions layer from EPA eGRID.")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Reuse existing raw files in data/raw/egrid instead of downloading again.",
    )
    args = parser.parse_args()

    df = build_il_energy_grid_emissions_layer(download_raw=not args.no_download)
    print(f"Wrote: {OUT_CSV} ({len(df)} counties)")
