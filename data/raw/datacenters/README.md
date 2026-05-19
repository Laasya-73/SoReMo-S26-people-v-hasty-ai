# Data Center Registry Sources

This folder stores raw responses used by `src/build_datacenter_registry.py`.

## Sources used

1. PeeringDB facilities API (global baseline)
- Endpoint: `https://www.peeringdb.com/api/fac`
- Site: https://www.peeringdb.com/
- Used for: global and US/Illinois facility records with coordinates, operator, and site metadata.

2. OpenStreetMap + Overpass API (Illinois augmentation)
- API: `https://overpass-api.de/api/interpreter`
- Query basis: `man_made=data_center`, `building=data_center`, `landuse=data_center` within Illinois boundary.
- Used for: additional Illinois points that may not appear in other registries.

3. SoReMo curated Illinois site dataset
- File: `data/processed/il_sites_enhanced.csv`
- Used for: project-specific existing/proposed/denied/inventory context.

## Notes on the user-provided links

- `datacentermap.com` and `cloudinfrastructuremap.com` are useful discovery sites.
- For reproducible automated ingestion, this pipeline uses open/API-accessible sources above.
- If you want to add licensed commercial datasets later, map their exports to the schema in `data/processed/il_datacenters_registry.csv` and `data/processed/global_datacenters_registry.csv`.
