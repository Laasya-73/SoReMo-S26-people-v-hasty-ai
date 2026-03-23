from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import geopandas as gpd
import pandas as pd
from pandas.errors import EmptyDataError


ROOT = Path(__file__).resolve().parents[1]

COUNTY_SHP = ROOT / "data/boundaries/IL_County_Boundaries.shp"
COUNTY_STATS_CSV = ROOT / "data/processed/il_county_stats_enhanced.csv"

RAW_DIR = ROOT / "data/raw/noise"
FAA_RAW_GEOJSON = RAW_DIR / "faa_il_airports.geojson"
CHI_NOISE_ANNUAL_CSV = RAW_DIR / "chicago_311_noise_annual.csv"
CHI_NOISE_COMMUNITY_AREA_CSV = RAW_DIR / "chicago_311_noise_by_community_area.csv"
CHI_INDUSTRIAL_ANNUAL_CSV = RAW_DIR / "chicago_311_industrial_annual.csv"  # legacy, retained for compatibility
EPA_TRI_FACILITIES_CSV = RAW_DIR / "epa_tri_il_facilities.csv"

OUT_CSV = ROOT / "data/processed/il_county_noise_community.csv"

FAA_AIRPORTS_QUERY_URL = (
    "https://services3.arcgis.com/fWPkIR8HhOCRcYjp/ArcGIS/rest/services/airports/FeatureServer/0/query"
)
CHICAGO_311_ENDPOINT = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"
EPA_TRI_FACILITIES_URL = "https://data.epa.gov/efservice/tri_facility/state_abbr/IL/rows/0:20000/JSON"


def _coerce_fips(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace(".0", "", regex=False)
    return s.str.zfill(5)


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _fetch_json(url: str, params: dict[str, Any] | None = None) -> Any:
    full_url = url
    if params:
        full_url = f"{url}?{urlencode(params, doseq=True)}"
    with urlopen(full_url, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"API error: {payload['error']}")
    return payload


def _download_faa_il_airports() -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    payload = _fetch_json(
        FAA_AIRPORTS_QUERY_URL,
        {
            "where": "ST_POSTAL='IL'",
            "outFields": ",".join(
                [
                    "FULLNAME",
                    "LOCID",
                    "ST_POSTAL",
                    "COUNTY_NAM",
                    "CITY_NAME",
                    "LATITUDE",
                    "LONGITUDE",
                    "COMM_SERV",
                    "AIR_TAXI",
                    "LOCAL_OPS",
                    "ITIN_OPS",
                    "MIL_OPS",
                    "Enplanemen",
                    "Passengers",
                ]
            ),
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "geojson",
        },
    )
    FAA_RAW_GEOJSON.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _download_chicago_noise_tables(start_year: int = 2019) -> tuple[pd.DataFrame, pd.DataFrame]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    where_noise = f"upper(sr_type) like '%NOISE%' AND date_extract_y(created_date) >= {int(start_year)}"
    noise_annual = _fetch_json(
        CHICAGO_311_ENDPOINT,
        {
            "$select": "date_extract_y(created_date) as year,count(*) as noise_count",
            "$where": where_noise,
            "$group": "year",
            "$order": "year",
            "$limit": 5000,
        },
    )
    noise_annual_df = pd.DataFrame(noise_annual)
    if noise_annual_df.empty:
        noise_annual_df = pd.DataFrame(columns=["year", "noise_count"])
    if not noise_annual_df.empty:
        noise_annual_df["year"] = _num(noise_annual_df["year"]).astype("Int64")
        noise_annual_df["noise_count"] = _num(noise_annual_df["noise_count"]).astype("Int64")
        noise_annual_df = noise_annual_df.sort_values("year").reset_index(drop=True)
    noise_annual_df.to_csv(CHI_NOISE_ANNUAL_CSV, index=False)

    noise_by_area = _fetch_json(
        CHICAGO_311_ENDPOINT,
        {
            "$select": "date_extract_y(created_date) as year,community_area,count(*) as noise_count",
            "$where": f"{where_noise} AND community_area is not null",
            "$group": "year,community_area",
            "$order": "year,community_area",
            "$limit": 50000,
        },
    )
    noise_by_area_df = pd.DataFrame(noise_by_area)
    if noise_by_area_df.empty:
        noise_by_area_df = pd.DataFrame(columns=["year", "community_area", "noise_count"])
    if not noise_by_area_df.empty:
        noise_by_area_df["year"] = _num(noise_by_area_df["year"]).astype("Int64")
        noise_by_area_df["community_area"] = _num(noise_by_area_df["community_area"]).astype("Int64")
        noise_by_area_df["noise_count"] = _num(noise_by_area_df["noise_count"]).astype("Int64")
        noise_by_area_df = noise_by_area_df.sort_values(["year", "community_area"]).reset_index(drop=True)
    noise_by_area_df.to_csv(CHI_NOISE_COMMUNITY_AREA_CSV, index=False)

    # Legacy compatibility file. Kept intentionally so old references don't break.
    if not CHI_INDUSTRIAL_ANNUAL_CSV.exists():
        pd.DataFrame(columns=["year", "industrial_count"]).to_csv(CHI_INDUSTRIAL_ANNUAL_CSV, index=False)

    return noise_annual_df, noise_by_area_df


def _download_epa_tri_facilities() -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    payload = _fetch_json(EPA_TRI_FACILITIES_URL)
    tri = pd.DataFrame(payload if isinstance(payload, list) else [])
    if tri.empty:
        tri = pd.DataFrame(
            columns=[
                "tri_facility_id",
                "facility_name",
                "county_name",
                "state_county_fips_code",
                "fac_closed_ind",
                "state_abbr",
            ]
        )
    tri.to_csv(EPA_TRI_FACILITIES_CSV, index=False)
    return tri


def _norm(series: pd.Series) -> pd.Series:
    s = _num(series)
    if s.dropna().empty:
        return s
    mn = float(s.min())
    mx = float(s.max())
    if math.isclose(mx, mn):
        return s * 0
    return (s - mn) / (mx - mn)


def _build_county_layer(noise_annual: pd.DataFrame, tri_facilities: pd.DataFrame) -> pd.DataFrame:
    counties = gpd.read_file(COUNTY_SHP)[["GEOID", "NAME", "geometry"]].copy()
    counties = counties.to_crs(epsg=4326)
    counties["GEOID"] = _coerce_fips(counties["GEOID"])
    counties["County_Name"] = counties["NAME"].astype(str).str.strip() + " County"

    if not FAA_RAW_GEOJSON.exists():
        raise FileNotFoundError(f"Missing FAA airports file: {FAA_RAW_GEOJSON}")

    faa = gpd.read_file(FAA_RAW_GEOJSON)
    if faa.empty:
        raise RuntimeError("FAA airports file is empty.")
    faa = faa.to_crs(epsg=4326)

    join = gpd.sjoin(
        faa[
            [
                c
                for c in [
                    "FULLNAME",
                    "LOCID",
                    "COMM_SERV",
                    "AIR_TAXI",
                    "LOCAL_OPS",
                    "ITIN_OPS",
                    "MIL_OPS",
                    "Enplanemen",
                    "Passengers",
                    "geometry",
                ]
                if c in faa.columns
            ]
        ],
        counties[["GEOID", "County_Name", "geometry"]],
        how="inner",
        predicate="within",
    )

    for col in ["COMM_SERV", "AIR_TAXI", "LOCAL_OPS", "ITIN_OPS", "MIL_OPS", "Enplanemen", "Passengers"]:
        if col in join.columns:
            join[col] = _num(join[col]).fillna(0.0)
        else:
            join[col] = 0.0

    join["FAA_Airport_Operations_Total"] = (
        join["COMM_SERV"] + join["AIR_TAXI"] + join["LOCAL_OPS"] + join["ITIN_OPS"] + join["MIL_OPS"]
    )
    join["FAA_Airport_Operations_Positive"] = (join["FAA_Airport_Operations_Total"] > 0).astype(int)
    join["FAA_Enplanements_Positive"] = (join["Enplanemen"] > 0).astype(int)

    grouped = (
        join.groupby(["GEOID", "County_Name"], dropna=False)
        .agg(
            FAA_Airport_Count=("LOCID", "count"),
            FAA_Airport_Operations_Total=("FAA_Airport_Operations_Total", "sum"),
            FAA_Enplanements_Total=("Enplanemen", "sum"),
            FAA_Passengers_Total=("Passengers", "sum"),
            FAA_Airports_With_Operations=("FAA_Airport_Operations_Positive", "sum"),
            FAA_Airports_With_Enplanements=("FAA_Enplanements_Positive", "sum"),
        )
        .reset_index()
    )

    counties_area = counties.to_crs(epsg=5070)
    counties_area["County_Area_km2"] = counties_area.geometry.area / 1_000_000.0
    grouped = grouped.merge(counties_area[["GEOID", "County_Area_km2"]], on="GEOID", how="left")
    grouped["FAA_Airport_Density_per_1000km2"] = (
        grouped["FAA_Airport_Count"] / grouped["County_Area_km2"] * 1000.0
    ).where(grouped["County_Area_km2"] > 0)

    grouped["ops_log"] = _num(grouped["FAA_Airport_Operations_Total"]).fillna(0).map(lambda v: math.log1p(max(v, 0)))
    grouped["dens_log"] = _num(grouped["FAA_Airport_Density_per_1000km2"]).fillna(0).map(lambda v: math.log1p(max(v, 0)))
    grouped["enp_log"] = _num(grouped["FAA_Enplanements_Total"]).fillna(0).map(lambda v: math.log1p(max(v, 0)))

    grouped["FAA_Noise_Exposure_Index"] = (
        (
            _norm(grouped["ops_log"]).fillna(0) * 0.5
            + _norm(grouped["dens_log"]).fillna(0) * 0.3
            + _norm(grouped["enp_log"]).fillna(0) * 0.2
        )
        * 100.0
    ).round(1)

    out = counties[["GEOID", "County_Name"]].merge(grouped, on=["GEOID", "County_Name"], how="left")
    for col in [
        "FAA_Airport_Count",
        "FAA_Airport_Operations_Total",
        "FAA_Enplanements_Total",
        "FAA_Passengers_Total",
        "FAA_Airports_With_Operations",
        "FAA_Airports_With_Enplanements",
        "County_Area_km2",
        "FAA_Airport_Density_per_1000km2",
        "FAA_Noise_Exposure_Index",
    ]:
        if col in out.columns:
            out[col] = _num(out[col]).fillna(0.0)

    current_year = datetime.utcnow().year
    noise_years = (
        _num(noise_annual["year"]).dropna().astype(int).tolist()
        if (noise_annual is not None and not noise_annual.empty and "year" in noise_annual.columns)
        else []
    )
    latest_complete_year = max((y for y in noise_years if y < current_year), default=None)
    if latest_complete_year is None and noise_years:
        latest_complete_year = max(noise_years)

    recent_years: list[int] = []
    if latest_complete_year is not None:
        recent_years = [y for y in noise_years if latest_complete_year - 2 <= y <= latest_complete_year]

    recent_noise_avg = None
    recent_noise_total = None
    if noise_annual is not None and not noise_annual.empty and recent_years:
        n = noise_annual.copy()
        n["year"] = _num(n["year"]).astype("Int64")
        n["noise_count"] = _num(n["noise_count"]).fillna(0)
        n = n[n["year"].isin(recent_years)]
        if not n.empty:
            recent_noise_avg = float(n["noise_count"].mean())
            recent_noise_total = float(n["noise_count"].sum())

    out["Chicago_311_Noise_AnnualAvg_Recent3yr"] = 0.0
    out["Chicago_311_Noise_Total_Recent3yr"] = 0.0
    out["Chicago_311_Industrial_Total_Recent3yr"] = 0.0  # deprecated legacy field, retained
    cook_mask = out["County_Name"].astype(str).str.strip().str.upper().eq("COOK COUNTY")
    if recent_noise_avg is not None:
        out.loc[cook_mask, "Chicago_311_Noise_AnnualAvg_Recent3yr"] = recent_noise_avg
    if recent_noise_total is not None:
        out.loc[cook_mask, "Chicago_311_Noise_Total_Recent3yr"] = recent_noise_total

    tri = tri_facilities.copy()
    if tri.empty:
        tri = pd.DataFrame(columns=["tri_facility_id", "state_county_fips_code", "fac_closed_ind"])

    if "state_county_fips_code" not in tri.columns:
        tri["state_county_fips_code"] = pd.NA
    tri["GEOID"] = _coerce_fips(tri["state_county_fips_code"])
    tri = tri[tri["GEOID"].str.startswith("17", na=False)].copy()

    if "tri_facility_id" not in tri.columns:
        tri["tri_facility_id"] = pd.NA
    tri["tri_facility_id"] = tri["tri_facility_id"].astype(str).str.strip()
    tri = tri[tri["tri_facility_id"].ne("") & tri["tri_facility_id"].ne("nan")].copy()

    if "fac_closed_ind" not in tri.columns:
        tri["fac_closed_ind"] = "0"
    tri["fac_closed_ind"] = tri["fac_closed_ind"].astype(str).str.strip()
    tri = tri.sort_values(["tri_facility_id", "fac_closed_ind"]).drop_duplicates(["tri_facility_id"], keep="first")
    tri["TRI_Is_Active"] = (~tri["fac_closed_ind"].eq("1")).astype(int)

    tri_grouped = (
        tri.groupby("GEOID", dropna=False)
        .agg(
            EPA_TRI_Facility_Count=("tri_facility_id", "nunique"),
            EPA_TRI_Active_Facility_Count=("TRI_Is_Active", "sum"),
        )
        .reset_index()
    )

    tri_grouped = tri_grouped.merge(counties_area[["GEOID", "County_Area_km2"]], on="GEOID", how="left")
    tri_grouped["EPA_TRI_Facility_Density_per_1000km2"] = (
        tri_grouped["EPA_TRI_Active_Facility_Count"] / tri_grouped["County_Area_km2"] * 1000.0
    ).where(tri_grouped["County_Area_km2"] > 0)

    out = out.merge(
        tri_grouped[["GEOID", "EPA_TRI_Facility_Count", "EPA_TRI_Active_Facility_Count", "EPA_TRI_Facility_Density_per_1000km2"]],
        on="GEOID",
        how="left",
    )

    for col in ["EPA_TRI_Facility_Count", "EPA_TRI_Active_Facility_Count", "EPA_TRI_Facility_Density_per_1000km2"]:
        out[col] = _num(out.get(col)).fillna(0.0)

    if COUNTY_STATS_CSV.exists():
        stats = pd.read_csv(COUNTY_STATS_CSV)
        if "GEOID" in stats.columns:
            stats["GEOID"] = _coerce_fips(stats["GEOID"])
            keep = [c for c in ["GEOID", "Total_Population", "Poverty_Rate_Percent", "Pct_Minority"] if c in stats.columns]
            out = out.merge(stats[keep], on="GEOID", how="left")

    out["Total_Population"] = _num(out.get("Total_Population")).fillna(0)
    out["Chicago_311_Noise_per_100k"] = (
        out["Chicago_311_Noise_AnnualAvg_Recent3yr"] / out["Total_Population"] * 100000.0
    ).where(out["Total_Population"] > 0, 0.0)
    out["EPA_TRI_Active_Facilities_per_100k"] = (
        out["EPA_TRI_Active_Facility_Count"] / out["Total_Population"] * 100000.0
    ).where(out["Total_Population"] > 0, 0.0)

    out["tri_count_log"] = _num(out["EPA_TRI_Active_Facility_Count"]).fillna(0).map(lambda v: math.log1p(max(v, 0)))
    out["tri_density_log"] = _num(out["EPA_TRI_Facility_Density_per_1000km2"]).fillna(0).map(
        lambda v: math.log1p(max(v, 0))
    )
    out["tri_per_100k_log"] = _num(out["EPA_TRI_Active_Facilities_per_100k"]).fillna(0).map(
        lambda v: math.log1p(max(v, 0))
    )
    out["EPA_TRI_Industrial_Pressure_Index"] = (
        (
            _norm(out["tri_count_log"]).fillna(0) * 0.55
            + _norm(out["tri_density_log"]).fillna(0) * 0.25
            + _norm(out["tri_per_100k_log"]).fillna(0) * 0.20
        )
        * 100.0
    ).round(1)

    out["noise_proxy_n"] = _norm(out["FAA_Noise_Exposure_Index"]).fillna(0)
    out["complaints_n"] = _norm(out["Chicago_311_Noise_per_100k"]).fillna(0)
    out["industrial_n"] = _norm(out["EPA_TRI_Industrial_Pressure_Index"]).fillna(0)
    out["poverty_n"] = _norm(out.get("Poverty_Rate_Percent")).fillna(0)
    out["minority_n"] = _norm(out.get("Pct_Minority")).fillna(0)
    out["community_vulnerability_n"] = (out["poverty_n"] * 0.6 + out["minority_n"] * 0.4).fillna(0)

    out["Noise_Community_Impact_Index"] = (
        (
            out["noise_proxy_n"] * 0.5
            + out["complaints_n"] * 0.2
            + out["industrial_n"] * 0.15
            + out["community_vulnerability_n"] * 0.15
        )
        * 100.0
    ).round(1)

    out["Noise_Community_Data_Year_Max"] = latest_complete_year
    out["Noise_Community_Recent_Window"] = (
        f"{min(recent_years)}-{max(recent_years)}" if recent_years else pd.NA
    )
    out["Noise_Community_Source"] = (
        "FAA airports FeatureServer + Chicago 311 noise requests + EPA TRI facility registry (Illinois)"
    )

    keep_cols = [
        "GEOID",
        "County_Name",
        "FAA_Airport_Count",
        "FAA_Airports_With_Operations",
        "FAA_Airports_With_Enplanements",
        "FAA_Airport_Operations_Total",
        "FAA_Enplanements_Total",
        "FAA_Passengers_Total",
        "FAA_Airport_Density_per_1000km2",
        "FAA_Noise_Exposure_Index",
        "Chicago_311_Noise_AnnualAvg_Recent3yr",
        "Chicago_311_Noise_Total_Recent3yr",
        "Chicago_311_Industrial_Total_Recent3yr",
        "Chicago_311_Noise_per_100k",
        "EPA_TRI_Facility_Count",
        "EPA_TRI_Active_Facility_Count",
        "EPA_TRI_Facility_Density_per_1000km2",
        "EPA_TRI_Active_Facilities_per_100k",
        "EPA_TRI_Industrial_Pressure_Index",
        "Noise_Community_Impact_Index",
        "Noise_Community_Data_Year_Max",
        "Noise_Community_Recent_Window",
        "Noise_Community_Source",
    ]
    out = out[[c for c in keep_cols if c in out.columns]].copy()

    numeric_cols = [
        "FAA_Airport_Count",
        "FAA_Airports_With_Operations",
        "FAA_Airports_With_Enplanements",
        "FAA_Airport_Operations_Total",
        "FAA_Enplanements_Total",
        "FAA_Passengers_Total",
        "FAA_Airport_Density_per_1000km2",
        "FAA_Noise_Exposure_Index",
        "Chicago_311_Noise_AnnualAvg_Recent3yr",
        "Chicago_311_Noise_Total_Recent3yr",
        "Chicago_311_Industrial_Total_Recent3yr",
        "Chicago_311_Noise_per_100k",
        "EPA_TRI_Facility_Count",
        "EPA_TRI_Active_Facility_Count",
        "EPA_TRI_Facility_Density_per_1000km2",
        "EPA_TRI_Active_Facilities_per_100k",
        "EPA_TRI_Industrial_Pressure_Index",
        "Noise_Community_Impact_Index",
    ]
    for col in numeric_cols:
        if col in out.columns:
            out[col] = _num(out[col]).round(2)

    return out.sort_values("GEOID").reset_index(drop=True)


def build_il_noise_community_layer(download_raw: bool = True, start_year: int = 2019) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if download_raw:
        _download_faa_il_airports()
        noise_annual, _ = _download_chicago_noise_tables(start_year=start_year)
        tri_facilities = _download_epa_tri_facilities()
    else:
        if not FAA_RAW_GEOJSON.exists():
            raise FileNotFoundError(f"Missing FAA airports file: {FAA_RAW_GEOJSON}")
        if not CHI_NOISE_ANNUAL_CSV.exists():
            raise FileNotFoundError(f"Missing Chicago noise annual file: {CHI_NOISE_ANNUAL_CSV}")
        if not EPA_TRI_FACILITIES_CSV.exists():
            raise FileNotFoundError(f"Missing EPA TRI facilities file: {EPA_TRI_FACILITIES_CSV}")

        try:
            noise_annual = pd.read_csv(CHI_NOISE_ANNUAL_CSV)
        except EmptyDataError:
            noise_annual = pd.DataFrame(columns=["year", "noise_count"])
        try:
            tri_facilities = pd.read_csv(EPA_TRI_FACILITIES_CSV)
        except EmptyDataError:
            tri_facilities = pd.DataFrame(columns=["tri_facility_id", "state_county_fips_code", "fac_closed_ind"])

    county = _build_county_layer(noise_annual=noise_annual, tri_facilities=tri_facilities)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    county.to_csv(OUT_CSV, index=False)
    return county


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Illinois county noise + community impact layer.")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Reuse existing raw files in data/raw/noise instead of downloading again.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2019,
        help="Start year for Chicago 311 aggregation queries.",
    )
    args = parser.parse_args()

    df = build_il_noise_community_layer(download_raw=not args.no_download, start_year=args.start_year)
    print(f"Wrote: {OUT_CSV} ({len(df)} counties)")
