from src.config import IL_SITES_CSV, DEFAULT_OUTPUT_MAP
from src.utils.io import read_csv, ensure_parent_dir
from src.mapping.build_map import build_illinois_map

def main():
    sites = read_csv(IL_SITES_CSV)
    m = build_illinois_map(sites)
    ensure_parent_dir(DEFAULT_OUTPUT_MAP)
    m.save(str(DEFAULT_OUTPUT_MAP))
    print(f"Saved map to: {DEFAULT_OUTPUT_MAP}")

if __name__ == "__main__":
    main()
