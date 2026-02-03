from src.config import IL_SITES_CSV, DEFAULT_OUTPUT_MAP, IL_COUNTY_BOUNDARIES_SHP, IL_COUNTY_STATS_ENHANCED_CSV
from src.utils.io import read_csv, ensure_parent_dir, read_geographic_data

from src.mapping.build_map import build_illinois_map
import pandas as pd

def main():
    # 1. Load the data
    sites = read_csv(IL_SITES_CSV)

    # 2. Load the county boundary shapes
    # Point this to the .shp file
    counties_gdf = read_geographic_data(IL_COUNTY_BOUNDARIES_SHP)

    # 3. Load economic/demographic data
    economic_data = pd.read_csv(IL_COUNTY_STATS_ENHANCED_CSV)

    # Force GEOID to be strings to ensure a perfect match
    counties_gdf['GEOID'] = counties_gdf['GEOID'].astype(str)
    economic_data['GEOID'] = economic_data['GEOID'].astype(str)

    # 4. Merge the shapes with the economic data
    # Join on 'GEOID' to ensure every county shape knows its poverty/income rate
    counties_enriched = counties_gdf.merge(economic_data, on='GEOID')

    # 5. Build the map
    m = build_illinois_map(sites, counties_layer=counties_enriched)

    ensure_parent_dir(DEFAULT_OUTPUT_MAP)
    m.save(str(DEFAULT_OUTPUT_MAP))
    print(f"Saved map to: {DEFAULT_OUTPUT_MAP}")

if __name__ == "__main__":
    main()