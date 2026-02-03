import pandas as pd
from pathlib import Path
import geopandas as gpd
import os


def read_csv(path: Path) -> pd.DataFrame:
    # Standard csv reader
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path)


def read_geographic_data(file_path):

    # Reads a Shapefile (.shp) or GeoJSON and converts
    # it to WGS84 for Leaflet compatibility.

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Geographic file not found at: {file_path}")

    gdf = gpd.read_file(file_path)

    # Ensure the data is in the correct projection for Folium (Leaflet)
    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs(epsg=4326)

    return gdf

def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
