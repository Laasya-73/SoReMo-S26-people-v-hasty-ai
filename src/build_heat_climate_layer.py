from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pandas as pd
import geopandas as gpd


ROOT = Path(__file__).resolve().parents[1]

COUNTY_SHP = ROOT / "data/boundaries/IL_County_Boundaries.shp"

RAW_DIR = ROOT / "data/raw/heat_climate"
NOAA_RAW_CSV = RAW_DIR / "noaa_il_county_heat_timeseries.csv"
FEMA_RAW_CSV = RAW_DIR / "fema_nri_il_county_heat.csv"

OUT_CSV = ROOT / "data/processed/il_county_heat_climate.csv"

FEMA_NRI_COUNTIES_QUERY = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/ArcGIS/rest/services/"
    "National_Risk_Index_Counties/FeatureServer/0/query"
)

NOAA_CAG_TEMPLATE = (
    "https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/county/time-series/"
    "{county_code}/{element}/{scale}/{month}/{start}-{end}.csv"
)


def _coerce_fips(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace(".0", "", regex=False)
    return s.str.zfill(5)


def _safe_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"API error: {payload['error']}")
    return payload


def _fetch_noaa_series(county_code: str, element: str, scale: int, month: int, start: int, end: int) -> pd.DataFrame:
    url = NOAA_CAG_TEMPLATE.format(
        county_code=county_code,
        element=element,
        scale=scale,
        month=month,
        start=start,
        end=end,
    )
    return pd.read_csv(url, comment="#")


def _trend_per_decade(years: pd.Series, values: pd.Series) -> float | None:
    x = _safe_num(years)
    y = _safe_num(values)
    m = x.notna() & y.notna()
    if m.sum() < 2:
        return None
    x = x[m].astype(float)
    y = y[m].astype(float)

    x_mean = x.mean()
    y_mean = y.mean()
    var = ((x - x_mean) ** 2).sum()
    if var == 0:
        return None
    slope_per_year = ((x - x_mean) * (y - y_mean)).sum() / var
    return float(slope_per_year * 10.0)


def _minmax(series: pd.Series) -> pd.Series:
    s = _safe_num(series)
    if s.dropna().empty:
        return s
    mn = float(s.min())
    mx = float(s.max())
    if mx == mn:
        return s * 0
    return (s - mn) / (mx - mn)


def _build_noaa_il_county_metrics(start_year: int = 2010, end_year: int = 2024, pause_s: float = 0.08) -> tuple[pd.DataFrame, pd.DataFrame]:
    counties = gpd.read_file(COUNTY_SHP)[["GEOID", "NAME"]].copy()
    counties["GEOID"] = _coerce_fips(counties["GEOID"])
    counties["County_Name"] = counties["NAME"].astype(str).str.strip() + " County"

    long_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for _, row in counties.iterrows():
        geoid = str(row["GEOID"])
        county_name = str(row["County_Name"])
        county_code = f"IL-{geoid[-3:]}"

        try:
            # Annual Cooling Degree Days (heat/cooling demand signal).
            cdd = _fetch_noaa_series(county_code, "cdd", 12, 12, start_year, end_year)
            cdd["Date"] = cdd["Date"].astype(str)
            cdd["Year"] = cdd["Date"].str.slice(0, 4).astype(int)
            cdd["Value"] = _safe_num(cdd["Value"])

            # Summer (Jun-Aug) maximum temperature.
            tmax_sum = _fetch_noaa_series(county_code, "tmax", 3, 8, start_year, end_year)
            tmax_sum["Date"] = tmax_sum["Date"].astype(str)
            tmax_sum["Year"] = tmax_sum["Date"].str.slice(0, 4).astype(int)
            tmax_sum["Value"] = _safe_num(tmax_sum["Value"])
        except Exception:
            summary_rows.append(
                {
                    "GEOID": geoid,
                    "County_Name": county_name,
                    "NOAA_CDD_Recent5yr": None,
                    "NOAA_CDD_Trend_perDecade": None,
                    "NOAA_Tmax_Summer_Recent5yr_F": None,
                    "NOAA_Tmax_Summer_Trend_perDecade_F": None,
                    "NOAA_Heat_Data_Recent_Year": None,
                }
            )
            continue

        recent_max_year = int(max(cdd["Year"].max(), tmax_sum["Year"].max()))
        recent_min_year = recent_max_year - 4

        cdd_recent = cdd[cdd["Year"].between(recent_min_year, recent_max_year)]["Value"].mean()
        tmax_recent = tmax_sum[tmax_sum["Year"].between(recent_min_year, recent_max_year)]["Value"].mean()

        cdd_trend = _trend_per_decade(cdd["Year"], cdd["Value"])
        tmax_trend = _trend_per_decade(tmax_sum["Year"], tmax_sum["Value"])

        summary_rows.append(
            {
                "GEOID": geoid,
                "County_Name": county_name,
                "NOAA_CDD_Recent5yr": round(float(cdd_recent), 2) if pd.notna(cdd_recent) else None,
                "NOAA_CDD_Trend_perDecade": round(float(cdd_trend), 3) if cdd_trend is not None else None,
                "NOAA_Tmax_Summer_Recent5yr_F": round(float(tmax_recent), 2) if pd.notna(tmax_recent) else None,
                "NOAA_Tmax_Summer_Trend_perDecade_F": round(float(tmax_trend), 3) if tmax_trend is not None else None,
                "NOAA_Heat_Data_Recent_Year": recent_max_year,
            }
        )

        for _, r in cdd.iterrows():
            long_rows.append(
                {
                    "GEOID": geoid,
                    "County_Name": county_name,
                    "County_Code": county_code,
                    "Series": "NOAA_CDD_Annual",
                    "Year": int(r["Year"]),
                    "Value": float(r["Value"]) if pd.notna(r["Value"]) else None,
                }
            )
        for _, r in tmax_sum.iterrows():
            long_rows.append(
                {
                    "GEOID": geoid,
                    "County_Name": county_name,
                    "County_Code": county_code,
                    "Series": "NOAA_Tmax_Summer",
                    "Year": int(r["Year"]),
                    "Value": float(r["Value"]) if pd.notna(r["Value"]) else None,
                }
            )

        if pause_s > 0:
            time.sleep(pause_s)

    noaa_long = pd.DataFrame(long_rows)
    noaa_summary = pd.DataFrame(summary_rows).sort_values("GEOID").reset_index(drop=True)
    return noaa_long, noaa_summary


def _download_fema_nri_il_heat() -> pd.DataFrame:
    fields = [
        "COUNTY",
        "STATEABBRV",
        "STCOFIPS",
        "EAL_SCORE",
        "SOVI_SCORE",
        "RESL_SCORE",
        "HWAV_AFREQ",
        "HWAV_RISKS",
        "HWAV_RISKR",
        "HWAV_EALT",
        "HWAV_EALR",
        "HWAV_ALR_NPCTL",
    ]
    out_fields = ",".join(fields)
    query = (
        f"{FEMA_NRI_COUNTIES_QUERY}"
        f"?where=STATEABBRV%3D%27IL%27"
        f"&outFields={out_fields}"
        f"&returnGeometry=false"
        f"&f=json"
    )
    payload = _fetch_json(query)
    feats = payload.get("features", [])
    rows = [(f.get("attributes") or {}) for f in feats]
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "STCOFIPS" in df.columns:
        df["GEOID"] = _coerce_fips(df["STCOFIPS"])
    if "COUNTY" in df.columns:
        df["County_Name"] = df["COUNTY"].astype(str).str.strip() + " County"

    num_cols = [
        "EAL_SCORE",
        "SOVI_SCORE",
        "RESL_SCORE",
        "HWAV_AFREQ",
        "HWAV_RISKS",
        "HWAV_EALT",
        "HWAV_ALR_NPCTL",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = _safe_num(df[c])

    return df


def build_il_heat_climate_layer(download_raw: bool = True, start_year: int = 2010, end_year: int = 2024) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if download_raw:
        noaa_long, noaa_summary = _build_noaa_il_county_metrics(start_year=start_year, end_year=end_year)
        fema = _download_fema_nri_il_heat()
        noaa_long.to_csv(NOAA_RAW_CSV, index=False)
        fema.to_csv(FEMA_RAW_CSV, index=False)
    else:
        if not NOAA_RAW_CSV.exists():
            raise FileNotFoundError(f"Missing NOAA raw CSV: {NOAA_RAW_CSV}")
        if not FEMA_RAW_CSV.exists():
            raise FileNotFoundError(f"Missing FEMA raw CSV: {FEMA_RAW_CSV}")

        noaa_long = pd.read_csv(NOAA_RAW_CSV)
        fema = pd.read_csv(FEMA_RAW_CSV)
        fema["GEOID"] = _coerce_fips(fema["GEOID"])
        noaa_long["GEOID"] = _coerce_fips(noaa_long["GEOID"])

        # Recompute NOAA summary from cached long file.
        cdd = noaa_long[noaa_long["Series"] == "NOAA_CDD_Annual"].copy()
        tmax = noaa_long[noaa_long["Series"] == "NOAA_Tmax_Summer"].copy()
        cdd["Year"] = _safe_num(cdd["Year"])
        cdd["Value"] = _safe_num(cdd["Value"])
        tmax["Year"] = _safe_num(tmax["Year"])
        tmax["Value"] = _safe_num(tmax["Value"])

        rows: list[dict[str, Any]] = []
        for geoid in sorted(noaa_long["GEOID"].dropna().astype(str).unique()):
            cdd_g = cdd[cdd["GEOID"] == geoid].copy()
            tmax_g = tmax[tmax["GEOID"] == geoid].copy()
            if cdd_g.empty and tmax_g.empty:
                continue
            county_name = (
                noaa_long.loc[noaa_long["GEOID"] == geoid, "County_Name"].dropna().astype(str).head(1).tolist()
                or [f"{geoid} County"]
            )[0]
            recent_max_year = int(max(cdd_g["Year"].max(), tmax_g["Year"].max()))
            recent_min_year = recent_max_year - 4
            cdd_recent = cdd_g[cdd_g["Year"].between(recent_min_year, recent_max_year)]["Value"].mean()
            tmax_recent = tmax_g[tmax_g["Year"].between(recent_min_year, recent_max_year)]["Value"].mean()
            rows.append(
                {
                    "GEOID": geoid,
                    "County_Name": county_name,
                    "NOAA_CDD_Recent5yr": round(float(cdd_recent), 2) if pd.notna(cdd_recent) else None,
                    "NOAA_CDD_Trend_perDecade": (
                        round(float(_trend_per_decade(cdd_g["Year"], cdd_g["Value"])), 3)
                        if _trend_per_decade(cdd_g["Year"], cdd_g["Value"]) is not None
                        else None
                    ),
                    "NOAA_Tmax_Summer_Recent5yr_F": round(float(tmax_recent), 2) if pd.notna(tmax_recent) else None,
                    "NOAA_Tmax_Summer_Trend_perDecade_F": (
                        round(float(_trend_per_decade(tmax_g["Year"], tmax_g["Value"])), 3)
                        if _trend_per_decade(tmax_g["Year"], tmax_g["Value"]) is not None
                        else None
                    ),
                    "NOAA_Heat_Data_Recent_Year": recent_max_year,
                }
            )
        noaa_summary = pd.DataFrame(rows).sort_values("GEOID").reset_index(drop=True)

    if noaa_summary.empty:
        raise RuntimeError("No NOAA county heat metrics generated.")
    if fema.empty:
        raise RuntimeError("No FEMA county heat metrics generated.")

    fema_keep = fema[
        [
            c
            for c in [
                "GEOID",
                "County_Name",
                "HWAV_AFREQ",
                "HWAV_RISKS",
                "HWAV_RISKR",
                "HWAV_EALT",
                "HWAV_EALR",
                "HWAV_ALR_NPCTL",
                "SOVI_SCORE",
                "RESL_SCORE",
                "EAL_SCORE",
            ]
            if c in fema.columns
        ]
    ].copy()

    merged = noaa_summary.merge(fema_keep, on=["GEOID", "County_Name"], how="outer")

    # Composite Heat + Climate Stress [0-100]:
    # - FEMA heat risk score captures hazard x exposure x vulnerability signal.
    # - FEMA heat annual loss-rate percentile captures national relative severity.
    # - NOAA CDD and summer Tmax capture observed thermal load and ambient heat.
    # - NOAA summer Tmax trend captures local warming acceleration.
    merged["NOAA_Tmax_Trend_Positive"] = _safe_num(merged["NOAA_Tmax_Summer_Trend_perDecade_F"]).clip(lower=0)
    c1 = _minmax(merged["HWAV_RISKS"])
    c2 = _minmax(merged["HWAV_ALR_NPCTL"])
    c3 = _minmax(merged["NOAA_CDD_Recent5yr"])
    c4 = _minmax(merged["NOAA_Tmax_Summer_Recent5yr_F"])
    c5 = _minmax(merged["NOAA_Tmax_Trend_Positive"])

    acc = pd.Series(0.0, index=merged.index, dtype=float)
    wsum = pd.Series(0.0, index=merged.index, dtype=float)
    parts = [(c1, 0.35), (c2, 0.2), (c3, 0.2), (c4, 0.15), (c5, 0.1)]
    for comp, w in parts:
        valid = comp.notna()
        acc.loc[valid] += comp.loc[valid] * w
        wsum.loc[valid] += w

    out = merged.copy()
    out["Heat_Climate_Stress_Index"] = pd.NA
    valid_rows = wsum > 0
    out.loc[valid_rows, "Heat_Climate_Stress_Index"] = ((acc.loc[valid_rows] / wsum.loc[valid_rows]) * 100).round(1)
    out["Heat_Climate_Data_Coverage_Pct"] = (wsum / 1.0 * 100.0).round(1)
    out["Heat_Climate_Source"] = (
        "NOAA Climate at a Glance county API (NCEI) + FEMA National Risk Index Counties service"
    )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.sort_values("GEOID").to_csv(OUT_CSV, index=False)
    return out.sort_values("GEOID").reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Illinois county heat + climate stress layer.")
    parser.add_argument("--no-download", action="store_true", help="Reuse existing raw files instead of downloading.")
    parser.add_argument("--start-year", type=int, default=2010, help="NOAA series start year.")
    parser.add_argument("--end-year", type=int, default=2024, help="NOAA series end year.")
    args = parser.parse_args()

    df = build_il_heat_climate_layer(
        download_raw=not args.no_download,
        start_year=args.start_year,
        end_year=args.end_year,
    )
    print(f"Wrote: {OUT_CSV} ({len(df)} counties)")
