# Land Use / Zoning Sources

This folder stores raw data used by `src/build_land_use_zoning_layer.py`.

## Source A: Illinois GIS Clearinghouse (statewide land cover)

- Portal: https://clearinghouse.isgs.illinois.edu/
- County land-cover stats index used by builder:
  - `https://clearinghouse.isgs.illinois.edu/webdocs/landcover/stats/landcover/mainpages/stats_by_cnty.htm`
- Builder downloads each county page from that index into:
  - `data/raw/land_use_zoning/landcover_counties/*.htm`

Used fields:

- Agricultural land %
- Forested land %
- Urban and built-up land %
- Wetland %

## Source B: Chicago Data Portal (zoning districts)

- Portal: https://data.cityofchicago.org/
- API endpoint used by builder:
  - `https://data.cityofchicago.org/resource/dj47-wfun.geojson?$limit=50000`
- Saved file:
  - `data/raw/land_use_zoning/chicago_zoning_districts.geojson`

Used fields:

- `zone_class` (mapped into residential / industrial / commercial / special)
- geometry (for site-in-zone and near-residential calculations)

## Notes on coverage

- Land cover is statewide (all Illinois counties).
- Zoning geometry source is Chicago-specific, so zoning-derived indicators are available only where site records intersect that zoning coverage.
- `LandUse_Zoning_Data_Coverage_Pct` indicates where zoning signals are partial vs available.
