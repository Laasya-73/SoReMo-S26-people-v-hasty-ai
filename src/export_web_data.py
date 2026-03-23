from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.scoring import DEFAULT_SCORING_WEIGHTS


ROOT = Path(__file__).resolve().parents[1]

BOUNDARIES_SHP = ROOT / "data/boundaries/IL_County_Boundaries.shp"
SITES_CSV = ROOT / "data/processed/il_sites_enhanced.csv"
COUNTY_STATS_CSV = ROOT / "data/processed/il_county_stats_enhanced.csv"
AQI_CSV = ROOT / "data/raw/annual_aqi_by_county_2025.csv"
LEAD_CSV = ROOT / "data/raw/LEADTool_Data Counties.csv"
ENERGY_XLSB = ROOT / "data/raw/2016cityandcountyenergyprofiles.xlsb"
WATER_STRESS_CSV = ROOT / "data/processed/il_county_water_stress.csv"
GRID_EMISSIONS_CSV = ROOT / "data/processed/il_county_grid_emissions.csv"
HEAT_CLIMATE_CSV = ROOT / "data/processed/il_county_heat_climate.csv"
NOISE_COMMUNITY_CSV = ROOT / "data/processed/il_county_noise_community.csv"
JUSTICE_CSV = ROOT / "data/processed/il_county_justice.csv"
LAND_USE_ZONING_CSV = ROOT / "data/processed/il_county_land_use_zoning.csv"
IL_DC_REGISTRY_CSV = ROOT / "data/processed/il_datacenters_registry.csv"
GLOBAL_DC_REGISTRY_CSV = ROOT / "data/processed/global_datacenters_registry.csv"

WEB_DATA_DIR = ROOT / "web/public/data"
OUT_COUNTIES_GEOJSON = WEB_DATA_DIR / "il_counties.geojson"
OUT_SITES_GEOJSON = WEB_DATA_DIR / "il_sites.geojson"
OUT_METADATA_JSON = WEB_DATA_DIR / "map_metadata.json"
OUT_GLOBAL_DC_GEOJSON = WEB_DATA_DIR / "global_datacenters_registry.geojson"
OUT_IL_DC_GEOJSON = WEB_DATA_DIR / "il_datacenters_registry.geojson"


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


def _find_col(df: pd.DataFrame, base_name: str) -> str | None:
    if base_name in df.columns:
        return base_name
    for c in df.columns:
        if c == base_name or c.startswith(base_name + "__"):
            return c
    return None


def _read_lead_county_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, skiprows=8)
    df.columns = _make_unique_columns(df.columns)
    return df


def _read_energy_profiles_xlsb_county(path: Path) -> pd.DataFrame:
    from pyxlsb import open_workbook

    rows = []
    with open_workbook(str(path)) as wb:
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


def _minmax(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().empty:
        return s
    mn = float(s.min())
    mx = float(s.max())
    if mx == mn:
        return s * 0
    return (s - mn) / (mx - mn)


def _weighted_composite_score(
    df: pd.DataFrame,
    components: list[tuple[str, float]],
    invert_fields: set[str] | None = None,
) -> pd.Series:
    invert_fields = invert_fields or set()
    acc = pd.Series(0.0, index=df.index, dtype=float)
    weight_sum = pd.Series(0.0, index=df.index, dtype=float)

    for field, weight in components:
        if field not in df.columns:
            continue
        comp = _minmax(df[field])
        if field in invert_fields:
            comp = 1 - comp
        valid = comp.notna()
        acc.loc[valid] += comp.loc[valid] * weight
        weight_sum.loc[valid] += weight

    out = pd.Series(float("nan"), index=df.index, dtype="float64")
    valid_rows = weight_sum > 0
    out.loc[valid_rows] = ((acc.loc[valid_rows] / weight_sum.loc[valid_rows]) * 100).round(1)
    return out


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


def _pressure_by_geoid(sites: pd.DataFrame, scenario: str) -> pd.DataFrame:
    s = _classify_sites(sites)
    if "GEOID" not in s.columns:
        return pd.DataFrame(columns=["GEOID", "Pressure_Score"])

    s["GEOID"] = _coerce_fips(s["GEOID"])
    if scenario == "current":
        s = s[s["is_existing"]].copy()

    g = (
        s.groupby("GEOID", dropna=False)[["is_existing", "is_proposed", "is_denied", "is_inventory"]]
        .sum()
        .reset_index()
        .rename(
            columns={
                "is_existing": "Site_Count_Existing",
                "is_proposed": "Site_Count_Proposed",
                "is_denied": "Site_Count_Denied",
                "is_inventory": "Site_Count_Inventory",
            }
        )
    )

    for c in ["Site_Count_Existing", "Site_Count_Proposed", "Site_Count_Denied", "Site_Count_Inventory"]:
        g[c] = pd.to_numeric(g[c], errors="coerce").fillna(0)

    w = DEFAULT_SCORING_WEIGHTS["pressure"]
    g["Pressure_Score"] = (
        g["Site_Count_Existing"] * float(w["existing"])
        + g["Site_Count_Proposed"] * float(w["proposed"])
        + g["Site_Count_Denied"] * float(w["denied"])
        + g["Site_Count_Inventory"] * float(w["inventory"])
    ).round(2)
    return g


def _build_county_geodata() -> tuple[gpd.GeoDataFrame, int | None]:
    counties = gpd.read_file(BOUNDARIES_SHP)
    counties["GEOID"] = _coerce_fips(counties["GEOID"])

    counties = counties.to_crs(epsg=3857)
    counties["geometry"] = counties["geometry"].simplify(tolerance=200, preserve_topology=True)
    counties = counties.to_crs(epsg=4326)

    stats = pd.read_csv(COUNTY_STATS_CSV)
    stats["GEOID"] = _coerce_fips(stats["GEOID"])
    merged = counties.merge(stats, on="GEOID", how="left")
    merged["NAME_clean"] = merged["NAME"].astype(str).str.replace(" County", "", regex=False).str.strip().str.upper()

    latest_year: int | None = None
    if AQI_CSV.exists():
        aqi = pd.read_csv(AQI_CSV)
        aqi_il = aqi[aqi["State"].astype(str).str.strip().str.lower() == "illinois"].copy()
        aqi_il["Year"] = pd.to_numeric(aqi_il["Year"], errors="coerce")
        if not aqi_il["Year"].dropna().empty:
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
            ].rename(
                columns={
                    "90th Percentile AQI": "AQI_P90",
                    "Median AQI": "AQI_Median",
                    "Max AQI": "AQI_Max",
                    "Days Ozone": "Ozone_Days",
                    "Days PM2.5": "PM25_Days",
                    "Days with AQI": "AQI_Days_Total",
                }
            )
            merged = merged.merge(aqi_keep, left_on="NAME_clean", right_on="County_clean", how="left")

    if LEAD_CSV.exists():
        lead = _read_lead_county_csv(LEAD_CSV)
        if "Geography ID" in lead.columns:
            lead["GEOID"] = _coerce_fips(lead["Geography ID"])
            lead_keep = lead[
                [
                    c
                    for c in [
                        "GEOID",
                        "Energy Burden (% income)",
                        "Avg. Annual Energy Cost ($)",
                    ]
                    if c in lead.columns
                ]
            ].rename(
                columns={
                    "Energy Burden (% income)": "Energy_Burden_PctIncome",
                    "Avg. Annual Energy Cost ($)": "Avg_Annual_Energy_Cost_USD",
                }
            )
            merged = merged.merge(lead_keep, on="GEOID", how="left")

    if ENERGY_XLSB.exists():
        ep = _read_energy_profiles_xlsb_county(ENERGY_XLSB)
        state_col = _find_col(ep, "state_abbr")
        county_col = _find_col(ep, "county_id")
        cons_col = _find_col(ep, "consumption (MWh/capita)")
        if state_col and county_col and cons_col:
            ep_il = ep[ep[state_col].astype(str).str.upper() == "IL"].copy()
            ep_il["GEOID"] = _coerce_fips(ep_il[county_col])
            ep_keep = ep_il[["GEOID", cons_col]].rename(columns={cons_col: "Elec_Consumption_MWh_perCapita"})
            merged = merged.merge(ep_keep, on="GEOID", how="left")

    if WATER_STRESS_CSV.exists():
        water = pd.read_csv(WATER_STRESS_CSV)
        if "GEOID" in water.columns:
            water["GEOID"] = _coerce_fips(water["GEOID"])
            water_keep_cols = [
                c
                for c in [
                    "GEOID",
                    "Water_Stress_Index",
                    "Aqueduct_BWS_Score",
                    "Aqueduct_Drought_Score",
                    "Aqueduct_GWDecline_Score",
                    "Aqueduct_OverallPowerRisk_Score",
                    "Aqueduct_DefaultOverall_Score",
                    "Aqueduct_Coverage_Pct",
                ]
                if c in water.columns
            ]
            merged = merged.merge(water[water_keep_cols], on="GEOID", how="left")

    if GRID_EMISSIONS_CSV.exists():
        grid = pd.read_csv(GRID_EMISSIONS_CSV)
        if "GEOID" in grid.columns:
            grid["GEOID"] = _coerce_fips(grid["GEOID"])
            grid_keep_cols = [
                c
                for c in [
                    "GEOID",
                    "Grid_Primary_Subregion",
                    "Grid_Primary_Subregion_Area_Pct",
                    "Grid_Subregion_Coverage_Pct",
                    "Grid_Clean_Share_Pct",
                    "Grid_Fossil_Share_Pct",
                    "Grid_Carbon_Intensity_lb_per_MWh",
                    "Grid_Carbon_Intensity_kg_per_MWh",
                    "Grid_Est_CO2_kt_per_100MWyr",
                    "eGRID_Data_Year",
                ]
                if c in grid.columns
            ]
            merged = merged.merge(grid[grid_keep_cols], on="GEOID", how="left")

    if HEAT_CLIMATE_CSV.exists():
        heat = pd.read_csv(HEAT_CLIMATE_CSV)
        if "GEOID" in heat.columns:
            heat["GEOID"] = _coerce_fips(heat["GEOID"])
            heat_keep_cols = [
                c
                for c in [
                    "GEOID",
                    "NOAA_CDD_Recent5yr",
                    "NOAA_CDD_Trend_perDecade",
                    "NOAA_Tmax_Summer_Recent5yr_F",
                    "NOAA_Tmax_Summer_Trend_perDecade_F",
                    "NOAA_Heat_Data_Recent_Year",
                    "HWAV_AFREQ",
                    "HWAV_RISKS",
                    "HWAV_RISKR",
                    "HWAV_EALT",
                    "HWAV_EALR",
                    "HWAV_ALR_NPCTL",
                    "SOVI_SCORE",
                    "RESL_SCORE",
                    "EAL_SCORE",
                    "Heat_Climate_Stress_Index",
                    "Heat_Climate_Data_Coverage_Pct",
                ]
                if c in heat.columns
            ]
            merged = merged.merge(heat[heat_keep_cols], on="GEOID", how="left")

    if NOISE_COMMUNITY_CSV.exists():
        noise = pd.read_csv(NOISE_COMMUNITY_CSV)
        if "GEOID" in noise.columns:
            noise["GEOID"] = _coerce_fips(noise["GEOID"])
            noise_keep_cols = [
                c
                for c in [
                    "GEOID",
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
                ]
                if c in noise.columns
            ]
            merged = merged.merge(noise[noise_keep_cols], on="GEOID", how="left")

    if JUSTICE_CSV.exists():
        justice = pd.read_csv(JUSTICE_CSV)
        if "GEOID" in justice.columns:
            justice["GEOID"] = _coerce_fips(justice["GEOID"])
            justice_keep_cols = [
                c
                for c in [
                    "GEOID",
                    "EJScreen_Pop_Weighted_Minority_Pct",
                    "EJScreen_Pop_Weighted_LowIncome_Pct",
                    "EJScreen_Pop_Weighted_PM25",
                    "EJScreen_Pop_Weighted_Ozone",
                    "EJScreen_Pop_Weighted_DieselPM",
                    "EJScreen_Pollution_Burden_Index",
                    "EJScreen_Justice_Index",
                    "EP_POV150",
                    "EP_HBURD",
                    "EP_NOHSDP",
                    "EP_NOVEH",
                    "CDC_SVI_Overall_Pctl",
                    "CDC_SVI_Theme1_SES_Pctl",
                    "CDC_SVI_Theme2_HHDisability_Pctl",
                    "CDC_SVI_Theme3_MinorityLanguage_Pctl",
                    "CDC_SVI_Theme4_HousingTransport_Pctl",
                    "Social_Environmental_Justice_Index",
                    "Justice_Data_Coverage_Pct",
                ]
                if c in justice.columns
            ]
            merged = merged.merge(justice[justice_keep_cols], on="GEOID", how="left")

    if LAND_USE_ZONING_CSV.exists():
        land_use = pd.read_csv(LAND_USE_ZONING_CSV)
        if "GEOID" in land_use.columns:
            land_use["GEOID"] = _coerce_fips(land_use["GEOID"])
            land_use_keep_cols = [
                c
                for c in [
                    "GEOID",
                    "LandCover_Agricultural_Pct",
                    "LandCover_Forested_Pct",
                    "LandCover_UrbanBuiltUp_Pct",
                    "LandCover_Wetland_Pct",
                    "LandCover_Agricultural_Rank",
                    "LandCover_Forested_Rank",
                    "LandCover_UrbanBuiltUp_Rank",
                    "LandCover_Wetland_Rank",
                    "Total_Site_Count",
                    "Chicago_Zoning_Site_Covered_Count",
                    "Chicago_Zoning_Residential_Site_Count",
                    "Chicago_Zoning_Industrial_Site_Count",
                    "Chicago_Zoning_Commercial_Site_Count",
                    "Chicago_Zoning_Special_Site_Count",
                    "Chicago_Zoning_Residential_Nearby500m_Count",
                    "Chicago_Zoning_Coverage_Pct",
                    "Chicago_Zoning_Residential_Site_Share_Pct",
                    "Chicago_Zoning_IndustrialCommercial_Site_Share_Pct",
                    "Chicago_Zoning_Residential_Nearby500m_Share_Pct",
                    "Zoning_Annoyance_Threshold_Index",
                    "Zoning_Allowance_Index",
                    "LandUse_Zoning_Data_Coverage_Pct",
                ]
                if c in land_use.columns
            ]
            merged = merged.merge(land_use[land_use_keep_cols], on="GEOID", how="left")

    merged["Energy_Burden_PctIncome_disp"] = pd.to_numeric(merged.get("Energy_Burden_PctIncome"), errors="coerce")
    merged["Elec_Consumption_MWh_perCapita_disp"] = pd.to_numeric(
        merged.get("Elec_Consumption_MWh_perCapita"), errors="coerce"
    )
    merged["Water_Stress_Index"] = pd.to_numeric(merged.get("Water_Stress_Index"), errors="coerce")
    merged["Aqueduct_BWS_Score"] = pd.to_numeric(merged.get("Aqueduct_BWS_Score"), errors="coerce")
    merged["Aqueduct_Drought_Score"] = pd.to_numeric(merged.get("Aqueduct_Drought_Score"), errors="coerce")
    merged["Aqueduct_GWDecline_Score"] = pd.to_numeric(merged.get("Aqueduct_GWDecline_Score"), errors="coerce")
    merged["Aqueduct_OverallPowerRisk_Score"] = pd.to_numeric(
        merged.get("Aqueduct_OverallPowerRisk_Score"), errors="coerce"
    )
    merged["Aqueduct_DefaultOverall_Score"] = pd.to_numeric(
        merged.get("Aqueduct_DefaultOverall_Score"), errors="coerce"
    )
    merged["Aqueduct_Coverage_Pct"] = pd.to_numeric(merged.get("Aqueduct_Coverage_Pct"), errors="coerce")
    merged["Grid_Clean_Share_Pct"] = pd.to_numeric(merged.get("Grid_Clean_Share_Pct"), errors="coerce")
    merged["Grid_Fossil_Share_Pct"] = pd.to_numeric(merged.get("Grid_Fossil_Share_Pct"), errors="coerce")
    merged["Grid_Carbon_Intensity_lb_per_MWh"] = pd.to_numeric(
        merged.get("Grid_Carbon_Intensity_lb_per_MWh"), errors="coerce"
    )
    merged["Grid_Carbon_Intensity_kg_per_MWh"] = pd.to_numeric(
        merged.get("Grid_Carbon_Intensity_kg_per_MWh"), errors="coerce"
    )
    merged["Grid_Est_CO2_kt_per_100MWyr"] = pd.to_numeric(
        merged.get("Grid_Est_CO2_kt_per_100MWyr"), errors="coerce"
    )
    merged["NOAA_CDD_Recent5yr"] = pd.to_numeric(merged.get("NOAA_CDD_Recent5yr"), errors="coerce")
    merged["NOAA_CDD_Trend_perDecade"] = pd.to_numeric(merged.get("NOAA_CDD_Trend_perDecade"), errors="coerce")
    merged["NOAA_Tmax_Summer_Recent5yr_F"] = pd.to_numeric(
        merged.get("NOAA_Tmax_Summer_Recent5yr_F"), errors="coerce"
    )
    merged["NOAA_Tmax_Summer_Trend_perDecade_F"] = pd.to_numeric(
        merged.get("NOAA_Tmax_Summer_Trend_perDecade_F"), errors="coerce"
    )
    merged["HWAV_AFREQ"] = pd.to_numeric(merged.get("HWAV_AFREQ"), errors="coerce")
    merged["HWAV_RISKS"] = pd.to_numeric(merged.get("HWAV_RISKS"), errors="coerce")
    merged["HWAV_EALT"] = pd.to_numeric(merged.get("HWAV_EALT"), errors="coerce")
    merged["HWAV_ALR_NPCTL"] = pd.to_numeric(merged.get("HWAV_ALR_NPCTL"), errors="coerce")
    merged["SOVI_SCORE"] = pd.to_numeric(merged.get("SOVI_SCORE"), errors="coerce")
    merged["RESL_SCORE"] = pd.to_numeric(merged.get("RESL_SCORE"), errors="coerce")
    merged["EAL_SCORE"] = pd.to_numeric(merged.get("EAL_SCORE"), errors="coerce")
    merged["Heat_Climate_Stress_Index"] = pd.to_numeric(
        merged.get("Heat_Climate_Stress_Index"), errors="coerce"
    )
    merged["Heat_Climate_Data_Coverage_Pct"] = pd.to_numeric(
        merged.get("Heat_Climate_Data_Coverage_Pct"), errors="coerce"
    )
    merged["FAA_Airport_Count"] = pd.to_numeric(merged.get("FAA_Airport_Count"), errors="coerce")
    merged["FAA_Airports_With_Operations"] = pd.to_numeric(
        merged.get("FAA_Airports_With_Operations"), errors="coerce"
    )
    merged["FAA_Airports_With_Enplanements"] = pd.to_numeric(
        merged.get("FAA_Airports_With_Enplanements"), errors="coerce"
    )
    merged["FAA_Airport_Operations_Total"] = pd.to_numeric(
        merged.get("FAA_Airport_Operations_Total"), errors="coerce"
    )
    merged["FAA_Enplanements_Total"] = pd.to_numeric(merged.get("FAA_Enplanements_Total"), errors="coerce")
    merged["FAA_Passengers_Total"] = pd.to_numeric(merged.get("FAA_Passengers_Total"), errors="coerce")
    merged["FAA_Airport_Density_per_1000km2"] = pd.to_numeric(
        merged.get("FAA_Airport_Density_per_1000km2"), errors="coerce"
    )
    merged["FAA_Noise_Exposure_Index"] = pd.to_numeric(merged.get("FAA_Noise_Exposure_Index"), errors="coerce")
    merged["Chicago_311_Noise_AnnualAvg_Recent3yr"] = pd.to_numeric(
        merged.get("Chicago_311_Noise_AnnualAvg_Recent3yr"), errors="coerce"
    )
    merged["Chicago_311_Noise_Total_Recent3yr"] = pd.to_numeric(
        merged.get("Chicago_311_Noise_Total_Recent3yr"), errors="coerce"
    )
    merged["Chicago_311_Industrial_Total_Recent3yr"] = pd.to_numeric(
        merged.get("Chicago_311_Industrial_Total_Recent3yr"), errors="coerce"
    )
    merged["Chicago_311_Noise_per_100k"] = pd.to_numeric(merged.get("Chicago_311_Noise_per_100k"), errors="coerce")
    merged["EPA_TRI_Facility_Count"] = pd.to_numeric(merged.get("EPA_TRI_Facility_Count"), errors="coerce")
    merged["EPA_TRI_Active_Facility_Count"] = pd.to_numeric(
        merged.get("EPA_TRI_Active_Facility_Count"), errors="coerce"
    )
    merged["EPA_TRI_Facility_Density_per_1000km2"] = pd.to_numeric(
        merged.get("EPA_TRI_Facility_Density_per_1000km2"), errors="coerce"
    )
    merged["EPA_TRI_Active_Facilities_per_100k"] = pd.to_numeric(
        merged.get("EPA_TRI_Active_Facilities_per_100k"), errors="coerce"
    )
    merged["EPA_TRI_Industrial_Pressure_Index"] = pd.to_numeric(
        merged.get("EPA_TRI_Industrial_Pressure_Index"), errors="coerce"
    )
    merged["Noise_Community_Impact_Index"] = pd.to_numeric(
        merged.get("Noise_Community_Impact_Index"), errors="coerce"
    )
    merged["EJScreen_Pop_Weighted_Minority_Pct"] = pd.to_numeric(
        merged.get("EJScreen_Pop_Weighted_Minority_Pct"), errors="coerce"
    )
    merged["EJScreen_Pop_Weighted_LowIncome_Pct"] = pd.to_numeric(
        merged.get("EJScreen_Pop_Weighted_LowIncome_Pct"), errors="coerce"
    )
    merged["EJScreen_Pop_Weighted_PM25"] = pd.to_numeric(
        merged.get("EJScreen_Pop_Weighted_PM25"), errors="coerce"
    )
    merged["EJScreen_Pop_Weighted_Ozone"] = pd.to_numeric(
        merged.get("EJScreen_Pop_Weighted_Ozone"), errors="coerce"
    )
    merged["EJScreen_Pop_Weighted_DieselPM"] = pd.to_numeric(
        merged.get("EJScreen_Pop_Weighted_DieselPM"), errors="coerce"
    )
    merged["EJScreen_Pollution_Burden_Index"] = pd.to_numeric(
        merged.get("EJScreen_Pollution_Burden_Index"), errors="coerce"
    )
    merged["EJScreen_Justice_Index"] = pd.to_numeric(merged.get("EJScreen_Justice_Index"), errors="coerce")
    merged["EP_POV150"] = pd.to_numeric(merged.get("EP_POV150"), errors="coerce")
    merged["EP_HBURD"] = pd.to_numeric(merged.get("EP_HBURD"), errors="coerce")
    merged["EP_NOHSDP"] = pd.to_numeric(merged.get("EP_NOHSDP"), errors="coerce")
    merged["EP_NOVEH"] = pd.to_numeric(merged.get("EP_NOVEH"), errors="coerce")
    merged["CDC_SVI_Overall_Pctl"] = pd.to_numeric(merged.get("CDC_SVI_Overall_Pctl"), errors="coerce")
    merged["CDC_SVI_Theme1_SES_Pctl"] = pd.to_numeric(merged.get("CDC_SVI_Theme1_SES_Pctl"), errors="coerce")
    merged["CDC_SVI_Theme2_HHDisability_Pctl"] = pd.to_numeric(
        merged.get("CDC_SVI_Theme2_HHDisability_Pctl"), errors="coerce"
    )
    merged["CDC_SVI_Theme3_MinorityLanguage_Pctl"] = pd.to_numeric(
        merged.get("CDC_SVI_Theme3_MinorityLanguage_Pctl"), errors="coerce"
    )
    merged["CDC_SVI_Theme4_HousingTransport_Pctl"] = pd.to_numeric(
        merged.get("CDC_SVI_Theme4_HousingTransport_Pctl"), errors="coerce"
    )
    merged["Social_Environmental_Justice_Index"] = pd.to_numeric(
        merged.get("Social_Environmental_Justice_Index"), errors="coerce"
    )
    merged["Justice_Data_Coverage_Pct"] = pd.to_numeric(merged.get("Justice_Data_Coverage_Pct"), errors="coerce")
    merged["LandCover_Agricultural_Pct"] = pd.to_numeric(
        merged.get("LandCover_Agricultural_Pct"), errors="coerce"
    )
    merged["LandCover_Forested_Pct"] = pd.to_numeric(merged.get("LandCover_Forested_Pct"), errors="coerce")
    merged["LandCover_UrbanBuiltUp_Pct"] = pd.to_numeric(
        merged.get("LandCover_UrbanBuiltUp_Pct"), errors="coerce"
    )
    merged["LandCover_Wetland_Pct"] = pd.to_numeric(merged.get("LandCover_Wetland_Pct"), errors="coerce")
    merged["LandCover_Agricultural_Rank"] = pd.to_numeric(
        merged.get("LandCover_Agricultural_Rank"), errors="coerce"
    )
    merged["LandCover_Forested_Rank"] = pd.to_numeric(
        merged.get("LandCover_Forested_Rank"), errors="coerce"
    )
    merged["LandCover_UrbanBuiltUp_Rank"] = pd.to_numeric(
        merged.get("LandCover_UrbanBuiltUp_Rank"), errors="coerce"
    )
    merged["LandCover_Wetland_Rank"] = pd.to_numeric(merged.get("LandCover_Wetland_Rank"), errors="coerce")
    merged["Chicago_Zoning_Site_Covered_Count"] = pd.to_numeric(
        merged.get("Chicago_Zoning_Site_Covered_Count"), errors="coerce"
    )
    merged["Chicago_Zoning_Residential_Site_Count"] = pd.to_numeric(
        merged.get("Chicago_Zoning_Residential_Site_Count"), errors="coerce"
    )
    merged["Chicago_Zoning_Industrial_Site_Count"] = pd.to_numeric(
        merged.get("Chicago_Zoning_Industrial_Site_Count"), errors="coerce"
    )
    merged["Chicago_Zoning_Commercial_Site_Count"] = pd.to_numeric(
        merged.get("Chicago_Zoning_Commercial_Site_Count"), errors="coerce"
    )
    merged["Chicago_Zoning_Special_Site_Count"] = pd.to_numeric(
        merged.get("Chicago_Zoning_Special_Site_Count"), errors="coerce"
    )
    merged["Chicago_Zoning_Residential_Nearby500m_Count"] = pd.to_numeric(
        merged.get("Chicago_Zoning_Residential_Nearby500m_Count"), errors="coerce"
    )
    merged["Chicago_Zoning_Coverage_Pct"] = pd.to_numeric(
        merged.get("Chicago_Zoning_Coverage_Pct"), errors="coerce"
    )
    merged["Chicago_Zoning_Residential_Site_Share_Pct"] = pd.to_numeric(
        merged.get("Chicago_Zoning_Residential_Site_Share_Pct"), errors="coerce"
    )
    merged["Chicago_Zoning_IndustrialCommercial_Site_Share_Pct"] = pd.to_numeric(
        merged.get("Chicago_Zoning_IndustrialCommercial_Site_Share_Pct"), errors="coerce"
    )
    merged["Chicago_Zoning_Residential_Nearby500m_Share_Pct"] = pd.to_numeric(
        merged.get("Chicago_Zoning_Residential_Nearby500m_Share_Pct"), errors="coerce"
    )
    merged["Zoning_Annoyance_Threshold_Index"] = pd.to_numeric(
        merged.get("Zoning_Annoyance_Threshold_Index"), errors="coerce"
    )
    merged["Zoning_Allowance_Index"] = pd.to_numeric(merged.get("Zoning_Allowance_Index"), errors="coerce")
    merged["LandUse_Zoning_Data_Coverage_Pct"] = pd.to_numeric(
        merged.get("LandUse_Zoning_Data_Coverage_Pct"), errors="coerce"
    )

    pov_n = _minmax(merged.get("Poverty_Rate_Percent"))
    min_n = _minmax(merged.get("Pct_Minority"))
    merged["Impact_Score"] = ((0.55 * pov_n + 0.45 * min_n) * 100).round(1)

    ew = DEFAULT_SCORING_WEIGHTS["economic"]
    merged["Economic_Vulnerability_Score"] = _weighted_composite_score(
        merged,
        components=[
            ("Poverty_Rate_Percent", float(ew["poverty"])),
            ("Pct_Minority", float(ew["minority"])),
            ("Median_Household_Income", float(ew["income"])),
            ("Median_Monthly_Housing_Cost", float(ew["housing"])),
            ("Energy_Burden_PctIncome_disp", float(ew["energy"])),
        ],
        invert_fields={"Median_Household_Income"},
    )

    cw = DEFAULT_SCORING_WEIGHTS["cumulative"]
    merged["Cumulative_Burden_Score"] = _weighted_composite_score(
        merged,
        components=[
            ("AQI_P90", float(cw["aqi"])),
            ("Ozone_Days", float(cw["ozone"])),
            ("PM25_Days", float(cw["pm25"])),
            ("Energy_Burden_PctIncome_disp", float(cw["energy"])),
            ("Elec_Consumption_MWh_perCapita_disp", float(cw["electricity"])),
        ],
    )

    sites = pd.read_csv(SITES_CSV)
    pressure_current = _pressure_by_geoid(sites, scenario="current").rename(
        columns={"Pressure_Score": "Pressure_Score_Current"}
    )
    pressure_planned = _pressure_by_geoid(sites, scenario="planned").rename(
        columns={"Pressure_Score": "Pressure_Score_Planned"}
    )
    merged = merged.merge(pressure_current[["GEOID", "Pressure_Score_Current"]], on="GEOID", how="left")
    merged = merged.merge(pressure_planned[["GEOID", "Pressure_Score_Planned"]], on="GEOID", how="left")

    merged["Pressure_Score_Current"] = pd.to_numeric(merged["Pressure_Score_Current"], errors="coerce").fillna(0.0)
    merged["Pressure_Score_Planned"] = pd.to_numeric(merged["Pressure_Score_Planned"], errors="coerce").fillna(0.0)
    merged["DC_Carbon_Exposure_Index"] = (
        merged["Pressure_Score_Planned"] * merged["Grid_Carbon_Intensity_kg_per_MWh"]
    ).round(2)
    merged["DC_Heat_Feedback_Index"] = (
        merged["Pressure_Score_Planned"] * merged["Heat_Climate_Stress_Index"]
    ).round(2)
    merged["DC_Noise_Community_Overlap_Index"] = (
        merged["Pressure_Score_Planned"] * merged["Noise_Community_Impact_Index"]
    ).round(2)

    return merged, latest_year


def _build_sites_geodata() -> gpd.GeoDataFrame:
    s = pd.read_csv(SITES_CSV)
    s = _classify_sites(s)
    s["GEOID"] = _coerce_fips(s["GEOID"])

    status = pd.Series("proposed", index=s.index, dtype=object)
    status = status.where(~s["is_existing"], "existing")
    status = status.where(~s["is_denied"], "denied")
    status = status.where(~s["is_inventory"], "inventory")
    s["status_class"] = status

    s["lat"] = pd.to_numeric(s["lat"], errors="coerce")
    s["lon"] = pd.to_numeric(s["lon"], errors="coerce")
    s = s[s["lat"].notna() & s["lon"].notna()].copy()

    keep_cols = [
        "site_id",
        "name",
        "layer",
        "status_class",
        "operator",
        "city",
        "state",
        "County_Name",
        "GEOID",
        "surroundings_snapshot",
        "community_signals",
        "stressors",
        "sources",
        "lat",
        "lon",
    ]
    s_keep = s[[c for c in keep_cols if c in s.columns]].copy()
    gdf = gpd.GeoDataFrame(s_keep, geometry=gpd.points_from_xy(s_keep["lon"], s_keep["lat"]), crs="EPSG:4326")

    if IL_DC_REGISTRY_CSV.exists():
        il_reg = pd.read_csv(IL_DC_REGISTRY_CSV).copy()
        if "source_system" in il_reg.columns:
            il_reg = il_reg[il_reg["source_system"].astype(str) != "SoReMo Curated"].copy()
        il_reg["lat"] = pd.to_numeric(il_reg.get("latitude"), errors="coerce")
        il_reg["lon"] = pd.to_numeric(il_reg.get("longitude"), errors="coerce")
        il_reg = il_reg[il_reg["lat"].notna() & il_reg["lon"].notna()].copy()
        if not il_reg.empty:
            reg_sites = pd.DataFrame(
                {
                    "site_id": il_reg.get("registry_id", "").astype(str),
                    "name": il_reg.get("name", "").astype(str),
                    "layer": "registry",
                    "status_class": "registry",
                    "operator": il_reg.get("operator", "").astype(str),
                    "city": il_reg.get("city", "").astype(str),
                    "state": il_reg.get("state", "").astype(str),
                    "County_Name": il_reg.get("County_Name", "").astype(str),
                    "GEOID": _coerce_fips(
                        il_reg.get("GEOID", pd.Series("", index=il_reg.index, dtype=object)).astype(str)
                    ),
                    "surroundings_snapshot": "External registry site record.",
                    "community_signals": "Imported from external data-center registry sources.",
                    "stressors": "Reference registry point for infrastructure concentration context.",
                    "sources": il_reg.get("source_url", "").fillna("").astype(str),
                    "data_source": il_reg.get("source_system", "Registry").fillna("Registry").astype(str),
                    "lat": il_reg["lat"],
                    "lon": il_reg["lon"],
                }
            )
            reg_gdf = gpd.GeoDataFrame(
                reg_sites,
                geometry=gpd.points_from_xy(reg_sites["lon"], reg_sites["lat"]),
                crs="EPSG:4326",
            )
            gdf["data_source"] = "SoReMo Curated"
            gdf = pd.concat([gdf, reg_gdf], ignore_index=True)

    return gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")


def _build_global_registry_geodata() -> gpd.GeoDataFrame:
    if not GLOBAL_DC_REGISTRY_CSV.exists():
        return gpd.GeoDataFrame(columns=["registry_id", "name", "geometry"], geometry="geometry", crs="EPSG:4326")

    df = pd.read_csv(GLOBAL_DC_REGISTRY_CSV).copy()
    df["latitude"] = pd.to_numeric(df.get("latitude"), errors="coerce")
    df["longitude"] = pd.to_numeric(df.get("longitude"), errors="coerce")
    df = df[df["latitude"].notna() & df["longitude"].notna()].copy()
    keep = [
        "registry_id",
        "source_record_id",
        "name",
        "operator",
        "provider_family",
        "city",
        "state",
        "country",
        "region_continent",
        "status",
        "website",
        "net_count",
        "ix_count",
        "carrier_count",
        "source_system",
        "source_url",
        "record_scope",
        "is_us",
        "is_illinois",
        "latitude",
        "longitude",
    ]
    keep = [c for c in keep if c in df.columns]
    out = df[keep].copy()
    gdf = gpd.GeoDataFrame(out, geometry=gpd.points_from_xy(out["longitude"], out["latitude"]), crs="EPSG:4326")
    return gdf


def _build_il_registry_geodata() -> gpd.GeoDataFrame:
    if not IL_DC_REGISTRY_CSV.exists():
        return gpd.GeoDataFrame(columns=["registry_id", "name", "geometry"], geometry="geometry", crs="EPSG:4326")

    df = pd.read_csv(IL_DC_REGISTRY_CSV).copy()
    df["latitude"] = pd.to_numeric(df.get("latitude"), errors="coerce")
    df["longitude"] = pd.to_numeric(df.get("longitude"), errors="coerce")
    df = df[df["latitude"].notna() & df["longitude"].notna()].copy()
    if "GEOID" in df.columns:
        df["GEOID"] = _coerce_fips(df["GEOID"])
    keep = [
        "registry_id",
        "source_record_id",
        "name",
        "operator",
        "provider_family",
        "city",
        "state",
        "country",
        "status",
        "source_system",
        "source_url",
        "record_scope",
        "GEOID",
        "County_Name",
        "latitude",
        "longitude",
    ]
    keep = [c for c in keep if c in df.columns]
    out = df[keep].copy()
    gdf = gpd.GeoDataFrame(out, geometry=gpd.points_from_xy(out["longitude"], out["latitude"]), crs="EPSG:4326")
    return gdf


def export_web_data() -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    counties_gdf, latest_aqi_year = _build_county_geodata()
    sites_gdf = _build_sites_geodata()
    global_registry_gdf = _build_global_registry_geodata()
    il_registry_gdf = _build_il_registry_geodata()

    counties_keep = [
        "GEOID",
        "NAME",
        "County_Name",
        "Impact_Score",
        "Pressure_Score_Current",
        "Pressure_Score_Planned",
        "Economic_Vulnerability_Score",
        "Cumulative_Burden_Score",
        "Poverty_Rate_Percent",
        "Pct_Minority",
        "Median_Household_Income",
        "AQI_P90",
        "Ozone_Days",
        "PM25_Days",
        "Energy_Burden_PctIncome_disp",
        "Avg_Annual_Energy_Cost_USD",
        "Elec_Consumption_MWh_perCapita_disp",
        "Water_Stress_Index",
        "Aqueduct_BWS_Score",
        "Aqueduct_Drought_Score",
        "Aqueduct_GWDecline_Score",
        "Aqueduct_OverallPowerRisk_Score",
        "Aqueduct_DefaultOverall_Score",
        "Aqueduct_Coverage_Pct",
        "Grid_Primary_Subregion",
        "Grid_Primary_Subregion_Area_Pct",
        "Grid_Subregion_Coverage_Pct",
        "Grid_Clean_Share_Pct",
        "Grid_Fossil_Share_Pct",
        "Grid_Carbon_Intensity_lb_per_MWh",
        "Grid_Carbon_Intensity_kg_per_MWh",
        "Grid_Est_CO2_kt_per_100MWyr",
        "DC_Carbon_Exposure_Index",
        "NOAA_CDD_Recent5yr",
        "NOAA_CDD_Trend_perDecade",
        "NOAA_Tmax_Summer_Recent5yr_F",
        "NOAA_Tmax_Summer_Trend_perDecade_F",
        "NOAA_Heat_Data_Recent_Year",
        "HWAV_AFREQ",
        "HWAV_RISKS",
        "HWAV_RISKR",
        "HWAV_EALT",
        "HWAV_EALR",
        "HWAV_ALR_NPCTL",
        "SOVI_SCORE",
        "RESL_SCORE",
        "EAL_SCORE",
        "Heat_Climate_Stress_Index",
        "Heat_Climate_Data_Coverage_Pct",
        "DC_Heat_Feedback_Index",
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
        "DC_Noise_Community_Overlap_Index",
        "Social_Environmental_Justice_Index",
        "EJScreen_Justice_Index",
        "EJScreen_Pollution_Burden_Index",
        "EJScreen_Pop_Weighted_Minority_Pct",
        "EJScreen_Pop_Weighted_LowIncome_Pct",
        "EJScreen_Pop_Weighted_PM25",
        "EJScreen_Pop_Weighted_Ozone",
        "EJScreen_Pop_Weighted_DieselPM",
        "CDC_SVI_Overall_Pctl",
        "CDC_SVI_Theme1_SES_Pctl",
        "CDC_SVI_Theme2_HHDisability_Pctl",
        "CDC_SVI_Theme3_MinorityLanguage_Pctl",
        "CDC_SVI_Theme4_HousingTransport_Pctl",
        "EP_POV150",
        "EP_HBURD",
        "EP_NOHSDP",
        "EP_NOVEH",
        "Justice_Data_Coverage_Pct",
        "LandCover_Agricultural_Pct",
        "LandCover_Forested_Pct",
        "LandCover_UrbanBuiltUp_Pct",
        "LandCover_Wetland_Pct",
        "LandCover_Agricultural_Rank",
        "LandCover_Forested_Rank",
        "LandCover_UrbanBuiltUp_Rank",
        "LandCover_Wetland_Rank",
        "Chicago_Zoning_Site_Covered_Count",
        "Chicago_Zoning_Residential_Site_Count",
        "Chicago_Zoning_Industrial_Site_Count",
        "Chicago_Zoning_Commercial_Site_Count",
        "Chicago_Zoning_Special_Site_Count",
        "Chicago_Zoning_Residential_Nearby500m_Count",
        "Chicago_Zoning_Coverage_Pct",
        "Chicago_Zoning_Residential_Site_Share_Pct",
        "Chicago_Zoning_IndustrialCommercial_Site_Share_Pct",
        "Chicago_Zoning_Residential_Nearby500m_Share_Pct",
        "Zoning_Annoyance_Threshold_Index",
        "Zoning_Allowance_Index",
        "LandUse_Zoning_Data_Coverage_Pct",
        "Noise_Community_Data_Year_Max",
        "Noise_Community_Recent_Window",
        "eGRID_Data_Year",
        "geometry",
    ]
    counties_out = counties_gdf[[c for c in counties_keep if c in counties_gdf.columns]].copy()
    if "County_Name" not in counties_out.columns and "NAME" in counties_out.columns:
        counties_out["County_Name"] = counties_out["NAME"].astype(str) + " County"

    counties_out.to_file(OUT_COUNTIES_GEOJSON, driver="GeoJSON")
    sites_gdf.to_file(OUT_SITES_GEOJSON, driver="GeoJSON")
    global_registry_gdf.to_file(OUT_GLOBAL_DC_GEOJSON, driver="GeoJSON")
    il_registry_gdf.to_file(OUT_IL_DC_GEOJSON, driver="GeoJSON")

    metadata = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "latest_aqi_year": latest_aqi_year,
        "weights": DEFAULT_SCORING_WEIGHTS,
        "datacenter_registry": {
            "illinois_count": int(len(il_registry_gdf)),
            "global_count": int(len(global_registry_gdf)),
            "sources": [
                "PeeringDB facilities API",
                "OpenStreetMap Overpass (data_center tags)",
                "SoReMo curated Illinois site list",
            ],
        },
        "county_layers": {
            "impact": {"label": "Community Impact Score", "property": "Impact_Score"},
            "pressure": {
                "label": "Data Center Pressure Score",
                "property_current": "Pressure_Score_Current",
                "property_planned": "Pressure_Score_Planned",
            },
            "economic": {"label": "Economic Vulnerability 2.0", "property": "Economic_Vulnerability_Score"},
            "cumulative": {"label": "Cumulative Burden (Air + Energy)", "property": "Cumulative_Burden_Score"},
            "poverty": {"label": "County Poverty Rate (%)", "property": "Poverty_Rate_Percent"},
            "minority": {"label": "County Minority Population (%)", "property": "Pct_Minority"},
            "aqi": {"label": "Air Quality (AQI P90)", "property": "AQI_P90"},
            "ozone": {"label": "Ozone Days", "property": "Ozone_Days"},
            "pm25": {"label": "PM2.5 Days", "property": "PM25_Days"},
            "energy_burden": {"label": "Energy Burden (% income)", "property": "Energy_Burden_PctIncome_disp"},
            "avg_energy_cost": {"label": "Avg Annual Household Energy Cost ($)", "property": "Avg_Annual_Energy_Cost_USD"},
            "electricity_use": {
                "label": "Electricity Use (MWh per capita)",
                "property": "Elec_Consumption_MWh_perCapita_disp",
            },
            "water_index": {"label": "Water Stress Index (Aqueduct, 0-100)", "property": "Water_Stress_Index"},
            "water_stress": {"label": "Baseline Water Stress (Aqueduct, 0-5)", "property": "Aqueduct_BWS_Score"},
            "water_drought": {"label": "Drought Risk (Aqueduct, 0-5)", "property": "Aqueduct_Drought_Score"},
            "water_groundwater": {
                "label": "Groundwater Table Decline (Aqueduct, 0-5)",
                "property": "Aqueduct_GWDecline_Score",
            },
            "water_power_risk": {
                "label": "Water Risk for Electric Power (Aqueduct, 0-5)",
                "property": "Aqueduct_OverallPowerRisk_Score",
            },
            "grid_clean_share": {"label": "Grid Clean Share (%)", "property": "Grid_Clean_Share_Pct"},
            "grid_fossil_share": {"label": "Grid Fossil Share (%)", "property": "Grid_Fossil_Share_Pct"},
            "grid_carbon_intensity": {
                "label": "Grid Carbon Intensity (kg CO2/MWh)",
                "property": "Grid_Carbon_Intensity_kg_per_MWh",
            },
            "grid_co2_100mw": {
                "label": "Estimated CO2 for 100 MW Load (kt/yr)",
                "property": "Grid_Est_CO2_kt_per_100MWyr",
            },
            "dc_carbon_exposure": {
                "label": "Data Center Carbon Exposure (pressure x kg CO2/MWh)",
                "property": "DC_Carbon_Exposure_Index",
            },
            "heat_climate_index": {
                "label": "Heat + Climate Stress Index (0-100)",
                "property": "Heat_Climate_Stress_Index",
            },
            "heat_cdd_recent": {
                "label": "NOAA Cooling Degree Days (5-yr avg)",
                "property": "NOAA_CDD_Recent5yr",
            },
            "heat_tmax_summer": {
                "label": "NOAA Summer Max Temp (5-yr avg, deg F)",
                "property": "NOAA_Tmax_Summer_Recent5yr_F",
            },
            "heat_fema_risk": {
                "label": "FEMA Heat Wave Risk Score",
                "property": "HWAV_RISKS",
            },
            "heat_fema_loss_pctile": {
                "label": "FEMA Heat Loss-Rate Percentile",
                "property": "HWAV_ALR_NPCTL",
            },
            "heat_feedback": {
                "label": "Data Center Heat Feedback (pressure x heat index)",
                "property": "DC_Heat_Feedback_Index",
            },
            "noise_community_index": {
                "label": "Noise + Community Impact Index (0-100)",
                "property": "Noise_Community_Impact_Index",
            },
            "noise_faa_exposure": {
                "label": "FAA Airport Noise Exposure Index (0-100)",
                "property": "FAA_Noise_Exposure_Index",
            },
            "noise_airport_density": {
                "label": "Airport Density (count per 1000 km2)",
                "property": "FAA_Airport_Density_per_1000km2",
            },
            "noise_ops_total": {
                "label": "Airport Operations Proxy (annual)",
                "property": "FAA_Airport_Operations_Total",
            },
            "noise_chicago_311": {
                "label": "Chicago 311 Noise Complaints (avg per year, recent 3 years)",
                "property": "Chicago_311_Noise_AnnualAvg_Recent3yr",
            },
            "noise_tri_facility_count": {
                "label": "EPA TRI Active Industrial Facilities (count)",
                "property": "EPA_TRI_Active_Facility_Count",
            },
            "noise_tri_pressure": {
                "label": "EPA TRI Industrial Pressure Index (0-100)",
                "property": "EPA_TRI_Industrial_Pressure_Index",
            },
            "noise_overlap": {
                "label": "Data Center Noise-Community Overlap (pressure x noise impact)",
                "property": "DC_Noise_Community_Overlap_Index",
            },
            "justice_index": {
                "label": "Social & Environmental Justice Index (0-100)",
                "property": "Social_Environmental_Justice_Index",
            },
            "justice_ejscreen": {
                "label": "EPA EJScreen Justice Index (0-100)",
                "property": "EJScreen_Justice_Index",
            },
            "justice_pollution": {
                "label": "EPA EJScreen Pollution Burden (0-100)",
                "property": "EJScreen_Pollution_Burden_Index",
            },
            "justice_lowincome": {
                "label": "EPA EJScreen Low-Income Population (%)",
                "property": "EJScreen_Pop_Weighted_LowIncome_Pct",
            },
            "justice_minority": {
                "label": "EPA EJScreen Minority Population (%)",
                "property": "EJScreen_Pop_Weighted_Minority_Pct",
            },
            "justice_svi_overall": {
                "label": "CDC SVI Overall Percentile",
                "property": "CDC_SVI_Overall_Pctl",
            },
            "justice_svi_housing_transport": {
                "label": "CDC SVI Housing & Transportation Percentile",
                "property": "CDC_SVI_Theme4_HousingTransport_Pctl",
            },
            "landcover_urban_builtup": {
                "label": "Land Cover: Urban/Built-Up (%)",
                "property": "LandCover_UrbanBuiltUp_Pct",
            },
            "landcover_agriculture": {
                "label": "Land Cover: Agricultural (%)",
                "property": "LandCover_Agricultural_Pct",
            },
            "landcover_forested": {
                "label": "Land Cover: Forested (%)",
                "property": "LandCover_Forested_Pct",
            },
            "landcover_wetland": {
                "label": "Land Cover: Wetland (%)",
                "property": "LandCover_Wetland_Pct",
            },
            "zoning_allowance": {
                "label": "Zoning Allowance Index (Industrial+Commercial share, %)",
                "property": "Zoning_Allowance_Index",
            },
            "zoning_annoyance_threshold": {
                "label": "Zoning Annoyance Threshold Index (0-100)",
                "property": "Zoning_Annoyance_Threshold_Index",
            },
            "zoning_residential_nearby": {
                "label": "Sites Near Residential Zoning (500m, % of county sites)",
                "property": "Chicago_Zoning_Residential_Nearby500m_Share_Pct",
            },
            "landuse_zoning_coverage": {
                "label": "Land Use/Zoning Data Coverage (%)",
                "property": "LandUse_Zoning_Data_Coverage_Pct",
            },
        },
    }

    OUT_METADATA_JSON.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Wrote: {OUT_COUNTIES_GEOJSON}")
    print(f"Wrote: {OUT_SITES_GEOJSON}")
    print(f"Wrote: {OUT_GLOBAL_DC_GEOJSON}")
    print(f"Wrote: {OUT_IL_DC_GEOJSON}")
    print(f"Wrote: {OUT_METADATA_JSON}")


if __name__ == "__main__":
    export_web_data()
