from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

COUNTY_SHP = ROOT / "data/boundaries/IL_County_Boundaries.shp"
CURATED_SITES_CSV = ROOT / "data/processed/il_sites_enhanced.csv"

RAW_DIR = ROOT / "data/raw/datacenters"
PEERINGDB_RAW_JSON = RAW_DIR / "peeringdb_facilities_raw.json"
OSM_IL_RAW_JSON = RAW_DIR / "osm_il_datacenters_raw.json"

OUT_GLOBAL_CSV = ROOT / "data/processed/global_datacenters_registry.csv"
OUT_ILLINOIS_CSV = ROOT / "data/processed/il_datacenters_registry.csv"

PEERINGDB_FAC_URL = "https://www.peeringdb.com/api/fac"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _fetch_json(url: str, *, params: dict[str, Any] | None = None, method: str = "GET", body: bytes | None = None) -> Any:
    if params:
        qs = urlencode(params)
        url = f"{url}?{qs}"
    req = Request(
        url,
        data=body,
        method=method,
        headers={
            "User-Agent": "SoReMo-DataRegistry/1.0 (+https://github.com/Laasya-73/SoReMo-S26-people-v-hasty-ai)"
        },
    )
    with urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except Exception:
        return None
    if not pd.notna(x):
        return None
    return x


def _clean(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _norm_text(s: Any) -> str:
    t = _clean(s).lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def _provider_family(name: str, operator: str) -> str:
    txt = f"{name} {operator}".lower()
    patterns = [
        ("Amazon AWS", [r"\bamazon\b", r"\baws\b"]),
        ("Google", [r"\bgoogle\b", r"\bgcp\b"]),
        ("Microsoft Azure", [r"\bmicrosoft\b", r"\bazure\b"]),
        ("Meta", [r"\bmeta\b", r"\bfacebook\b"]),
        ("Apple", [r"\bapple\b"]),
        ("Oracle", [r"\boracle\b"]),
        ("IBM", [r"\bibm\b"]),
        ("Alibaba Cloud", [r"\balibaba\b"]),
        ("Tencent Cloud", [r"\btencent\b"]),
        ("Equinix", [r"\bequinix\b"]),
        ("Digital Realty", [r"\bdigital realty\b", r"\bdupont fabros\b"]),
        ("QTS", [r"\bqts\b"]),
    ]
    for label, pats in patterns:
        if any(re.search(p, txt) for p in pats):
            return label
    return "Other/Unknown"


def _first_source_link(sources: str) -> str:
    if not sources:
        return ""
    parts = [p.strip() for p in str(sources).split(";") if p.strip()]
    return parts[0] if parts else ""


def _fetch_peeringdb_facilities() -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    skip = 0
    limit = 1000

    while True:
        payload = _fetch_json(
            PEERINGDB_FAC_URL,
            params={"depth": 0, "limit": limit, "skip": skip},
            method="GET",
        )
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        skip += limit
        time.sleep(0.2)
    return all_rows


def _fetch_osm_illinois_datacenters() -> dict[str, Any]:
    query = """
[out:json][timeout:240];
area["ISO3166-2"="US-IL"][admin_level=4]->.a;
(
  node["man_made"="data_center"](area.a);
  way["man_made"="data_center"](area.a);
  relation["man_made"="data_center"](area.a);
  node["building"="data_center"](area.a);
  way["building"="data_center"](area.a);
  relation["building"="data_center"](area.a);
  node["landuse"="data_center"](area.a);
  way["landuse"="data_center"](area.a);
  relation["landuse"="data_center"](area.a);
);
out center tags;
""".strip()
    return _fetch_json(OVERPASS_URL, method="POST", body=query.encode("utf-8"))


def _to_peeringdb_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for r in rows:
        lat = _num(r.get("latitude"))
        lon = _num(r.get("longitude"))
        if lat is None or lon is None:
            continue
        name = _clean(r.get("name"))
        operator = _clean(r.get("org_name"))
        rec = {
            "registry_id": f"PDB-{r.get('id')}",
            "source_record_id": r.get("id"),
            "name": name,
            "operator": operator,
            "city": _clean(r.get("city")),
            "state": _clean(r.get("state")),
            "country": _clean(r.get("country")),
            "latitude": lat,
            "longitude": lon,
            "website": _clean(r.get("website")),
            "status": _clean(r.get("status")),
            "region_continent": _clean(r.get("region_continent")),
            "net_count": _num(r.get("net_count")),
            "ix_count": _num(r.get("ix_count")),
            "carrier_count": _num(r.get("carrier_count")),
            "source_system": "PeeringDB",
            "source_url": f"https://www.peeringdb.com/fac/{r.get('id')}",
            "provider_family": _provider_family(name, operator),
            "record_scope": "global",
        }
        records.append(rec)
    return pd.DataFrame(records)


def _to_osm_df(payload: dict[str, Any]) -> pd.DataFrame:
    rows = payload.get("elements", []) if isinstance(payload, dict) else []
    records: list[dict[str, Any]] = []
    for e in rows:
        tags = e.get("tags", {}) or {}
        lat = _num(e.get("lat"))
        lon = _num(e.get("lon"))
        center = e.get("center", {}) or {}
        if lat is None:
            lat = _num(center.get("lat"))
        if lon is None:
            lon = _num(center.get("lon"))
        if lat is None or lon is None:
            continue

        name = _clean(tags.get("name")) or _clean(tags.get("operator")) or f"OSM Data Center {e.get('id')}"
        operator = _clean(tags.get("operator"))
        rec = {
            "registry_id": f"OSM-{e.get('type')}-{e.get('id')}",
            "source_record_id": e.get("id"),
            "name": name,
            "operator": operator,
            "city": _clean(tags.get("addr:city")) or _clean(tags.get("city")),
            "state": _clean(tags.get("addr:state")) or "IL",
            "country": _clean(tags.get("addr:country")) or "US",
            "latitude": lat,
            "longitude": lon,
            "website": _clean(tags.get("website")),
            "status": "mapped",
            "region_continent": "North America",
            "net_count": None,
            "ix_count": None,
            "carrier_count": None,
            "source_system": "OpenStreetMap",
            "source_url": f"https://www.openstreetmap.org/{e.get('type')}/{e.get('id')}",
            "provider_family": _provider_family(name, operator),
            "record_scope": "illinois",
        }
        records.append(rec)
    return pd.DataFrame(records)


def _to_curated_il_df(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path).copy()
    df["latitude"] = pd.to_numeric(df.get("lat"), errors="coerce")
    df["longitude"] = pd.to_numeric(df.get("lon"), errors="coerce")
    df = df[df["latitude"].notna() & df["longitude"].notna()].copy()

    out = pd.DataFrame(
        {
            "registry_id": "CUR-" + df["site_id"].astype(str),
            "source_record_id": df["site_id"].astype(str),
            "name": df["name"].astype(str),
            "operator": df.get("operator", "").astype(str),
            "city": df.get("city", "").astype(str),
            "state": df.get("state", "IL").astype(str),
            "country": "US",
            "latitude": df["latitude"],
            "longitude": df["longitude"],
            "website": "",
            "status": df.get("layer", "").astype(str),
            "region_continent": "North America",
            "net_count": None,
            "ix_count": None,
            "carrier_count": None,
            "source_system": "SoReMo Curated",
            "source_url": df.get("sources", "").map(_first_source_link),
            "provider_family": [
                _provider_family(str(n), str(o))
                for n, o in zip(df.get("name", ""), df.get("operator", ""), strict=False)
            ],
            "record_scope": "illinois",
        }
    )
    return out


def _dedupe_registry(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    priority = {"SoReMo Curated": 0, "PeeringDB": 1, "OpenStreetMap": 2}
    out["source_priority"] = out["source_system"].map(priority).fillna(9).astype(int)
    out["name_norm"] = out["name"].map(_norm_text)
    out["operator_norm"] = out["operator"].map(_norm_text)
    out["city_norm"] = out["city"].map(_norm_text)
    out["lat_bin"] = pd.to_numeric(out["latitude"], errors="coerce").round(3)
    out["lon_bin"] = pd.to_numeric(out["longitude"], errors="coerce").round(3)
    out["dedupe_name_key"] = out["name_norm"].where(out["name_norm"] != "", out["operator_norm"] + out["city_norm"])

    out = out.sort_values(["source_priority", "dedupe_name_key"]).drop_duplicates(
        subset=["dedupe_name_key", "lat_bin", "lon_bin"], keep="first"
    )

    out = out.drop(
        columns=[
            "source_priority",
            "name_norm",
            "operator_norm",
            "city_norm",
            "lat_bin",
            "lon_bin",
            "dedupe_name_key",
        ],
        errors="ignore",
    )
    return out.reset_index(drop=True)


def _attach_illinois_county(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    counties = gpd.read_file(COUNTY_SHP)[["GEOID", "NAME", "geometry"]].copy()
    counties = counties.to_crs(epsg=4326)
    counties["GEOID"] = counties["GEOID"].astype(str).str.zfill(5)
    counties["County_Name"] = counties["NAME"].astype(str).str.strip() + " County"

    gdf = gpd.GeoDataFrame(
        df.copy(),
        geometry=gpd.points_from_xy(pd.to_numeric(df["longitude"], errors="coerce"), pd.to_numeric(df["latitude"], errors="coerce")),
        crs="EPSG:4326",
    )
    join = gpd.sjoin(gdf, counties[["GEOID", "County_Name", "geometry"]], how="left", predicate="within")
    out = pd.DataFrame(join.drop(columns=["geometry", "index_right"], errors="ignore"))
    out["GEOID"] = out["GEOID"].astype(str).str.zfill(5)
    return out


def build_datacenter_registry(download_raw: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if download_raw:
        peering_rows = _fetch_peeringdb_facilities()
        PEERINGDB_RAW_JSON.write_text(json.dumps({"data": peering_rows}, indent=2), encoding="utf-8")
        osm_il_payload = _fetch_osm_illinois_datacenters()
        OSM_IL_RAW_JSON.write_text(json.dumps(osm_il_payload, indent=2), encoding="utf-8")
    else:
        if not PEERINGDB_RAW_JSON.exists():
            raise FileNotFoundError(f"Missing raw PeeringDB file: {PEERINGDB_RAW_JSON}")
        if not OSM_IL_RAW_JSON.exists():
            raise FileNotFoundError(f"Missing raw OSM file: {OSM_IL_RAW_JSON}")
        peering_rows = json.loads(PEERINGDB_RAW_JSON.read_text(encoding="utf-8")).get("data", [])
        osm_il_payload = json.loads(OSM_IL_RAW_JSON.read_text(encoding="utf-8"))

    peering = _to_peeringdb_df(peering_rows)
    global_registry = peering.copy()
    global_registry["is_us"] = (global_registry["country"].str.upper() == "US").astype(int)
    global_registry["is_illinois"] = (
        (global_registry["country"].str.upper() == "US")
        & (global_registry["state"].str.upper().isin(["IL", "ILLINOIS"]))
    ).astype(int)

    peering_il = global_registry[global_registry["is_illinois"] == 1].copy()
    osm_il = _to_osm_df(osm_il_payload)
    curated_il = _to_curated_il_df(CURATED_SITES_CSV)

    il_registry = pd.concat([curated_il, peering_il, osm_il], ignore_index=True)
    il_registry = _dedupe_registry(il_registry)
    il_registry = _attach_illinois_county(il_registry)

    keep_global = [
        "registry_id",
        "source_record_id",
        "name",
        "operator",
        "provider_family",
        "city",
        "state",
        "country",
        "region_continent",
        "latitude",
        "longitude",
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
    ]
    global_registry = global_registry[[c for c in keep_global if c in global_registry.columns]].copy()

    keep_il = [
        "registry_id",
        "source_record_id",
        "name",
        "operator",
        "provider_family",
        "city",
        "state",
        "country",
        "latitude",
        "longitude",
        "status",
        "website",
        "source_system",
        "source_url",
        "record_scope",
        "GEOID",
        "County_Name",
    ]
    il_registry = il_registry[[c for c in keep_il if c in il_registry.columns]].copy()

    OUT_GLOBAL_CSV.parent.mkdir(parents=True, exist_ok=True)
    global_registry.to_csv(OUT_GLOBAL_CSV, index=False)
    il_registry.to_csv(OUT_ILLINOIS_CSV, index=False)
    return global_registry, il_registry


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Illinois + global data-center registry datasets.")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Reuse saved raw responses in data/raw/datacenters instead of downloading.",
    )
    args = parser.parse_args()

    global_df, il_df = build_datacenter_registry(download_raw=not args.no_download)
    print(f"Wrote: {OUT_GLOBAL_CSV} ({len(global_df)} rows)")
    print(f"Wrote: {OUT_ILLINOIS_CSV} ({len(il_df)} rows)")
