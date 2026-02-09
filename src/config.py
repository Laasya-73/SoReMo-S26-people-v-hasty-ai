from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
GRID_STRESS_DIR = RAW_DIR / "grid_stress"

BOUNDARIES_DIR = DATA_DIR / "boundaries"

OUTPUTS_DIR = REPO_ROOT / "outputs"
MAPS_DIR = OUTPUTS_DIR / "maps"

IL_SITES_CSV = PROCESSED_DIR / "il_sites_enhanced.csv"
IL_COUNTY_STATS_ENHANCED_CSV = PROCESSED_DIR / "il_county_stats_enhanced.csv"

IL_COUNTY_BOUNDARIES_SHP = BOUNDARIES_DIR / "IL_County_Boundaries.shp"

DEFAULT_OUTPUT_MAP = MAPS_DIR / "illinois_datacenters_map.html"

