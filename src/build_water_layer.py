from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
COUNTY_SHP = ROOT / "data/boundaries/IL_County_Boundaries.shp"
AQUEDUCT_GDB = (
    ROOT
    / "data/raw/water/aqueduct-4-0/Aqueduct40_waterrisk_download_Y2023M07D05/GDB/Aq40_Y2023D07M05.gdb"
)
OUT_CSV = ROOT / "data/processed/il_county_water_stress.csv"


def _coerce_fips(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace(".0", "", regex=False)
    return s.str.zfill(5)


def _weighted_mean(df: pd.DataFrame, value_col: str, weight_col: str) -> float | None:
    v = pd.to_numeric(df[value_col], errors="coerce")
    w = pd.to_numeric(df[weight_col], errors="coerce")
    m = v.notna() & w.notna() & (w > 0)
    if not m.any():
        return None
    return float((v[m] * w[m]).sum() / w[m].sum())


def build_il_water_stress_layer() -> pd.DataFrame:
    if not AQUEDUCT_GDB.exists():
        raise FileNotFoundError(
            f"Aqueduct geodatabase not found at: {AQUEDUCT_GDB}\n"
            "Download and extract Aqueduct 4.0 first."
        )

    counties = gpd.read_file(COUNTY_SHP)[["GEOID", "NAME", "geometry"]].copy()
    counties["GEOID"] = _coerce_fips(counties["GEOID"])
    counties["County_Name"] = counties["NAME"].astype(str).str.strip() + " County"
    counties = counties.to_crs(epsg=4326)
    bbox = tuple(counties.total_bounds)

    aqueduct_cols = [
        "aq30_id",
        "bws_score",
        "drr_score",
        "gtd_score",
        "w_awr_elp_tot_score",
        "w_awr_def_tot_score",
        "geometry",
    ]
    aqueduct = gpd.read_file(
        AQUEDUCT_GDB,
        layer="baseline_annual",
        bbox=bbox,
        columns=aqueduct_cols,
    )
    score_cols = [
        "bws_score",
        "drr_score",
        "gtd_score",
        "w_awr_elp_tot_score",
        "w_awr_def_tot_score",
    ]
    for col in score_cols:
        aqueduct[col] = pd.to_numeric(aqueduct[col], errors="coerce")
        aqueduct[col] = aqueduct[col].where((aqueduct[col] >= 0) & (aqueduct[col] <= 5))

    aqueduct = aqueduct.to_crs(epsg=5070)
    counties_m = counties.to_crs(epsg=5070)

    intersections = gpd.overlay(counties_m, aqueduct, how="intersection")
    intersections["part_area_m2"] = intersections.geometry.area

    county_area = counties_m.copy()
    county_area["county_area_m2"] = county_area.geometry.area
    intersections = intersections.merge(
        county_area[["GEOID", "county_area_m2"]],
        on="GEOID",
        how="left",
    )

    rows: list[dict] = []
    for geoid, grp in intersections.groupby("GEOID"):
        county_name = grp["County_Name"].iloc[0]
        coverage_pct = float((grp["part_area_m2"].sum() / grp["county_area_m2"].iloc[0]) * 100.0)

        bws = _weighted_mean(grp, "bws_score", "part_area_m2")
        drought = _weighted_mean(grp, "drr_score", "part_area_m2")
        gw_decline = _weighted_mean(grp, "gtd_score", "part_area_m2")
        power_risk = _weighted_mean(grp, "w_awr_elp_tot_score", "part_area_m2")
        overall_risk = _weighted_mean(grp, "w_awr_def_tot_score", "part_area_m2")

        # Composite [0,100] for easy communication in map overlays:
        # higher means higher stress/risk context for cooling-water dependence.
        parts = []
        if bws is not None:
            parts.append((bws / 5.0, 0.40))
        if drought is not None:
            parts.append((drought / 5.0, 0.25))
        if gw_decline is not None:
            parts.append((gw_decline / 5.0, 0.20))
        if power_risk is not None:
            parts.append((power_risk / 5.0, 0.15))
        if parts:
            weight_sum = sum(w for _, w in parts)
            water_index = (sum(v * w for v, w in parts) / weight_sum) * 100.0
        else:
            water_index = None

        rows.append(
            {
                "GEOID": geoid,
                "County_Name": county_name,
                "Water_Stress_Index": round(float(water_index), 2) if water_index is not None else None,
                "Aqueduct_BWS_Score": round(float(bws), 3) if bws is not None else None,
                "Aqueduct_Drought_Score": round(float(drought), 3) if drought is not None else None,
                "Aqueduct_GWDecline_Score": round(float(gw_decline), 3) if gw_decline is not None else None,
                "Aqueduct_OverallPowerRisk_Score": round(float(power_risk), 3) if power_risk is not None else None,
                "Aqueduct_DefaultOverall_Score": round(float(overall_risk), 3) if overall_risk is not None else None,
                "Aqueduct_Coverage_Pct": round(coverage_pct, 1),
                "Aqueduct_Source": "WRI Aqueduct 4.0 baseline_annual (2023-07-05 release)",
            }
        )

    out = pd.DataFrame(rows).sort_values("GEOID").reset_index(drop=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    return out


if __name__ == "__main__":
    df = build_il_water_stress_layer()
    print(f"Wrote: {OUT_CSV} ({len(df)} counties)")
