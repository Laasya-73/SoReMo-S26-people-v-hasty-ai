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

RAW_DIR = ROOT / "data/raw/justice"
EJSCREEN_RAW_CSV = RAW_DIR / "epa_ejscreen_il_raw.csv"
SVI_RAW_CSV = RAW_DIR / "cdc_svi2020_il_county_raw.csv"
OUT_CSV = ROOT / "data/processed/il_county_justice.csv"

EJSCREEN_SERVICE_URL = (
    "https://services2.arcgis.com/FiaPA4ga0iQKduv3/ArcGIS/rest/services/EPA_EJ_Screen/FeatureServer/0/query"
)
SVI_SERVICE_URL = (
    "https://services3.arcgis.com/ZvidGQkLaDJxRSJ2/arcgis/rest/services/"
    "CDC_ATSDR_Social_Vulnerability_Index_2020_USA/FeatureServer/1/query"
)


def _coerce_fips(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace(".0", "", regex=False)
    return s.str.zfill(5)


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _minmax(series: pd.Series) -> pd.Series:
    s = _num(series)
    if s.dropna().empty:
        return s
    mn = float(s.min())
    mx = float(s.max())
    if mx == mn:
        return s * 0
    return (s - mn) / (mx - mn)


def _fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    full_url = f"{url}?{urlencode(params, doseq=True)}"
    with urlopen(full_url, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"API error: {payload['error']}")
    return payload


def _download_ejscreen_il() -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    fields = [
        "OBJECTID",
        "ID",
        "STATE_NAME",
        "ST_ABBREV",
        "ACSTOTPOP",
        "MINORPCT",
        "LOWINCPCT",
        "PM25",
        "OZONE",
        "DSLPM",
        "P_PM25",
        "P_OZONE",
        "P_DSLPM",
        "P_CANCR",
        "P_RESP",
        "P_PTRAF",
    ]

    count_payload = _fetch_json(
        EJSCREEN_SERVICE_URL,
        {
            "where": "STATE_NAME='Illinois'",
            "returnCountOnly": "true",
            "f": "json",
        },
    )
    total_count = int(count_payload.get("count", 0))
    page_size = 2000

    rows: list[dict[str, Any]] = []
    offset = 0
    while offset < total_count:
        payload = _fetch_json(
            EJSCREEN_SERVICE_URL,
            {
                "where": "STATE_NAME='Illinois'",
                "outFields": ",".join(fields),
                "returnGeometry": "false",
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "json",
            },
        )
        feats = payload.get("features", [])
        if not feats:
            break
        rows.extend((f.get("attributes") or {}) for f in feats)
        offset += len(feats)

    df = pd.DataFrame(rows)
    df.to_csv(EJSCREEN_RAW_CSV, index=False)
    return df


def _download_svi_il_county() -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    fields = [
        "ST_ABBR",
        "COUNTY",
        "FIPS",
        "E_TOTPOP",
        "EP_POV150",
        "EP_HBURD",
        "EP_NOHSDP",
        "EP_NOVEH",
        "EP_UNEMP",
        "EP_UNINSUR",
        "EP_GROUPQ",
        "RPL_THEME1",
        "RPL_THEME2",
        "RPL_THEME3",
        "RPL_THEME4",
        "RPL_THEMES",
    ]

    payload = _fetch_json(
        SVI_SERVICE_URL,
        {
            "where": "ST_ABBR='IL'",
            "outFields": ",".join(fields),
            "returnGeometry": "false",
            "f": "json",
        },
    )
    feats = payload.get("features", [])
    rows = [(f.get("attributes") or {}) for f in feats]
    df = pd.DataFrame(rows)
    df.to_csv(SVI_RAW_CSV, index=False)
    return df


def _weighted_mean(group: pd.DataFrame, value_col: str, weight_col: str) -> float | None:
    if value_col not in group.columns or weight_col not in group.columns:
        return None
    v = _num(group[value_col])
    w = _num(group[weight_col])
    mask = v.notna() & w.notna() & (w > 0)
    if not mask.any():
        return None
    return float((v[mask] * w[mask]).sum() / w[mask].sum())


def _aggregate_ejscreen_to_county(ej: pd.DataFrame) -> pd.DataFrame:
    if ej.empty:
        return pd.DataFrame(columns=["GEOID"])

    out = ej.copy()
    out["ID_digits"] = out["ID"].astype(str).str.replace(r"\D", "", regex=True)
    out["GEOID"] = out["ID_digits"].str[:5]
    out["GEOID"] = _coerce_fips(out["GEOID"])
    out = out[out["GEOID"].str.startswith("17", na=False)].copy()

    out["ACSTOTPOP"] = _num(out.get("ACSTOTPOP")).fillna(0)
    out["weight_pop"] = out["ACSTOTPOP"].where(out["ACSTOTPOP"] > 0, 1.0)

    for col in [
        "MINORPCT",
        "LOWINCPCT",
        "PM25",
        "OZONE",
        "DSLPM",
        "P_PM25",
        "P_OZONE",
        "P_DSLPM",
        "P_CANCR",
        "P_RESP",
        "P_PTRAF",
    ]:
        out[col] = _num(out.get(col))

    rows: list[dict[str, Any]] = []
    for geoid, grp in out.groupby("GEOID", dropna=False):
        row = {
            "GEOID": geoid,
            "EJScreen_BlockGroup_Count": int(len(grp)),
            "EJScreen_Pop_Weighted_Minority_Pct": _weighted_mean(grp, "MINORPCT", "weight_pop"),
            "EJScreen_Pop_Weighted_LowIncome_Pct": _weighted_mean(grp, "LOWINCPCT", "weight_pop"),
            "EJScreen_Pop_Weighted_PM25": _weighted_mean(grp, "PM25", "weight_pop"),
            "EJScreen_Pop_Weighted_Ozone": _weighted_mean(grp, "OZONE", "weight_pop"),
            "EJScreen_Pop_Weighted_DieselPM": _weighted_mean(grp, "DSLPM", "weight_pop"),
            "EJScreen_Pop_Weighted_PM25_Pctl": _weighted_mean(grp, "P_PM25", "weight_pop"),
            "EJScreen_Pop_Weighted_Ozone_Pctl": _weighted_mean(grp, "P_OZONE", "weight_pop"),
            "EJScreen_Pop_Weighted_DieselPM_Pctl": _weighted_mean(grp, "P_DSLPM", "weight_pop"),
            "EJScreen_Pop_Weighted_CancerRisk_Pctl": _weighted_mean(grp, "P_CANCR", "weight_pop"),
            "EJScreen_Pop_Weighted_RespHazard_Pctl": _weighted_mean(grp, "P_RESP", "weight_pop"),
            "EJScreen_Pop_Weighted_TrafficProx_Pctl": _weighted_mean(grp, "P_PTRAF", "weight_pop"),
        }
        rows.append(row)

    county = pd.DataFrame(rows).sort_values("GEOID").reset_index(drop=True)

    # EJScreen demographic fields can appear as fractions [0-1] depending on service publishing.
    # Convert to percent scale [0-100] when needed so map labels and comparisons are intuitive.
    for col in ["EJScreen_Pop_Weighted_Minority_Pct", "EJScreen_Pop_Weighted_LowIncome_Pct"]:
        v = _num(county[col])
        if v.dropna().empty:
            continue
        if float(v.max()) <= 1.5:
            county[col] = (v * 100.0).round(2)
        else:
            county[col] = v.round(2)

    pollution_cols = [
        "EJScreen_Pop_Weighted_PM25_Pctl",
        "EJScreen_Pop_Weighted_Ozone_Pctl",
        "EJScreen_Pop_Weighted_DieselPM_Pctl",
        "EJScreen_Pop_Weighted_CancerRisk_Pctl",
        "EJScreen_Pop_Weighted_RespHazard_Pctl",
        "EJScreen_Pop_Weighted_TrafficProx_Pctl",
    ]
    county["EJScreen_Pollution_Burden_Index"] = _num(county[pollution_cols].mean(axis=1, skipna=True)).round(2)
    county["EJScreen_Demographic_Burden_Index"] = (
        _num(
            county[
                [
                    "EJScreen_Pop_Weighted_Minority_Pct",
                    "EJScreen_Pop_Weighted_LowIncome_Pct",
                ]
            ].mean(axis=1, skipna=True)
        ).round(2)
    )
    county["EJScreen_Justice_Index"] = (
        county["EJScreen_Pollution_Burden_Index"] * 0.6 + county["EJScreen_Demographic_Burden_Index"] * 0.4
    ).round(2)
    return county


def _clean_svi_county(svi: pd.DataFrame) -> pd.DataFrame:
    if svi.empty:
        return pd.DataFrame(columns=["GEOID"])

    out = svi.copy()
    out["GEOID"] = _coerce_fips(out["FIPS"])
    out = out[out["GEOID"].str.startswith("17", na=False)].copy()

    numeric_fields = [
        "E_TOTPOP",
        "EP_POV150",
        "EP_HBURD",
        "EP_NOHSDP",
        "EP_NOVEH",
        "EP_UNEMP",
        "EP_UNINSUR",
        "EP_GROUPQ",
        "RPL_THEME1",
        "RPL_THEME2",
        "RPL_THEME3",
        "RPL_THEME4",
        "RPL_THEMES",
    ]
    for col in numeric_fields:
        out[col] = _num(out.get(col))
        out[col] = out[col].where(out[col] >= 0)

    out["CDC_SVI_Overall_Pctl"] = (out["RPL_THEMES"] * 100.0).round(2)
    out["CDC_SVI_Theme1_SES_Pctl"] = (out["RPL_THEME1"] * 100.0).round(2)
    out["CDC_SVI_Theme2_HHDisability_Pctl"] = (out["RPL_THEME2"] * 100.0).round(2)
    out["CDC_SVI_Theme3_MinorityLanguage_Pctl"] = (out["RPL_THEME3"] * 100.0).round(2)
    out["CDC_SVI_Theme4_HousingTransport_Pctl"] = (out["RPL_THEME4"] * 100.0).round(2)

    keep = [
        "GEOID",
        "COUNTY",
        "E_TOTPOP",
        "EP_POV150",
        "EP_HBURD",
        "EP_NOHSDP",
        "EP_NOVEH",
        "EP_UNEMP",
        "EP_UNINSUR",
        "EP_GROUPQ",
        "CDC_SVI_Overall_Pctl",
        "CDC_SVI_Theme1_SES_Pctl",
        "CDC_SVI_Theme2_HHDisability_Pctl",
        "CDC_SVI_Theme3_MinorityLanguage_Pctl",
        "CDC_SVI_Theme4_HousingTransport_Pctl",
    ]
    out = out[keep].copy()
    out = out.drop_duplicates(subset=["GEOID"], keep="first")
    return out.sort_values("GEOID").reset_index(drop=True)


def build_il_justice_layer(download_raw: bool = True) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if download_raw:
        ej_raw = _download_ejscreen_il()
        svi_raw = _download_svi_il_county()
    else:
        if not EJSCREEN_RAW_CSV.exists():
            raise FileNotFoundError(f"Missing raw EJScreen file: {EJSCREEN_RAW_CSV}")
        if not SVI_RAW_CSV.exists():
            raise FileNotFoundError(f"Missing raw CDC SVI file: {SVI_RAW_CSV}")
        ej_raw = pd.read_csv(EJSCREEN_RAW_CSV)
        svi_raw = pd.read_csv(SVI_RAW_CSV)

    ej_county = _aggregate_ejscreen_to_county(ej_raw)
    svi_county = _clean_svi_county(svi_raw)

    counties = gpd.read_file(COUNTY_SHP)[["GEOID", "NAME"]].copy()
    counties["GEOID"] = _coerce_fips(counties["GEOID"])
    counties["County_Name"] = counties["NAME"].astype(str).str.strip() + " County"

    out = counties[["GEOID", "County_Name"]].merge(ej_county, on="GEOID", how="left")
    out = out.merge(svi_county.drop(columns=["COUNTY"], errors="ignore"), on="GEOID", how="left")

    # Justice Lens index (0-100): combines EPA EJ burden and CDC SVI vulnerability.
    out["Justice_EJ_Burden_Index"] = _num(out.get("EJScreen_Justice_Index"))
    out["Justice_CDC_SVI_Index"] = _num(out.get("CDC_SVI_Overall_Pctl"))

    ej_n = _minmax(out["Justice_EJ_Burden_Index"]).fillna(0)
    svi_n = _minmax(out["Justice_CDC_SVI_Index"]).fillna(0)
    out["Social_Environmental_Justice_Index"] = ((ej_n * 0.6 + svi_n * 0.4) * 100.0).round(2)

    coverage_flags = pd.DataFrame(
        {
            "ej": out["Justice_EJ_Burden_Index"].notna().astype(int),
            "svi": out["Justice_CDC_SVI_Index"].notna().astype(int),
            "pov150": _num(out.get("EP_POV150")).notna().astype(int),
            "housing_transport": _num(out.get("CDC_SVI_Theme4_HousingTransport_Pctl")).notna().astype(int),
        }
    )
    out["Justice_Data_Coverage_Pct"] = (coverage_flags.sum(axis=1) / coverage_flags.shape[1] * 100.0).round(1)

    out["Justice_Source"] = (
        "EPA EJScreen Feature Service (Esri US Federal Data catalog) + "
        "CDC/ATSDR SVI 2020 USA Feature Service (data_cdc)"
    )

    numeric_cols = [
        "EJScreen_BlockGroup_Count",
        "EJScreen_Pop_Weighted_Minority_Pct",
        "EJScreen_Pop_Weighted_LowIncome_Pct",
        "EJScreen_Pop_Weighted_PM25",
        "EJScreen_Pop_Weighted_Ozone",
        "EJScreen_Pop_Weighted_DieselPM",
        "EJScreen_Pop_Weighted_PM25_Pctl",
        "EJScreen_Pop_Weighted_Ozone_Pctl",
        "EJScreen_Pop_Weighted_DieselPM_Pctl",
        "EJScreen_Pop_Weighted_CancerRisk_Pctl",
        "EJScreen_Pop_Weighted_RespHazard_Pctl",
        "EJScreen_Pop_Weighted_TrafficProx_Pctl",
        "EJScreen_Pollution_Burden_Index",
        "EJScreen_Demographic_Burden_Index",
        "EJScreen_Justice_Index",
        "EP_POV150",
        "EP_HBURD",
        "EP_NOHSDP",
        "EP_NOVEH",
        "EP_UNEMP",
        "EP_UNINSUR",
        "EP_GROUPQ",
        "CDC_SVI_Overall_Pctl",
        "CDC_SVI_Theme1_SES_Pctl",
        "CDC_SVI_Theme2_HHDisability_Pctl",
        "CDC_SVI_Theme3_MinorityLanguage_Pctl",
        "CDC_SVI_Theme4_HousingTransport_Pctl",
        "Social_Environmental_Justice_Index",
        "Justice_Data_Coverage_Pct",
    ]
    for col in numeric_cols:
        out[col] = _num(out.get(col)).round(2)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.sort_values("GEOID").to_csv(OUT_CSV, index=False)
    return out.sort_values("GEOID").reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Illinois county Social & Environmental Justice layer.")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Reuse existing raw files in data/raw/justice instead of downloading again.",
    )
    args = parser.parse_args()

    df = build_il_justice_layer(download_raw=not args.no_download)
    print(f"Wrote: {OUT_CSV} ({len(df)} counties)")
