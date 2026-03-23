from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlencode
from urllib.request import urlopen

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

COUNTY_SHP = ROOT / "data/boundaries/IL_County_Boundaries.shp"
SITES_CSV = ROOT / "data/processed/il_sites_enhanced.csv"

RAW_DIR = ROOT / "data/raw/land_use_zoning"
LANDCOVER_INDEX_HTML = RAW_DIR / "il_landcover_stats_by_county.html"
LANDCOVER_COUNTY_DIR = RAW_DIR / "landcover_counties"
CHICAGO_ZONING_GEOJSON = RAW_DIR / "chicago_zoning_districts.geojson"

OUT_CSV = ROOT / "data/processed/il_county_land_use_zoning.csv"

LANDCOVER_INDEX_URL = "https://clearinghouse.isgs.illinois.edu/webdocs/landcover/stats/landcover/mainpages/stats_by_cnty.htm"
CHICAGO_ZONING_URL = "https://data.cityofchicago.org/resource/dj47-wfun.geojson"


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


def _fetch_bytes(url: str) -> bytes:
    with urlopen(url, timeout=240) as resp:
        return resp.read()


def _download_chicago_zoning() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    query = urlencode({"$limit": 50000})
    payload = _fetch_bytes(f"{CHICAGO_ZONING_URL}?{query}")
    CHICAGO_ZONING_GEOJSON.write_bytes(payload)


def _download_landcover_county_pages() -> list[Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LANDCOVER_COUNTY_DIR.mkdir(parents=True, exist_ok=True)

    index_bytes = _fetch_bytes(LANDCOVER_INDEX_URL)
    LANDCOVER_INDEX_HTML.write_bytes(index_bytes)
    index_html = index_bytes.decode("latin-1", errors="ignore")

    rel_links = re.findall(r'href\s*=\s*"(\.\./counties/[^"]+\.htm)"', index_html, flags=re.I)
    rel_links = sorted(set(rel_links))

    out_paths: list[Path] = []
    for rel in rel_links:
        src_url = urljoin(LANDCOVER_INDEX_URL, rel)
        slug = Path(rel).name
        out = LANDCOVER_COUNTY_DIR / slug
        out.write_bytes(_fetch_bytes(src_url))
        out_paths.append(out)
    return out_paths


def _clean_html_text(cell_html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", cell_html)
    t = t.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_pct(text: str) -> float | None:
    t = str(text or "").strip()
    if not t or t == "-":
        return None
    if t.startswith("<"):
        # Source uses "<0.1" style. Use small midpoint proxy.
        return 0.05
    try:
        return float(t.replace(",", ""))
    except Exception:
        return None


def _parse_rank(text: str) -> float | None:
    t = str(text or "").strip()
    if not t or t == "-":
        return None
    m = re.match(r"(\d+)", t)
    if not m:
        return None
    return float(m.group(1))


def _norm_county_name(name: str) -> str:
    n = str(name or "").upper().replace("COUNTY", "").strip()
    n = re.sub(r"[^A-Z0-9]", "", n)
    return n


def _parse_landcover_page(path: Path) -> dict[str, Any] | None:
    html = path.read_text(encoding="latin-1", errors="ignore")
    h1 = re.search(r"<h1>\s*([^<]+?)\s*</h1>", html, flags=re.I)
    county_title = h1.group(1).strip() if h1 else path.stem
    county_name = county_title.replace(" County", "").strip()

    rows = re.findall(r"<tr>(.*?)</tr>", html, flags=re.I | re.S)
    data_rows: list[list[str]] = []
    for row_html in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
        if len(cells) < 10:
            continue
        texts = [_clean_html_text(c) for c in cells]
        data_rows.append(texts)

    # Top-level category rows are uppercase in source.
    categories: dict[str, dict[str, float | None]] = {}
    for r in data_rows:
        cat = str(r[0]).strip()
        if not cat or cat.upper() != cat or not any(ch.isalpha() for ch in cat):
            continue
        if cat.startswith("TOTALS"):
            continue
        categories[cat] = {
            "county_pct": _parse_pct(r[5]),
            "county_rank": _parse_rank(r[6]),
        }

    return {
        "County_Name": county_name + " County",
        "County_Name_Norm": _norm_county_name(county_name),
        "LandCover_Agricultural_Pct": categories.get("AGRICULTURAL LAND", {}).get("county_pct"),
        "LandCover_Agricultural_Rank": categories.get("AGRICULTURAL LAND", {}).get("county_rank"),
        "LandCover_Forested_Pct": categories.get("FORESTED LAND", {}).get("county_pct"),
        "LandCover_Forested_Rank": categories.get("FORESTED LAND", {}).get("county_rank"),
        "LandCover_UrbanBuiltUp_Pct": categories.get("URBAN AND BUILT-UP LAND", {}).get("county_pct"),
        "LandCover_UrbanBuiltUp_Rank": categories.get("URBAN AND BUILT-UP LAND", {}).get("county_rank"),
        "LandCover_Wetland_Pct": categories.get("WETLAND", {}).get("county_pct"),
        "LandCover_Wetland_Rank": categories.get("WETLAND", {}).get("county_rank"),
    }


def _build_landcover_by_county(download_raw: bool) -> pd.DataFrame:
    if download_raw:
        page_paths = _download_landcover_county_pages()
    else:
        if not LANDCOVER_COUNTY_DIR.exists():
            raise FileNotFoundError(f"Missing county page directory: {LANDCOVER_COUNTY_DIR}")
        page_paths = sorted(LANDCOVER_COUNTY_DIR.glob("*.htm"))
        if not page_paths:
            raise FileNotFoundError(f"No county pages found in: {LANDCOVER_COUNTY_DIR}")

    rows = []
    for p in page_paths:
        parsed = _parse_landcover_page(p)
        if parsed:
            rows.append(parsed)
    out = pd.DataFrame(rows)
    return out


def _classify_zone_group(zone_class: str) -> str:
    z = str(zone_class or "").upper().strip()
    if not z:
        return "unknown"
    if z.startswith(("RS", "RT", "RM", "R")):
        return "residential"
    if z.startswith(("PMD", "M")):
        return "industrial"
    if z.startswith(("B", "C", "D", "DX", "DR", "DC")):
        return "commercial"
    if z.startswith(("PD", "POS", "T", "DS")):
        return "special"
    return "other"


def _build_chicago_zoning_site_metrics(download_raw: bool) -> pd.DataFrame:
    if download_raw:
        _download_chicago_zoning()
    if not CHICAGO_ZONING_GEOJSON.exists():
        raise FileNotFoundError(f"Missing Chicago zoning file: {CHICAGO_ZONING_GEOJSON}")

    sites = pd.read_csv(SITES_CSV).copy()
    sites["GEOID"] = _coerce_fips(sites["GEOID"])
    sites["lat"] = _num(sites["lat"])
    sites["lon"] = _num(sites["lon"])
    sites = sites[sites["lat"].notna() & sites["lon"].notna()].copy()
    sites["site_rowid"] = range(len(sites))
    sites_gdf = gpd.GeoDataFrame(
        sites[["site_rowid", "site_id", "GEOID", "County_Name", "lat", "lon"]],
        geometry=gpd.points_from_xy(sites["lon"], sites["lat"]),
        crs="EPSG:4326",
    )

    zoning = gpd.read_file(CHICAGO_ZONING_GEOJSON).to_crs(epsg=4326)
    if "zone_class" not in zoning.columns:
        zoning["zone_class"] = pd.NA
    zoning["Zone_Class"] = zoning["zone_class"].astype(str)
    zoning["Zone_Group"] = zoning["Zone_Class"].map(_classify_zone_group)

    join = gpd.sjoin(
        sites_gdf[["site_rowid", "site_id", "GEOID", "geometry"]],
        zoning[["Zone_Class", "Zone_Group", "geometry"]],
        how="left",
        predicate="within",
    )
    site_zone = (
        join.sort_values(["site_rowid", "index_right"])
        .drop_duplicates(subset=["site_rowid"], keep="first")[["site_rowid", "Zone_Class", "Zone_Group"]]
    )
    sites_enriched = sites_gdf.merge(site_zone, on="site_rowid", how="left")

    # Residential adjacency within 500m (annoyance-threshold proxy).
    sites_m = sites_enriched.to_crs(epsg=26916)
    zoning_m = zoning.to_crs(epsg=26916)
    residential = zoning_m[zoning_m["Zone_Group"] == "residential"].copy()

    near_res_site_ids: set[int] = set()
    if not residential.empty and not sites_m.empty:
        buf = sites_m[["site_rowid", "geometry"]].copy()
        buf["geometry"] = buf.geometry.buffer(500)
        near = gpd.sjoin(buf, residential[["geometry"]], how="inner", predicate="intersects")
        near_res_site_ids = set(near["site_rowid"].astype(int).tolist())

    sites_enriched["Residential_Nearby_500m"] = sites_enriched["site_rowid"].isin(near_res_site_ids).astype(int)

    county_total_sites = (
        sites_enriched.groupby("GEOID", dropna=False).agg(Total_Site_Count=("site_rowid", "count")).reset_index()
    )
    county_cov = (
        sites_enriched[sites_enriched["Zone_Group"].notna()]
        .groupby("GEOID", dropna=False)
        .agg(
            Chicago_Zoning_Site_Covered_Count=("site_rowid", "count"),
            Chicago_Zoning_Residential_Site_Count=("Zone_Group", lambda s: int((s == "residential").sum())),
            Chicago_Zoning_Industrial_Site_Count=("Zone_Group", lambda s: int((s == "industrial").sum())),
            Chicago_Zoning_Commercial_Site_Count=("Zone_Group", lambda s: int((s == "commercial").sum())),
            Chicago_Zoning_Special_Site_Count=("Zone_Group", lambda s: int((s == "special").sum())),
        )
        .reset_index()
    )
    county_near = (
        sites_enriched.groupby("GEOID", dropna=False)
        .agg(Chicago_Zoning_Residential_Nearby500m_Count=("Residential_Nearby_500m", "sum"))
        .reset_index()
    )

    out = county_total_sites.merge(county_cov, on="GEOID", how="left").merge(county_near, on="GEOID", how="left")
    for col in [
        "Chicago_Zoning_Site_Covered_Count",
        "Chicago_Zoning_Residential_Site_Count",
        "Chicago_Zoning_Industrial_Site_Count",
        "Chicago_Zoning_Commercial_Site_Count",
        "Chicago_Zoning_Special_Site_Count",
        "Chicago_Zoning_Residential_Nearby500m_Count",
    ]:
        out[col] = _num(out[col]).fillna(0)

    out["Chicago_Zoning_IndustrialCommercial_Site_Count"] = (
        out["Chicago_Zoning_Industrial_Site_Count"] + out["Chicago_Zoning_Commercial_Site_Count"]
    )

    out["Chicago_Zoning_Coverage_Pct"] = (
        out["Chicago_Zoning_Site_Covered_Count"] / out["Total_Site_Count"] * 100.0
    ).where(out["Total_Site_Count"] > 0)
    out["Chicago_Zoning_Residential_Site_Share_Pct"] = (
        out["Chicago_Zoning_Residential_Site_Count"] / out["Chicago_Zoning_Site_Covered_Count"] * 100.0
    ).where(out["Chicago_Zoning_Site_Covered_Count"] > 0)
    out["Chicago_Zoning_IndustrialCommercial_Site_Share_Pct"] = (
        out["Chicago_Zoning_IndustrialCommercial_Site_Count"] / out["Chicago_Zoning_Site_Covered_Count"] * 100.0
    ).where(out["Chicago_Zoning_Site_Covered_Count"] > 0)
    out["Chicago_Zoning_Residential_Nearby500m_Share_Pct"] = (
        out["Chicago_Zoning_Residential_Nearby500m_Count"] / out["Total_Site_Count"] * 100.0
    ).where(out["Total_Site_Count"] > 0)

    return out.sort_values("GEOID").reset_index(drop=True)


def build_il_land_use_zoning_layer(download_raw: bool = True) -> pd.DataFrame:
    landcover = _build_landcover_by_county(download_raw=download_raw)
    zoning_site = _build_chicago_zoning_site_metrics(download_raw=download_raw)

    counties = gpd.read_file(COUNTY_SHP)[["GEOID", "NAME"]].copy()
    counties["GEOID"] = _coerce_fips(counties["GEOID"])
    counties["County_Name"] = counties["NAME"].astype(str).str.strip() + " County"
    counties["County_Name_Norm"] = counties["NAME"].astype(str).map(_norm_county_name)

    out = counties[["GEOID", "County_Name", "County_Name_Norm"]].merge(
        landcover.drop(columns=["County_Name"], errors="ignore"),
        on="County_Name_Norm",
        how="left",
    )
    out = out.merge(zoning_site, on="GEOID", how="left")

    for col in [
        "LandCover_Agricultural_Pct",
        "LandCover_Forested_Pct",
        "LandCover_UrbanBuiltUp_Pct",
        "LandCover_Wetland_Pct",
        "Chicago_Zoning_Coverage_Pct",
        "Chicago_Zoning_Residential_Site_Share_Pct",
        "Chicago_Zoning_IndustrialCommercial_Site_Share_Pct",
        "Chicago_Zoning_Residential_Nearby500m_Share_Pct",
    ]:
        out[col] = _num(out[col])

    # Annoyance-threshold style index:
    # higher when sites are zoned residential and/or near residential areas.
    z_res_raw = out["Chicago_Zoning_Residential_Site_Share_Pct"]
    z_near_raw = out["Chicago_Zoning_Residential_Nearby500m_Share_Pct"]
    z_res = z_res_raw.fillna(0)
    z_near = z_near_raw.fillna(0)
    urban = out["LandCover_UrbanBuiltUp_Pct"]
    urban_n = _minmax(urban).fillna(0) * 100.0

    annoyance = (
        (z_res * 0.5) + (z_near * 0.35) + (urban_n * 0.15)
    ).round(2)
    zoning_available = z_res_raw.notna() | z_near_raw.notna()
    out["Zoning_Annoyance_Threshold_Index"] = annoyance.where(zoning_available)

    # Zoning allowance proxy: more industrial/commercial zoning around sites => higher allowance.
    out["Zoning_Allowance_Index"] = _num(out["Chicago_Zoning_IndustrialCommercial_Site_Share_Pct"]).round(2)

    coverage_parts = pd.DataFrame(
        {
            "landcover_urban": out["LandCover_UrbanBuiltUp_Pct"].notna().astype(int),
            "zoning_share": out["Chicago_Zoning_Residential_Site_Share_Pct"].notna().astype(int),
            "zoning_near": out["Chicago_Zoning_Residential_Nearby500m_Share_Pct"].notna().astype(int),
        }
    )
    out["LandUse_Zoning_Data_Coverage_Pct"] = (coverage_parts.sum(axis=1) / coverage_parts.shape[1] * 100.0).round(1)

    out["LandUse_Zoning_Source"] = (
        "Illinois GIS Clearinghouse Land Cover 1999-2000 county statistics + "
        "Chicago Data Portal zoning districts (current)"
    )

    keep_cols = [
        "GEOID",
        "County_Name",
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
        "LandUse_Zoning_Source",
    ]
    out = out[[c for c in keep_cols if c in out.columns]].copy()

    for col in out.columns:
        if col in {"GEOID", "County_Name", "LandUse_Zoning_Source"}:
            continue
        out[col] = _num(out[col]).round(2)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.sort_values("GEOID").to_csv(OUT_CSV, index=False)
    return out.sort_values("GEOID").reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Illinois county land-use and zoning context layer.")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Reuse existing raw files in data/raw/land_use_zoning instead of downloading again.",
    )
    args = parser.parse_args()

    df = build_il_land_use_zoning_layer(download_raw=not args.no_download)
    print(f"Wrote: {OUT_CSV} ({len(df)} counties)")
