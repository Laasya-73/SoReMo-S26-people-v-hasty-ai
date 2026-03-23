<script>
  import { onMount, onDestroy } from "svelte";
  import maplibregl from "maplibre-gl";
  import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
  import { MapboxOverlay } from "@deck.gl/mapbox";
  import "maplibre-gl/dist/maplibre-gl.css";

  const WORKSPACE = { HOME: "home", MAP: "map", BRIEF: "brief", STUDIO: "studio", REGISTRY: "registry" };
  const WORKSPACE_PATHS = {
    [WORKSPACE.HOME]: "/",
    [WORKSPACE.MAP]: "/map",
    [WORKSPACE.BRIEF]: "/briefing",
    [WORKSPACE.STUDIO]: "/studio",
    [WORKSPACE.REGISTRY]: "/registry"
  };
  const WORKSPACE_TAB_META = {
    [WORKSPACE.HOME]: {
      title: "SoReMo | Illinois Data Center Impact Map",
      icon: "/icons/tab-home.svg"
    },
    [WORKSPACE.MAP]: {
      title: "Illinois Map | SoReMo '26",
      icon: "/icons/tab-map.svg"
    },
    [WORKSPACE.BRIEF]: {
      title: "County Intelligence Briefing | SoReMo '26",
      icon: "/icons/tab-briefing.svg"
    },
    [WORKSPACE.STUDIO]: {
      title: "Impact Scenario Studio | SoReMo '26",
      icon: "/icons/tab-studio.svg"
    },
    [WORKSPACE.REGISTRY]: {
      title: "Data Center Registry | SoReMo '26",
      icon: "/icons/tab-registry.svg"
    }
  };
  const TAB_ICON_VERSION = "20260323b";
  const SCENARIOS = [
    { key: "planned", label: "Planned buildout (existing + proposed + inventory + denied)" },
    { key: "current", label: "Current footprint (existing only)" }
  ];
  const FOCUS = ["Balanced overview", "Environmental stress", "Economic vulnerability", "Public hearing prep"];
  const LAYERED_NARRATIVE_STEPS = [
    {
      key: "where_infrastructure",
      label: "Where data centers are now/planned",
      summary: "Shows existing, proposed, denied, and inventory footprint with pressure scoring.",
      scenario: "planned",
      countyLayer: "pressure",
      visibility: { existing: true, proposed: true, denied: true, inventory: true, registry: false, outlines: true }
    },
    {
      key: "environmental_stress",
      label: "Existing environmental stress",
      summary: "Shows baseline county stress context before additional AI infrastructure burden.",
      scenario: "planned",
      countyLayer: "cumulative",
      visibility: { existing: true, proposed: true, denied: false, inventory: false, registry: false, outlines: true }
    },
    {
      key: "community_exposure",
      label: "Who lives there",
      summary: "Shows social and environmental justice context of potentially affected communities.",
      scenario: "planned",
      countyLayer: "justice_index",
      visibility: { existing: true, proposed: true, denied: false, inventory: false, registry: false, outlines: true }
    },
    {
      key: "ai_added_burden",
      label: "Additional AI burden (annoyance score)",
      summary: "Shows multi-factor annoyance burden and counties exceeding threshold X.",
      scenario: "planned",
      countyLayer: "annoyance_threshold",
      visibility: { existing: true, proposed: true, denied: true, inventory: true, registry: false, outlines: true }
    }
  ];
  const ANNOYANCE_COMPONENTS = [
    { key: "aqi", label: "AQI level", prop: "AQI_P90", unit: "aqi", weight: 0.25 },
    { key: "water", label: "Water stress", prop: "Water_Stress_Index", unit: "score", weight: 0.25 },
    { key: "energy", label: "Energy burden", prop: "Energy_Burden_PctIncome_disp", unit: "pct", weight: 0.25 },
    { key: "social", label: "Social vulnerability", prop: "Social_Environmental_Justice_Index", unit: "score", weight: 0.25 }
  ];
  const DEFAULT_ANNOYANCE_THRESHOLD = 70;
  const VIEWS = {
    Illinois: [-89.2, 40.05, 6.25],
    Chicago: [-87.75, 41.87, 9.6],
    ElkGrove: [-87.97, 42.0, 11.2],
    DeKalb: [-88.75, 41.93, 10.8],
    Naperville: [-88.17, 41.81, 12.5]
  };
  const BASEMAP_STYLES = {
    light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    color: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
    dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
  };
  const BASEMAP_LABELS = {
    light: "Light",
    color: "Color",
    dark: "Dark"
  };
  const SITE_COLORS = {
    existing: [24, 166, 119, 230],
    proposed: [49, 109, 214, 230],
    denied: [214, 62, 88, 235],
    inventory: [147, 88, 220, 220],
    registry: [242, 155, 29, 230]
  };
  const PRESSURE_STATUS_META = {
    existing: {
      label: "Existing sites",
      help: "Operating sites that already add ongoing utility and community load."
    },
    proposed: {
      label: "Proposed sites",
      help: "Pipeline projects likely to add future pressure if approved and built."
    },
    inventory: {
      label: "Inventory sites",
      help: "Sites in inventory/watchlist with moderate likelihood of activation."
    },
    denied: {
      label: "Denied sites",
      help: "Denied projects included as lower but non-zero planning signal."
    }
  };
  const PRESSURE_WEIGHT_RATIONALE = {
    existing: "1.0 is the baseline multiplier for currently operating sites (confirmed active footprint).",
    proposed: "1.5 is higher to reflect likely near-term growth pressure if projects move forward.",
    inventory: "0.75 is lower because inventory/watchlist projects are less certain than proposed.",
    denied: "0.5 keeps denied projects as low residual planning signal, not active build pressure."
  };
  const DEFAULT_PRESSURE_WEIGHTS = { existing: 1, proposed: 1.5, inventory: 0.75, denied: 0.5 };
  const PRESSURE_WEIGHT_LIMITS = { min: 0, max: 3, step: 0.05 };
  const PRESSURE_WEIGHT_PROFILES = {
    baseline: {
      label: "Recommended baseline",
      weights: null
    },
    cautious: {
      label: "Cautious permitting",
      weights: { existing: 1.1, proposed: 1.1, inventory: 0.5, denied: 0.2 }
    },
    growthHeavy: {
      label: "Fast-growth assumption",
      weights: { existing: 1, proposed: 1.9, inventory: 1, denied: 0.6 }
    }
  };
  const COUNTY_LAYERS = {
    none: { label: "No county fill", prop: null, unit: "", help: "Turns off county shading so you can focus on site points and boundaries only." },
    impact: { label: "Community Impact Score", prop: "Impact_Score", unit: "score", help: "Composite social-context signal (poverty + minority share) for community sensitivity.", colors: [[255, 242, 246], [253, 205, 221], [249, 134, 180], [197, 27, 125], [122, 1, 119]] },
    pressure: { label: "Data Center Pressure Score", propCurrent: "Pressure_Score_Current", propPlanned: "Pressure_Score_Planned", unit: "score", help: "Weighted pressure from existing, proposed, inventory, and denied sites for the selected scenario.", colors: [[239, 243, 255], [189, 215, 231], [107, 174, 214], [49, 130, 189], [8, 81, 156]] },
    annoyance_threshold: { label: "Annoyance Threshold Score (0-100)", prop: null, unit: "score", help: "Composite annoyance score from AQI, water stress, energy burden, and social vulnerability. Higher means more likely to exceed local tolerance threshold.", colors: [[255, 247, 251], [236, 226, 240], [208, 209, 230], [166, 189, 219], [54, 144, 192]] },
    economic: { label: "Economic Vulnerability 2.0", prop: "Economic_Vulnerability_Score", unit: "score", help: "County-level affordability and socioeconomic sensitivity indicator.", colors: [[247, 252, 245], [199, 233, 192], [116, 196, 118], [35, 139, 69], [0, 68, 27]] },
    cumulative: { label: "Cumulative Burden (Air + Energy)", prop: "Cumulative_Burden_Score", unit: "score", help: "Combined exposure signal from air-quality and energy-burden indicators.", colors: [[255, 247, 236], [254, 217, 142], [254, 153, 41], [217, 95, 14], [127, 39, 4]] },
    justice_index: { label: "Social & Environmental Justice Index", prop: "Social_Environmental_Justice_Index", unit: "score", help: "High-level justice lens combining EPA EJ burden context and CDC SVI vulnerability percentile.", colors: [[247, 252, 245], [199, 233, 192], [116, 196, 118], [35, 139, 69], [0, 68, 27]] },
    justice_ejscreen: { label: "EPA EJScreen Justice Index", prop: "EJScreen_Justice_Index", unit: "score", help: "EPA EJScreen-based justice indicator aggregated to county scale (higher means more burdened context).", colors: [[255, 245, 240], [254, 187, 161], [252, 106, 74], [222, 45, 38], [165, 15, 21]] },
    justice_pollution: { label: "EPA EJScreen Pollution Burden", prop: "EJScreen_Pollution_Burden_Index", unit: "score", help: "Pollution burden signal from EPA EJScreen PM2.5, ozone, diesel PM, cancer and respiratory-risk percentiles.", colors: [[255, 247, 236], [254, 217, 142], [254, 153, 41], [217, 95, 14], [127, 39, 4]] },
    justice_lowincome: { label: "EPA EJScreen Low-Income Population (%)", prop: "EJScreen_Pop_Weighted_LowIncome_Pct", unit: "pct", help: "Population-weighted low-income share from EPA EJScreen source geographies, summarized by county.", colors: [[252, 251, 253], [218, 218, 235], [158, 154, 200], [117, 107, 177], [84, 39, 143]] },
    justice_minority: { label: "EPA EJScreen Minority Population (%)", prop: "EJScreen_Pop_Weighted_Minority_Pct", unit: "pct", help: "Population-weighted minority share from EPA EJScreen source geographies, summarized by county.", colors: [[255, 255, 217], [237, 248, 177], [127, 205, 187], [29, 145, 192], [34, 94, 168]] },
    justice_svi_overall: { label: "CDC SVI Overall Percentile", prop: "CDC_SVI_Overall_Pctl", unit: "pct", help: "CDC/ATSDR Social Vulnerability Index overall percentile by county (higher = more vulnerable).", colors: [[247, 251, 255], [198, 219, 239], [107, 174, 214], [33, 113, 181], [8, 48, 107]] },
    justice_svi_housing_transport: { label: "CDC SVI Housing & Transport Percentile", prop: "CDC_SVI_Theme4_HousingTransport_Pctl", unit: "pct", help: "CDC SVI Theme 4 percentile capturing housing and transportation vulnerability.", colors: [[247, 252, 253], [204, 236, 230], [153, 216, 201], [65, 174, 118], [35, 139, 69]] },
    poverty: { label: "County Poverty Rate (%)", prop: "Poverty_Rate_Percent", unit: "pct", help: "Share of residents below poverty level in each county.", colors: [[252, 251, 253], [218, 218, 235], [158, 154, 200], [117, 107, 177], [84, 39, 143]] },
    minority: { label: "County Minority Population (%)", prop: "Pct_Minority", unit: "pct", help: "Percent of residents identified as minority population.", colors: [[255, 255, 217], [237, 248, 177], [127, 205, 187], [29, 145, 192], [34, 94, 168]] },
    aqi: { label: "Air Quality (AQI P90)", prop: "AQI_P90", unit: "aqi", help: "90th-percentile AQI, showing upper-end air quality stress by county.", colors: [[237, 248, 251], [178, 226, 226], [102, 194, 164], [44, 162, 95], [0, 109, 44]] },
    ozone: { label: "Ozone Days", prop: "Ozone_Days", unit: "days", help: "Annual number of ozone-affected AQI days.", colors: [[247, 252, 253], [204, 236, 230], [153, 216, 201], [65, 174, 118], [35, 139, 69]] },
    pm25: { label: "PM2.5 Days", prop: "PM25_Days", unit: "days", help: "Annual number of PM2.5-affected AQI days.", colors: [[255, 245, 240], [254, 187, 161], [252, 106, 74], [222, 45, 38], [165, 15, 21]] },
    energy_burden: { label: "Energy Burden (% income)", prop: "Energy_Burden_PctIncome_disp", unit: "pct", help: "Average household income share spent on energy costs.", colors: [[250, 245, 255], [218, 218, 235], [188, 189, 220], [128, 125, 186], [78, 55, 130]] },
    avg_energy_cost: { label: "Avg Annual Household Energy Cost ($)", prop: "Avg_Annual_Energy_Cost_USD", unit: "usd", help: "Estimated annual household energy spending by county.", colors: [[255, 245, 235], [254, 230, 206], [253, 174, 107], [230, 85, 13], [127, 39, 4]] },
    electricity_use: { label: "Electricity Use (MWh per capita)", prop: "Elec_Consumption_MWh_perCapita_disp", unit: "mwh", help: "Per-capita electricity consumption intensity from county energy profiles.", colors: [[247, 251, 255], [198, 219, 239], [107, 174, 214], [33, 113, 181], [8, 48, 107]] },
    water_index: { label: "Water Stress Index (Aqueduct, 0-100)", prop: "Water_Stress_Index", unit: "score", help: "Composite county water-risk index for data-center cooling context (higher = more stressed).", colors: [[247, 252, 255], [198, 219, 239], [107, 174, 214], [49, 130, 189], [8, 81, 156]] },
    water_stress: { label: "Baseline Water Stress (Aqueduct, 0-5)", prop: "Aqueduct_BWS_Score", unit: "score", help: "Baseline ratio of water demand to available supply (higher = tighter water balance).", colors: [[255, 245, 235], [253, 208, 162], [252, 141, 89], [227, 74, 51], [179, 0, 0]] },
    water_drought: { label: "Drought Risk (Aqueduct, 0-5)", prop: "Aqueduct_Drought_Score", unit: "score", help: "Long-term drought risk signal from Aqueduct baseline indicators.", colors: [[255, 255, 229], [255, 247, 188], [254, 227, 145], [254, 196, 79], [217, 95, 14]] },
    water_groundwater: { label: "Groundwater Table Decline (Aqueduct, 0-5)", prop: "Aqueduct_GWDecline_Score", unit: "score", help: "Groundwater table decline risk where data is available.", colors: [[252, 251, 253], [218, 218, 235], [188, 189, 220], [128, 125, 186], [84, 39, 143]] },
    water_power_risk: { label: "Water Risk for Electric Power (Aqueduct, 0-5)", prop: "Aqueduct_OverallPowerRisk_Score", unit: "score", help: "Aqueduct industry-weighted water risk tailored to electric-power operations.", colors: [[237, 248, 251], [178, 226, 226], [102, 194, 164], [44, 162, 95], [0, 109, 44]] },
    grid_clean_share: { label: "Grid Clean Share (%)", prop: "Grid_Clean_Share_Pct", unit: "pct", help: "Estimated low-carbon generation share (nuclear + hydro + biomass + wind + solar) in the county's eGRID subregion mix.", colors: [[247, 252, 245], [199, 233, 192], [116, 196, 118], [35, 139, 69], [0, 90, 50]] },
    grid_fossil_share: { label: "Grid Fossil Share (%)", prop: "Grid_Fossil_Share_Pct", unit: "pct", help: "Estimated fossil generation share (coal + oil + gas + other fossil) in the county's eGRID subregion mix.", colors: [[255, 247, 236], [254, 217, 142], [254, 153, 41], [217, 95, 14], [127, 39, 4]] },
    grid_carbon_intensity: { label: "Grid Carbon Intensity (kg CO2/MWh)", prop: "Grid_Carbon_Intensity_kg_per_MWh", unit: "kgco2", help: "Average emissions intensity of grid electricity serving the county's eGRID subregion (higher means dirtier electricity).", colors: [[255, 245, 240], [254, 187, 161], [252, 106, 74], [222, 45, 38], [103, 0, 13]] },
    grid_co2_100mw: { label: "Estimated CO2 for 100 MW Load (kt/yr)", prop: "Grid_Est_CO2_kt_per_100MWyr", unit: "ktco2", help: "Estimated annual CO2 for a continuous 100 MW load in this grid region; useful for scenario-scale carbon communication.", colors: [[255, 245, 240], [254, 187, 161], [252, 106, 74], [222, 45, 38], [103, 0, 13]] },
    dc_carbon_exposure: { label: "Data Center Carbon Exposure Index", prop: "DC_Carbon_Exposure_Index", unit: "score", help: "Pressure-weighted carbon exposure proxy: planned pressure score x grid carbon intensity.", colors: [[252, 251, 253], [218, 218, 235], [158, 154, 200], [117, 107, 177], [84, 39, 143]] },
    heat_climate_index: { label: "Heat + Climate Stress Index (0-100)", prop: "Heat_Climate_Stress_Index", unit: "score", help: "Combined heat-stress signal from NOAA thermal load metrics and FEMA heat-wave risk indicators.", colors: [[255, 245, 235], [253, 208, 162], [252, 141, 89], [227, 74, 51], [179, 0, 0]] },
    heat_cdd_recent: { label: "NOAA Cooling Degree Days (5-yr avg)", prop: "NOAA_CDD_Recent5yr", unit: "cdd", help: "Average annual cooling degree days (last 5 years), a proxy for cooling demand pressure.", colors: [[255, 255, 229], [255, 247, 188], [254, 227, 145], [254, 196, 79], [217, 95, 14]] },
    heat_tmax_summer: { label: "NOAA Summer Max Temp (5-yr avg, F)", prop: "NOAA_Tmax_Summer_Recent5yr_F", unit: "degf", help: "Average June-August maximum temperature over the last 5 years.", colors: [[255, 245, 240], [254, 224, 210], [252, 146, 114], [251, 106, 74], [203, 24, 29]] },
    heat_fema_risk: { label: "FEMA Heat Wave Risk Score", prop: "HWAV_RISKS", unit: "score", help: "FEMA National Risk Index heat-wave risk score (hazard x exposure x vulnerability).", colors: [[247, 251, 255], [198, 219, 239], [107, 174, 214], [33, 113, 181], [8, 48, 107]] },
    heat_fema_loss_pctile: { label: "FEMA Heat Loss-Rate Percentile", prop: "HWAV_ALR_NPCTL", unit: "pct", help: "National percentile for FEMA heat-wave expected annual loss rate (higher = relatively higher risk).", colors: [[247, 252, 245], [199, 233, 192], [116, 196, 118], [35, 139, 69], [0, 68, 27]] },
    heat_feedback: { label: "Data Center Heat Feedback Index", prop: "DC_Heat_Feedback_Index", unit: "score", help: "Planned pressure multiplied by county heat-climate stress; highlights heat-growth feedback hotspots.", colors: [[252, 251, 253], [218, 218, 235], [188, 189, 220], [128, 125, 186], [84, 39, 143]] },
    noise_community_index: { label: "Noise + Community Impact Index (0-100)", prop: "Noise_Community_Impact_Index", unit: "score", help: "Composite signal combining FAA airport noise exposure, Chicago noise complaints, EPA TRI industrial presence, and community vulnerability.", colors: [[247, 252, 253], [204, 236, 230], [153, 216, 201], [44, 162, 95], [0, 90, 50]] },
    noise_faa_exposure: { label: "FAA Airport Noise Exposure Index (0-100)", prop: "FAA_Noise_Exposure_Index", unit: "score", help: "FAA airport-based noise proxy from airport density, annual operations, and enplanements.", colors: [[255, 255, 217], [237, 248, 177], [127, 205, 187], [29, 145, 192], [12, 44, 132]] },
    noise_airport_density: { label: "Airport Density (count per 1000 km2)", prop: "FAA_Airport_Density_per_1000km2", unit: "density", help: "How many FAA airport facilities are located per 1,000 km2 in each county.", colors: [[255, 247, 251], [236, 226, 240], [208, 209, 230], [166, 189, 219], [43, 140, 190]] },
    noise_ops_total: { label: "Airport Operations Proxy (annual)", prop: "FAA_Airport_Operations_Total", unit: "count", help: "Sum of FAA-reported operations proxies (commercial, air taxi, local, itinerant, military) by county.", colors: [[255, 247, 236], [254, 217, 142], [254, 178, 76], [240, 59, 32], [153, 0, 0]] },
    noise_chicago_311: { label: "Chicago 311 Noise Complaints (avg/year, recent 3 years)", prop: "Chicago_311_Noise_AnnualAvg_Recent3yr", unit: "count", help: "Recent annual average of Chicago 311 noise complaints (city-source indicator, mapped to Cook County).", colors: [[255, 245, 240], [254, 224, 210], [252, 146, 114], [251, 106, 74], [203, 24, 29]] },
    noise_tri_facility_count: { label: "EPA TRI Active Industrial Facilities", prop: "EPA_TRI_Active_Facility_Count", unit: "count", help: "Active EPA TRI-reporting industrial facilities by county (statewide industrial footprint proxy).", colors: [[252, 251, 253], [218, 218, 235], [188, 189, 220], [128, 125, 186], [84, 39, 143]] },
    noise_tri_pressure: { label: "EPA TRI Industrial Pressure Index (0-100)", prop: "EPA_TRI_Industrial_Pressure_Index", unit: "score", help: "Normalized county industrial-pressure signal from active TRI facility count, density, and per-capita presence.", colors: [[255, 247, 236], [254, 217, 142], [254, 178, 76], [240, 59, 32], [153, 0, 0]] },
    noise_overlap: { label: "Data Center Noise-Community Overlap", prop: "DC_Noise_Community_Overlap_Index", unit: "score", help: "Pressure-weighted overlap: planned data center pressure x Noise + Community Impact Index.", colors: [[250, 245, 255], [218, 218, 235], [188, 189, 220], [128, 125, 186], [63, 0, 125]] },
    landcover_urban_builtup: { label: "Land Cover: Urban/Built-Up (%)", prop: "LandCover_UrbanBuiltUp_Pct", unit: "pct", help: "Share of county land classified as urban or built-up area (Illinois GIS Clearinghouse).", colors: [[255, 245, 240], [254, 224, 210], [252, 146, 114], [251, 106, 74], [203, 24, 29]] },
    landcover_agriculture: { label: "Land Cover: Agricultural (%)", prop: "LandCover_Agricultural_Pct", unit: "pct", help: "Share of county land classified as agricultural use.", colors: [[255, 255, 229], [247, 252, 185], [173, 221, 142], [49, 163, 84], [0, 104, 55]] },
    landcover_forested: { label: "Land Cover: Forested (%)", prop: "LandCover_Forested_Pct", unit: "pct", help: "Share of county land classified as forest cover.", colors: [[247, 252, 245], [199, 233, 192], [116, 196, 118], [35, 139, 69], [0, 68, 27]] },
    landcover_wetland: { label: "Land Cover: Wetland (%)", prop: "LandCover_Wetland_Pct", unit: "pct", help: "Share of county land classified as wetland.", colors: [[247, 252, 253], [204, 236, 230], [153, 216, 201], [65, 174, 118], [35, 139, 69]] },
    zoning_allowance: { label: "Zoning Allowance Index (%)", prop: "Zoning_Allowance_Index", unit: "pct", help: "Estimated share of site-overlapping Chicago zoning polygons classified industrial/commercial (higher = more permissive signal).", colors: [[247, 251, 255], [198, 219, 239], [107, 174, 214], [33, 113, 181], [8, 48, 107]] },
    zoning_annoyance_threshold: { label: "Zoning Annoyance Threshold Index (0-100)", prop: "Zoning_Annoyance_Threshold_Index", unit: "score", help: "Higher where sites overlap/approach residential zoning and urban built-up context, indicating higher community-friction potential.", colors: [[255, 247, 236], [254, 217, 142], [254, 153, 41], [217, 95, 14], [127, 39, 4]] },
    zoning_residential_nearby: { label: "Sites Near Residential Zoning (500m, %)", prop: "Chicago_Zoning_Residential_Nearby500m_Share_Pct", unit: "pct", help: "Percent of county site records within 500m of residential zoning polygons in available Chicago zoning coverage.", colors: [[255, 245, 240], [254, 224, 210], [252, 146, 114], [251, 106, 74], [203, 24, 29]] },
    landuse_zoning_coverage: { label: "Land Use/Zoning Data Coverage (%)", prop: "LandUse_Zoning_Data_Coverage_Pct", unit: "pct", help: "Coverage completeness for this module: land-cover + zoning-derived signals available for the county.", colors: [[247, 252, 253], [204, 236, 230], [153, 216, 201], [78, 179, 211], [43, 140, 190]] }
  };
  const COUNTY_LAYER_GROUP_ORDER = ["core", "justice", "water", "grid", "heat", "noise", "landuse", "context", "other"];
  const COUNTY_LAYER_GROUP_LABEL = {
    core: "Core",
    justice: "Justice",
    water: "Water",
    grid: "Grid & Emissions",
    heat: "Heat & Climate",
    noise: "Noise & Community",
    landuse: "Land Use & Zoning",
    context: "Context Metrics",
    other: "Additional"
  };
  const COUNTY_INDICATOR_DEFS = [
    { key: "pressure", label: "Pressure", unit: "score", propCurrent: "Pressure_Score_Current", propPlanned: "Pressure_Score_Planned", zeroAsMissing: false, priorityBoost: 8 },
    { key: "annoyance_score", label: "Annoyance Score", unit: "score", prop: null, zeroAsMissing: false, priorityBoost: 7 },
    { key: "impact", label: "Community Impact", unit: "score", prop: "Impact_Score", zeroAsMissing: true, priorityBoost: 6 },
    { key: "justice_index", label: "Justice Index", unit: "score", prop: "Social_Environmental_Justice_Index", zeroAsMissing: true, priorityBoost: 6 },
    { key: "svi", label: "CDC SVI Overall", unit: "pct", prop: "CDC_SVI_Overall_Pctl", zeroAsMissing: true, priorityBoost: 5 },
    { key: "ej_pollution", label: "EJ Pollution Burden", unit: "score", prop: "EJScreen_Pollution_Burden_Index", zeroAsMissing: true, priorityBoost: 5 },
    { key: "cumulative", label: "Cumulative Burden", unit: "score", prop: "Cumulative_Burden_Score", zeroAsMissing: true, priorityBoost: 5 },
    { key: "water_index", label: "Water Stress Index", unit: "score", prop: "Water_Stress_Index", zeroAsMissing: true, priorityBoost: 5 },
    { key: "water_stress", label: "Water Stress (Aqueduct)", unit: "score", prop: "Aqueduct_BWS_Score", zeroAsMissing: true, priorityBoost: 4 },
    { key: "water_drought", label: "Drought Risk (Aqueduct)", unit: "score", prop: "Aqueduct_Drought_Score", zeroAsMissing: true, priorityBoost: 3 },
    { key: "water_groundwater", label: "Groundwater Decline (Aqueduct)", unit: "score", prop: "Aqueduct_GWDecline_Score", zeroAsMissing: true, priorityBoost: 3 },
    { key: "aqi", label: "AQI P90", unit: "aqi", prop: "AQI_P90", zeroAsMissing: true, priorityBoost: 4 },
    { key: "ozone", label: "Ozone Days", unit: "days", prop: "Ozone_Days", zeroAsMissing: true, priorityBoost: 3 },
    { key: "pm25", label: "PM2.5 Days", unit: "days", prop: "PM25_Days", zeroAsMissing: true, priorityBoost: 3 },
    { key: "poverty", label: "Poverty", unit: "pct", prop: "Poverty_Rate_Percent", zeroAsMissing: false, priorityBoost: 3 },
    { key: "minority", label: "Minority", unit: "pct", prop: "Pct_Minority", zeroAsMissing: false, priorityBoost: 3 },
    { key: "energy_burden", label: "Energy Burden", unit: "pct", prop: "Energy_Burden_PctIncome_disp", zeroAsMissing: true, priorityBoost: 2 },
    { key: "energy_cost", label: "Avg Energy Cost", unit: "usd", prop: "Avg_Annual_Energy_Cost_USD", zeroAsMissing: false, priorityBoost: 2 },
    { key: "electricity_use", label: "Electricity Use", unit: "mwh", prop: "Elec_Consumption_MWh_perCapita_disp", zeroAsMissing: true, priorityBoost: 2 },
    { key: "heat_index", label: "Heat+Climate Stress", unit: "score", prop: "Heat_Climate_Stress_Index", zeroAsMissing: true, priorityBoost: 5 },
    { key: "heat_fema_risk", label: "Heat Wave Risk", unit: "score", prop: "HWAV_RISKS", zeroAsMissing: true, priorityBoost: 4 },
    { key: "heat_cdd", label: "Cooling Degree Days", unit: "cdd", prop: "NOAA_CDD_Recent5yr", zeroAsMissing: true, priorityBoost: 3 },
    { key: "heat_feedback", label: "Heat Feedback", unit: "score", prop: "DC_Heat_Feedback_Index", zeroAsMissing: true, priorityBoost: 5 },
    { key: "grid_fossil", label: "Grid Fossil Share", unit: "pct", prop: "Grid_Fossil_Share_Pct", zeroAsMissing: true, priorityBoost: 4 },
    { key: "grid_carbon_intensity", label: "Grid Carbon Intensity", unit: "kgco2", prop: "Grid_Carbon_Intensity_kg_per_MWh", zeroAsMissing: true, priorityBoost: 4 },
    { key: "grid_carbon_exposure", label: "Carbon Exposure", unit: "score", prop: "DC_Carbon_Exposure_Index", zeroAsMissing: true, priorityBoost: 5 },
    { key: "noise_impact", label: "Noise+Community Impact", unit: "score", prop: "Noise_Community_Impact_Index", zeroAsMissing: true, priorityBoost: 5 },
    { key: "noise_faa", label: "FAA Noise Exposure", unit: "score", prop: "FAA_Noise_Exposure_Index", zeroAsMissing: true, priorityBoost: 4 },
    { key: "noise_ops", label: "Airport Operations", unit: "count", prop: "FAA_Airport_Operations_Total", zeroAsMissing: true, priorityBoost: 3 },
    { key: "noise_311", label: "Chicago 311 Noise", unit: "count", prop: "Chicago_311_Noise_AnnualAvg_Recent3yr", zeroAsMissing: true, priorityBoost: 3 },
    { key: "noise_tri", label: "TRI Industrial Pressure", unit: "score", prop: "EPA_TRI_Industrial_Pressure_Index", zeroAsMissing: true, priorityBoost: 4 },
    { key: "noise_tri_fac", label: "TRI Active Facilities", unit: "count", prop: "EPA_TRI_Active_Facility_Count", zeroAsMissing: true, priorityBoost: 3 },
    { key: "noise_overlap", label: "Noise Overlap", unit: "score", prop: "DC_Noise_Community_Overlap_Index", zeroAsMissing: true, priorityBoost: 5 },
    { key: "landcover_urban", label: "Urban Built-Up Land", unit: "pct", prop: "LandCover_UrbanBuiltUp_Pct", zeroAsMissing: false, priorityBoost: 2 },
    { key: "zoning_annoyance", label: "Zoning Annoyance Threshold", unit: "score", prop: "Zoning_Annoyance_Threshold_Index", zeroAsMissing: true, priorityBoost: 4 },
    { key: "zoning_allowance", label: "Zoning Allowance", unit: "pct", prop: "Zoning_Allowance_Index", zeroAsMissing: true, priorityBoost: 3 },
    { key: "zoning_near_residential", label: "Sites Near Residential Zoning", unit: "pct", prop: "Chicago_Zoning_Residential_Nearby500m_Share_Pct", zeroAsMissing: true, priorityBoost: 4 }
  ];
  const PEER_PROFILE_DEFS = [
    { prop: "Poverty_Rate_Percent", unit: "pct", weight: 1.1 },
    { prop: "Pct_Minority", unit: "pct", weight: 1.1 },
    { prop: "Median_Household_Income", unit: "usd", weight: 1.0 },
    { prop: "Energy_Burden_PctIncome_disp", unit: "pct", weight: 0.9 },
    { prop: "AQI_P90", unit: "aqi", weight: 0.8 },
    { prop: "Elec_Consumption_MWh_perCapita_disp", unit: "mwh", weight: 0.7 }
  ];
  const PRESSURE_SEGMENT_COLORS = {
    existing: "#1d9d77",
    proposed: "#2c72d6",
    inventory: "#9c63d7",
    denied: "#db5068"
  };

  let workspace = WORKSPACE.HOME;
  let mobilePanelOpen = false;
  let isMobileViewport = false;
  let onPopState;
  let onResize;
  let mapEl, map, overlay;
  let currentStyleUrl = BASEMAP_STYLES.light;
  let loading = true, error = "";
  let routeLoadError = "";
  let counties, sites, metadata, globalRegistry;

  let mapScenario = "planned";
  let baseStyle = "light";
  let countyLayer = "impact";
  let layeredNarrativeStep = LAYERED_NARRATIVE_STEPS[0].key;
  let narrativeAutoplay = false;
  let narrativeAutoplaySeconds = 6;
  let narrativeAutoplayTimer;
  let countyOpacity = 0.75;
  let siteRadius = 8;
  let showExisting = true, showProposed = true, showDenied = true, showInventory = false, showRegistry = true, showOutlines = true;
  let annoyanceThreshold = DEFAULT_ANNOYANCE_THRESHOLD;
  let showAnnoyanceOverlay = true;
  let mapZoomCounty = "";
  let selectedCounty = null;
  let selectedSite = null;
  let mapToast = "";
  let mapToastTimer;
  const MAP_TOAST_MS = 900;
  let mapQueryReady = false;
  let lastMapLayerSignature = "";
  let jsPdfPromise;
  let metricSeriesCache = {};
  let peerMetricStatsCache = {};
  let selectedCountyIndicators = [];
  let selectedCountyQuality = null;
  let countyWatchlistAll = [];
  let countyWatchlist = [];
  let watchlistByGeoid = new Map();
  let watchlistFallback = [];
  let watchlistEmptyMessage = "";
  let watchlistModeLabel = "Recommended baseline";
  let annoyanceByGeoid = new Map();
  let annoyanceExceeding = [];
  let annoyanceExceedingSet = new Set();
  let pressureSummaryCurrent = new Map();
  let pressureSummaryPlanned = new Map();

  let briefScenario = "planned", briefFocus = "Balanced overview", briefOnlyWithSites = true, briefCounty = "", briefData = null, briefText = "";
  let studioScenario = "planned", studioOnlyWithSites = true, studioCounty = "", studioData = null, studioText = "";
  let retireExisting = 0, addProposed = 0, cancelProposed = 0, addInventory = 0, removeInventory = 0, addDenied = 0;
  let pressureWeightExisting = DEFAULT_PRESSURE_WEIGHTS.existing;
  let pressureWeightProposed = DEFAULT_PRESSURE_WEIGHTS.proposed;
  let pressureWeightInventory = DEFAULT_PRESSURE_WEIGHTS.inventory;
  let pressureWeightDenied = DEFAULT_PRESSURE_WEIGHTS.denied;
  let selectedPressureProfile = "baseline";
  let lastBriefAutoSignature = "";
  let BriefWorkspaceComponent = null;
  let StudioWorkspaceComponent = null;
  let RegistryWorkspaceComponent = null;
  let contentEl;
  let ambientX = 52;
  let ambientY = 26;

  const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : null);
  const fmt = (v, t) => {
    const n = num(v);
    if (n === null) return "N/A";
    if (t === "pct") return `${n.toFixed(1)}%`;
    if (t === "usd") return `$${n.toFixed(0)}`;
    if (t === "count") return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (t === "density") return `${n.toFixed(2)} / 1000 km2`;
    if (t === "mwh") return `${n.toFixed(2)} MWh/cap`;
    if (t === "aqi") return `${n.toFixed(1)} AQI`;
    if (t === "days") return `${n.toFixed(0)} days`;
    if (t === "cdd") return `${n.toFixed(0)} CDD`;
    if (t === "degf") return `${n.toFixed(1)}F`;
    if (t === "kgco2") return `${n.toFixed(1)} kg CO2/MWh`;
    if (t === "ktco2") return `${n.toFixed(1)} kt CO2/yr`;
    return n.toFixed(2);
  };

  const parseBoolParam = (raw, fallback) => {
    if (raw === "1" || raw === "true") return true;
    if (raw === "0" || raw === "false") return false;
    return fallback;
  };

  const clamp = (value, min, max, fallback) => {
    const n = num(value);
    if (n === null) return fallback;
    return Math.min(max, Math.max(min, n));
  };

  const normalizePressureWeight = (value, fallback) => {
    if (value === "" || value === null || value === undefined) return Number(fallback);
    const n = num(value);
    const base = n === null ? fallback : n;
    const bounded = Math.min(PRESSURE_WEIGHT_LIMITS.max, Math.max(PRESSURE_WEIGHT_LIMITS.min, base));
    return Number(bounded.toFixed(2));
  };

  function configuredPressureWeights() {
    const source = metadata?.weights?.pressure || DEFAULT_PRESSURE_WEIGHTS;
    return {
      existing: normalizePressureWeight(source.existing, DEFAULT_PRESSURE_WEIGHTS.existing),
      proposed: normalizePressureWeight(source.proposed, DEFAULT_PRESSURE_WEIGHTS.proposed),
      inventory: normalizePressureWeight(source.inventory, DEFAULT_PRESSURE_WEIGHTS.inventory),
      denied: normalizePressureWeight(source.denied, DEFAULT_PRESSURE_WEIGHTS.denied)
    };
  }

  function setPressureWeights(weights) {
    pressureWeightExisting = normalizePressureWeight(weights?.existing, DEFAULT_PRESSURE_WEIGHTS.existing);
    pressureWeightProposed = normalizePressureWeight(weights?.proposed, DEFAULT_PRESSURE_WEIGHTS.proposed);
    pressureWeightInventory = normalizePressureWeight(weights?.inventory, DEFAULT_PRESSURE_WEIGHTS.inventory);
    pressureWeightDenied = normalizePressureWeight(weights?.denied, DEFAULT_PRESSURE_WEIGHTS.denied);
  }

  function pressureWeightsForProfile(profileKey) {
    const profile = PRESSURE_WEIGHT_PROFILES[profileKey] || PRESSURE_WEIGHT_PROFILES.baseline;
    if (!profile.weights) return configuredPressureWeights();
    return {
      existing: normalizePressureWeight(profile.weights.existing, DEFAULT_PRESSURE_WEIGHTS.existing),
      proposed: normalizePressureWeight(profile.weights.proposed, DEFAULT_PRESSURE_WEIGHTS.proposed),
      inventory: normalizePressureWeight(profile.weights.inventory, DEFAULT_PRESSURE_WEIGHTS.inventory),
      denied: normalizePressureWeight(profile.weights.denied, DEFAULT_PRESSURE_WEIGHTS.denied)
    };
  }

  function pressureWeightsEqual(a, b) {
    const keys = ["existing", "proposed", "inventory", "denied"];
    return keys.every((key) => Math.abs(Number(a?.[key] || 0) - Number(b?.[key] || 0)) < 0.001);
  }

  function applyPressureProfile(profileKey) {
    if (profileKey === "custom") {
      selectedPressureProfile = "custom";
      return;
    }
    const weights = pressureWeightsForProfile(profileKey);
    setPressureWeights(weights);
    selectedPressureProfile = profileKey;
  }

  function resetPressureWeights() {
    applyPressureProfile("baseline");
  }

  const routeLoaderByWorkspace = {
    [WORKSPACE.BRIEF]: () => import("./workspaces/BriefWorkspace.svelte"),
    [WORKSPACE.STUDIO]: () => import("./workspaces/StudioWorkspace.svelte"),
    [WORKSPACE.REGISTRY]: () => import("./workspaces/RegistryWorkspace.svelte")
  };

  function handleAmbientMove(event) {
    if (!contentEl) return;
    const rect = contentEl.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    ambientX = Math.min(100, Math.max(0, ((event.clientX - rect.left) / rect.width) * 100));
    ambientY = Math.min(100, Math.max(0, ((event.clientY - rect.top) / rect.height) * 100));
  }

  function resetAmbient() {
    ambientX = 52;
    ambientY = 26;
  }

  function showMapToast(message) {
    mapToast = message;
    clearTimeout(mapToastTimer);
    mapToastTimer = setTimeout(() => {
      mapToast = "";
    }, MAP_TOAST_MS);
  }

  function applyMapStateFromQuery(search) {
    const params = new URLSearchParams(search || "");
    const scenario = params.get("scenario");
    if (SCENARIOS.some((s) => s.key === scenario)) mapScenario = scenario;
    const layer = params.get("layer");
    if (layer && COUNTY_LAYERS[layer]) countyLayer = layer;
    const basemap = params.get("basemap");
    if (basemap && BASEMAP_STYLES[basemap]) baseStyle = basemap;
    countyOpacity = clamp(params.get("opacity"), 0.2, 1, countyOpacity);
    siteRadius = clamp(params.get("size"), 4, 16, siteRadius);
    showExisting = parseBoolParam(params.get("existing"), showExisting);
    showProposed = parseBoolParam(params.get("proposed"), showProposed);
    showDenied = parseBoolParam(params.get("denied"), showDenied);
    showInventory = parseBoolParam(params.get("inventory"), showInventory);
    showRegistry = parseBoolParam(params.get("registry"), showRegistry);
    showOutlines = parseBoolParam(params.get("outlines"), showOutlines);
    annoyanceThreshold = clamp(params.get("annoyance_x"), 0, 100, annoyanceThreshold);
    showAnnoyanceOverlay = parseBoolParam(params.get("annoyance_overlay"), showAnnoyanceOverlay);
    const narrative = params.get("narrative");
    if (narrative && LAYERED_NARRATIVE_STEPS.some((s) => s.key === narrative)) layeredNarrativeStep = narrative;
    const county = params.get("zoom");
    if (county) mapZoomCounty = county;
  }

  function mapStateQuery() {
    const params = new URLSearchParams();
    params.set("scenario", mapScenario);
    params.set("layer", countyLayer);
    params.set("basemap", baseStyle);
    params.set("opacity", Number(countyOpacity).toFixed(2));
    params.set("size", String(Math.round(Number(siteRadius))));
    params.set("existing", showExisting ? "1" : "0");
    params.set("proposed", showProposed ? "1" : "0");
    params.set("denied", showDenied ? "1" : "0");
    params.set("inventory", showInventory ? "1" : "0");
    params.set("registry", showRegistry ? "1" : "0");
    params.set("outlines", showOutlines ? "1" : "0");
    params.set("annoyance_x", String(Math.round(Number(annoyanceThreshold))));
    params.set("annoyance_overlay", showAnnoyanceOverlay ? "1" : "0");
    params.set("narrative", layeredNarrativeStep);
    if (mapZoomCounty) params.set("zoom", mapZoomCounty);
    return params.toString();
  }

  function writeMapStateToUrl(replace = true) {
    if (typeof window === "undefined") return;
    const targetPath = WORKSPACE_PATHS[WORKSPACE.MAP];
    const query = mapStateQuery();
    const target = query ? `${targetPath}?${query}` : targetPath;
    const current = `${window.location.pathname}${window.location.search}`;
    if (current === target) return;
    if (replace) {
      window.history.replaceState({}, "", target);
    } else {
      window.history.pushState({}, "", target);
    }
  }

  async function ensureRouteComponent(targetWorkspace) {
    if (!routeLoaderByWorkspace[targetWorkspace]) return;
    try {
      if (targetWorkspace === WORKSPACE.BRIEF && !BriefWorkspaceComponent) {
        const mod = await routeLoaderByWorkspace[targetWorkspace]();
        BriefWorkspaceComponent = mod.default;
      }
      if (targetWorkspace === WORKSPACE.STUDIO && !StudioWorkspaceComponent) {
        const mod = await routeLoaderByWorkspace[targetWorkspace]();
        StudioWorkspaceComponent = mod.default;
      }
      if (targetWorkspace === WORKSPACE.REGISTRY && !RegistryWorkspaceComponent) {
        const mod = await routeLoaderByWorkspace[targetWorkspace]();
        RegistryWorkspaceComponent = mod.default;
      }
    } catch (e) {
      routeLoadError = e instanceof Error ? e.message : "Failed to load workspace module.";
    }
  }

  function workspaceFromPath(pathname) {
    const p = String(pathname || "/").toLowerCase();
    if (p === "/" || p === "/home") return WORKSPACE.HOME;
    if (p === "/map") return WORKSPACE.MAP;
    if (p === "/briefing") return WORKSPACE.BRIEF;
    if (p === "/studio") return WORKSPACE.STUDIO;
    if (p === "/registry") return WORKSPACE.REGISTRY;
    return WORKSPACE.HOME;
  }

  function navigateWorkspace(nextWorkspace, replace = false) {
    if (!WORKSPACE_PATHS[nextWorkspace]) return;
    workspace = nextWorkspace;
    const basePath = WORKSPACE_PATHS[nextWorkspace];
    const target = nextWorkspace === WORKSPACE.MAP
      ? `${basePath}?${mapStateQuery()}`
      : basePath;
    if (`${window.location.pathname}${window.location.search}` !== target) {
      if (replace) {
        window.history.replaceState({}, "", target);
      } else {
        window.history.pushState({}, "", target);
      }
    }
  }

  function syncViewportMode() {
    if (typeof window === "undefined") return;
    isMobileViewport = window.innerWidth <= 1024;
    if (!isMobileViewport) mobilePanelOpen = false;
  }

  function toggleMobilePanel() {
    mobilePanelOpen = !mobilePanelOpen;
  }

  function closeMobilePanel() {
    mobilePanelOpen = false;
  }

  function openWorkspace(nextWorkspace) {
    navigateWorkspace(nextWorkspace);
    if (isMobileViewport) mobilePanelOpen = false;
  }

  function applyNarrativeStep(stepKey, toast = true) {
    const step = LAYERED_NARRATIVE_STEPS.find((s) => s.key === stepKey);
    if (!step) return;
    layeredNarrativeStep = step.key;
    mapScenario = step.scenario;
    countyLayer = step.countyLayer;
    showExisting = step.visibility.existing;
    showProposed = step.visibility.proposed;
    showDenied = step.visibility.denied;
    showInventory = step.visibility.inventory;
    showRegistry = step.visibility.registry;
    showOutlines = step.visibility.outlines;
    if (step.key === "ai_added_burden") {
      showAnnoyanceOverlay = true;
    }
    if (toast && workspace === WORKSPACE.MAP) {
      showMapToast(`Narrative step applied: ${step.label}`);
    }
  }

  function clearNarrativeAutoplayTimer() {
    clearTimeout(narrativeAutoplayTimer);
    narrativeAutoplayTimer = null;
  }

  function narrativeStepIndex(stepKey) {
    const idx = LAYERED_NARRATIVE_STEPS.findIndex((s) => s.key === stepKey);
    return idx >= 0 ? idx : 0;
  }

  function nextNarrativeStepKey(stepKey) {
    const idx = narrativeStepIndex(stepKey);
    return LAYERED_NARRATIVE_STEPS[(idx + 1) % LAYERED_NARRATIVE_STEPS.length]?.key || LAYERED_NARRATIVE_STEPS[0].key;
  }

  function scheduleNarrativeAutoplay() {
    clearNarrativeAutoplayTimer();
    if (!narrativeAutoplay || workspace !== WORKSPACE.MAP) return;
    const delayMs = Math.max(2500, Math.round(Number(narrativeAutoplaySeconds) * 1000));
    narrativeAutoplayTimer = setTimeout(() => {
      if (!narrativeAutoplay || workspace !== WORKSPACE.MAP) return;
      applyNarrativeStep(nextNarrativeStepKey(layeredNarrativeStep), true);
    }, delayMs);
  }

  function startNarrativeAutoplay() {
    if (workspace !== WORKSPACE.MAP) {
      navigateWorkspace(WORKSPACE.MAP);
    }
    narrativeAutoplay = true;
    showMapToast(`Narrative autoplay started (${Math.max(2.5, Number(narrativeAutoplaySeconds)).toFixed(1)}s/step).`);
  }

  function stopNarrativeAutoplay(showToast = true) {
    narrativeAutoplay = false;
    clearNarrativeAutoplayTimer();
    if (showToast && workspace === WORKSPACE.MAP) {
      showMapToast("Narrative autoplay paused.");
    }
  }

  function nextNarrativeStepManual() {
    applyNarrativeStep(nextNarrativeStepKey(layeredNarrativeStep), true);
  }

  function annoyanceBreakdownForProperties(properties) {
    if (!properties) return null;
    const parts = ANNOYANCE_COMPONENTS.map((def) => {
      const value = num(properties?.[def.prop]);
      const bench = metricBenchmark(value, metricValuesFromCounties(def.prop), def.unit);
      const percentile = bench?.percentile ?? null;
      return {
        ...def,
        value,
        percentile,
        weighted: percentile === null ? null : percentile * def.weight
      };
    });
    const available = parts.filter((x) => x.percentile !== null);
    if (!available.length) return null;
    const weightSum = available.reduce((acc, x) => acc + x.weight, 0);
    if (!weightSum) return null;
    const score = available.reduce((acc, x) => acc + ((x.percentile || 0) * (x.weight / weightSum)), 0);
    return {
      score: Number(score.toFixed(1)),
      availableCount: available.length,
      totalCount: parts.length,
      parts
    };
  }

  function applyWorkspaceTabMeta(targetWorkspace = workspace) {
    if (typeof document === "undefined") return;
    const meta = WORKSPACE_TAB_META[targetWorkspace] || WORKSPACE_TAB_META[WORKSPACE.HOME];
    document.title = meta.title;
    let iconLink = document.querySelector("link[rel='icon']");
    if (!iconLink) {
      iconLink = document.createElement("link");
      iconLink.setAttribute("rel", "icon");
      document.head.appendChild(iconLink);
    }
    iconLink.setAttribute("type", "image/svg+xml");
    iconLink.setAttribute("href", `${meta.icon}?v=${TAB_ICON_VERSION}`);
  }

  function countyProp(layer, scenario) {
    const cfg = COUNTY_LAYERS[layer];
    if (!cfg) return null;
    if (layer === "pressure") return scenario === "current" ? cfg.propCurrent : cfg.propPlanned;
    return cfg.prop;
  }

  function countyLayerGroup(key) {
    if (["none", "impact", "pressure", "annoyance_threshold", "economic", "cumulative", "justice_index"].includes(key)) return "core";
    if (key.startsWith("justice_") || ["poverty", "minority"].includes(key)) return "justice";
    if (key.startsWith("water_")) return "water";
    if (key.startsWith("grid_") || key === "dc_carbon_exposure") return "grid";
    if (key.startsWith("heat_") || key === "heat_feedback") return "heat";
    if (key.startsWith("noise_") || key === "noise_overlap") return "noise";
    if (key.startsWith("landcover_") || key.startsWith("zoning_") || key.startsWith("landuse_")) return "landuse";
    if (["aqi", "ozone", "pm25", "energy_burden", "avg_energy_cost", "electricity_use"].includes(key)) return "context";
    return "other";
  }

  function groupedCountyLayerOptions() {
    const groups = COUNTY_LAYER_GROUP_ORDER.map((id) => ({ id, label: COUNTY_LAYER_GROUP_LABEL[id], options: [] }));
    const indexById = new Map(groups.map((g, idx) => [g.id, idx]));
    for (const [key, cfg] of Object.entries(COUNTY_LAYERS)) {
      const g = countyLayerGroup(key);
      const idx = indexById.get(g);
      if (idx === undefined) continue;
      groups[idx].options.push({ key, label: cfg.label });
    }
    return groups.filter((g) => g.options.length > 0);
  }

  function scenarioSites(s) {
    if (!sites?.features) return [];
    const core = sites.features.filter((f) => f.properties?.status_class !== "registry");
    return core.filter((f) => (s === "current" ? f.properties?.status_class === "existing" : true));
  }

  function registrySites() {
    if (!sites?.features) return [];
    return sites.features.filter((f) => f.properties?.status_class === "registry");
  }

  function visibleMapSites() {
    const core = scenarioSites(mapScenario).filter((f) => {
      const s = f.properties?.status_class;
      if (s === "existing") return showExisting;
      if (s === "proposed") return showProposed;
      if (s === "denied") return showDenied;
      if (s === "inventory") return showInventory;
      return false;
    });
    const reg = showRegistry ? registrySites() : [];
    return [...core, ...reg];
  }

  function summarize(sFeatures) {
    const w = pressureWeights();
    const m = new Map();
    for (const f of sFeatures) {
      const g = String(f.properties?.GEOID || "").padStart(5, "0");
      if (!g) continue;
      if (!m.has(g)) m.set(g, { existing: 0, proposed: 0, denied: 0, inventory: 0, total: 0, score: 0 });
      const r = m.get(g);
      const s = f.properties?.status_class;
      if (s === "existing") r.existing += 1;
      if (s === "proposed") r.proposed += 1;
      if (s === "denied") r.denied += 1;
      if (s === "inventory") r.inventory += 1;
      r.total += 1;
    }
    for (const r of m.values()) {
      r.score = Number((r.existing * w.existing + r.proposed * w.proposed + r.denied * w.denied + r.inventory * w.inventory).toFixed(2));
    }
    return m;
  }

  const row0 = (m, g) => m.get(g) || { existing: 0, proposed: 0, denied: 0, inventory: 0, total: 0, score: 0 };
  const countyFeature = (g) => counties?.features?.find((f) => String(f.properties?.GEOID) === String(g));

  function pressureSummaryForScenario(scenario) {
    return scenario === "current" ? pressureSummaryCurrent : pressureSummaryPlanned;
  }

  function pressureScoreForCounty(geoid, scenario) {
    const summary = pressureSummaryForScenario(scenario);
    return row0(summary, String(geoid || "").padStart(5, "0")).score;
  }

  function pressureValuesForScenario(scenario) {
    if (!counties?.features?.length) return [];
    const summary = pressureSummaryForScenario(scenario);
    return counties.features.map((f) => row0(summary, String(f.properties?.GEOID || "").padStart(5, "0")).score);
  }

  function countyLayerValue(properties, layer, scenario) {
    if (!properties) return null;
    if (layer === "pressure") return pressureScoreForCounty(properties.GEOID, scenario);
    if (layer === "annoyance_threshold") {
      const found = annoyanceByGeoid.get(String(properties.GEOID || ""));
      return found ? found.score : null;
    }
    const prop = countyProp(layer, scenario);
    if (!prop) return null;
    return num(properties[prop]);
  }

  function countyLayerValues(layer, scenario) {
    if (!counties?.features || layer === "none") return [];
    if (layer === "pressure") return pressureValuesForScenario(scenario);
    if (layer === "annoyance_threshold") return [...annoyanceByGeoid.values()].map((x) => x.score);
    const prop = countyProp(layer, scenario);
    if (!prop) return [];
    return metricValuesFromCounties(prop);
  }

  function countyOptions(scenario, onlyWithSites) {
    if (!counties?.features) return [];
    const s = summarize(scenarioSites(scenario));
    const out = counties.features.map((f) => {
      const g = String(f.properties?.GEOID || "");
      return { geoid: g, name: f.properties?.County_Name || `${f.properties?.NAME || "Unknown"} County`, count: row0(s, g).total };
    });
    return (onlyWithSites ? out.filter((x) => x.count > 0) : out).sort((a, b) => (b.count - a.count) || a.name.localeCompare(b.name));
  }

  function geometryBounds(geometry) {
    const b = [Infinity, Infinity, -Infinity, -Infinity];
    const walk = (coords) => {
      if (!Array.isArray(coords)) return;
      if (typeof coords[0] === "number" && typeof coords[1] === "number") {
        b[0] = Math.min(b[0], coords[0]);
        b[1] = Math.min(b[1], coords[1]);
        b[2] = Math.max(b[2], coords[0]);
        b[3] = Math.max(b[3], coords[1]);
        return;
      }
      for (const c of coords) walk(c);
    };
    walk(geometry?.coordinates);
    return b;
  }

  function zoomToCounty(geoid) {
    if (!map || !counties?.features) return;
    const f = counties.features.find((x) => String(x?.properties?.GEOID) === String(geoid));
    if (!f) return;
    mapZoomCounty = String(geoid || "");
    const b = geometryBounds(f.geometry);
    if (!Number.isFinite(b[0])) return;
    map.fitBounds(
      [
        [b[0], b[1]],
        [b[2], b[3]]
      ],
      { padding: 42, duration: 800 }
    );
    showMapToast(`Zoomed to ${f.properties?.County_Name || f.properties?.NAME || "county"}.`);
  }

  function quantileBreaksForLayer(layer, scenario, bins = 5) {
    const vals = countyLayerValues(layer, scenario).filter((x) => x !== null).sort((a, b) => a - b);
    if (!vals.length) return [0, 1];
    if (vals.length === 1) return [vals[0], vals[0] + 1];

    // Zero-dominated handling for pressure layers:
    // put score=0 in its own bin, then distribute non-zero values across remaining bins.
    if (layer === "pressure") {
      const zeroCount = vals.filter((v) => v === 0).length;
      if (zeroCount >= Math.ceil(vals.length * 0.5)) {
        const nonZero = vals.filter((v) => v > 0);
        if (!nonZero.length) return [0, 1e-6, 1, 1, 1, 1];
        const out = [0, 1e-6];
        const remainingBins = Math.max(1, bins - 1);
        for (let i = 1; i <= remainingBins; i += 1) {
          const p = i / remainingBins;
          const idx = Math.min(nonZero.length - 1, Math.max(0, Math.floor(p * (nonZero.length - 1))));
          out.push(nonZero[idx]);
        }
        for (let i = 1; i < out.length; i += 1) {
          if (out[i] <= out[i - 1]) out[i] = out[i - 1] + 1e-6;
        }
        return out;
      }
    }

    const out = [];
    for (let i = 0; i <= bins; i += 1) {
      const p = i / bins;
      const idx = Math.min(vals.length - 1, Math.max(0, Math.floor(p * (vals.length - 1))));
      out.push(vals[idx]);
    }
    for (let i = 1; i < out.length; i += 1) {
      if (out[i] <= out[i - 1]) out[i] = out[i - 1] + 1e-6;
    }
    return out;
  }

  function legendEntriesForLayer(cfg, breaks) {
    if (!cfg?.colors?.length || !breaks?.length) return [];
    const binCount = Math.min(cfg.colors.length, Math.max(1, breaks.length - 1));
    const hasZeroBin = Math.abs(breaks[0]) < 1e-10 && breaks[1] <= 1e-4;
    return Array.from({ length: binCount }, (_, idx) => {
      const qStart = idx * 20;
      const qEnd = (idx + 1) * 20;
      const from = breaks[idx];
      const to = breaks[idx + 1];
      return {
        color: cfg.colors[idx],
        quantile: hasZeroBin && idx === 0 ? "No site pressure" : `Q${idx + 1} (${qStart}-${qEnd}%)`,
        rangeLabel: hasZeroBin && idx === 0 ? "Score = 0" : `${fmt(from, cfg.unit)} - ${fmt(to, cfg.unit)}`
      };
    });
  }

  function metricValuesFromCounties(prop) {
    if (!counties?.features || !prop) return [];
    if (metricSeriesCache[prop]) return metricSeriesCache[prop];
    const vals = counties.features.map((f) => num(f.properties?.[prop])).filter((v) => v !== null);
    metricSeriesCache[prop] = vals;
    return vals;
  }

  function quantileValue(sorted, q) {
    if (!sorted.length) return null;
    const pos = (sorted.length - 1) * q;
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    if (lo === hi) return sorted[lo];
    const w = pos - lo;
    return sorted[lo] * (1 - w) + sorted[hi] * w;
  }

  function metricBand(percentile) {
    if (!Number.isFinite(percentile)) return "Unknown";
    if (percentile >= 90) return "Very high";
    if (percentile >= 75) return "High";
    if (percentile >= 45) return "Moderate";
    if (percentile >= 25) return "Low";
    return "Very low";
  }

  function metricBenchmark(value, values, unit) {
    const nValue = num(value);
    if (nValue === null || !values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    // Use strict-less-than rank so low tied values (e.g., many zeros)
    // are not incorrectly pushed into high percentiles.
    const lessCount = sorted.filter((x) => x < nValue).length;
    const percentile = sorted.length === 1
      ? 50
      : (lessCount / (sorted.length - 1)) * 100;
    const bounded = Math.max(0, Math.min(100, percentile));
    return {
      value: nValue,
      percentile: Number(bounded.toFixed(1)),
      band: metricBand(bounded),
      median: quantileValue(sorted, 0.5),
      min: sorted[0],
      max: sorted[sorted.length - 1],
      count: sorted.length,
      unit
    };
  }

  function countyIndicatorProp(def, scenario) {
    if (def.propCurrent || def.propPlanned) {
      return scenario === "current" ? def.propCurrent : def.propPlanned;
    }
    return def.prop;
  }

  function countyIndicatorValue(def, properties, scenario) {
    if (!properties) return null;
    if (def.key === "pressure") return num(pressureScoreForCounty(properties.GEOID, scenario));
    if (def.key === "annoyance_score") return num(annoyanceByGeoid.get(String(properties.GEOID || ""))?.score);
    const prop = countyIndicatorProp(def, scenario);
    if (!prop) return null;
    return num(properties[prop]);
  }

  function countyIndicatorSeries(def, scenario) {
    if (def.key === "pressure") return pressureValuesForScenario(scenario);
    if (def.key === "annoyance_score") return [...annoyanceByGeoid.values()].map((x) => x.score);
    const prop = countyIndicatorProp(def, scenario);
    return metricValuesFromCounties(prop);
  }

  function indicatorIsMissing(def, value) {
    return value === null || (def.zeroAsMissing && value === 0);
  }

  function countyDataQuality(properties, scenario) {
    if (!properties) return null;
    const assessed = COUNTY_INDICATOR_DEFS.map((def) => {
      const prop = countyIndicatorProp(def, scenario);
      const raw = countyIndicatorValue(def, properties, scenario);
      const missing = indicatorIsMissing(def, raw);
      return { def, prop, value: raw, missing };
    });
    const total = assessed.length;
    const missingItems = assessed.filter((x) => x.missing);
    const available = total - missingItems.length;
    const coveragePct = total ? Number(((available / total) * 100).toFixed(1)) : 0;
    let confidence = "Low";
    if (coveragePct >= 85) confidence = "High";
    else if (coveragePct >= 60) confidence = "Medium";
    return {
      total,
      available,
      missing: missingItems.length,
      coveragePct,
      confidence,
      missingLabels: missingItems.map((x) => x.def.label)
    };
  }

  function peerMetricStats(prop) {
    if (peerMetricStatsCache[prop]) return peerMetricStatsCache[prop];
    const vals = metricValuesFromCounties(prop);
    if (!vals.length) {
      const empty = { mean: 0, std: 1 };
      peerMetricStatsCache[prop] = empty;
      return empty;
    }
    const mean = vals.reduce((acc, x) => acc + x, 0) / vals.length;
    const variance = vals.reduce((acc, x) => acc + (x - mean) * (x - mean), 0) / vals.length;
    const std = Math.sqrt(variance) || 1;
    const stats = { mean, std };
    peerMetricStatsCache[prop] = stats;
    return stats;
  }

  function peerDistance(aProps, bProps) {
    let dims = 0;
    let sum = 0;
    for (const def of PEER_PROFILE_DEFS) {
      const aVal = num(aProps?.[def.prop]);
      const bVal = num(bProps?.[def.prop]);
      if (aVal === null || bVal === null) continue;
      const stats = peerMetricStats(def.prop);
      if (!stats.std) continue;
      const za = (aVal - stats.mean) / stats.std;
      const zb = (bVal - stats.mean) / stats.std;
      const d = za - zb;
      sum += (def.weight || 1) * d * d;
      dims += 1;
    }
    if (!dims) return Number.POSITIVE_INFINITY;
    return Math.sqrt(sum / dims);
  }

  function peerComparisonForCounty(geoid, scenario, limit = 3) {
    if (!counties?.features?.length || !geoid) return null;
    const target = counties.features.find((f) => String(f.properties?.GEOID) === String(geoid));
    if (!target) return null;
    const targetPressure = pressureScoreForCounty(geoid, scenario) ?? 0;
    const peers = counties.features
      .filter((f) => String(f.properties?.GEOID) !== String(geoid))
      .map((f) => {
        const distance = peerDistance(target.properties, f.properties);
        const peerPressure = pressureScoreForCounty(f.properties?.GEOID, scenario) ?? 0;
        return {
          geoid: String(f.properties?.GEOID || ""),
          name: f.properties?.County_Name || `${f.properties?.NAME || "Unknown"} County`,
          distance,
          pressure: peerPressure
        };
      })
      .filter((x) => Number.isFinite(x.distance))
      .sort((a, b) => a.distance - b.distance)
      .slice(0, limit);
    if (!peers.length) return null;
    const peerAvgPressure = Number((peers.reduce((acc, p) => acc + p.pressure, 0) / peers.length).toFixed(2));
    const deltaVsPeers = Number((targetPressure - peerAvgPressure).toFixed(2));
    return {
      targetPressure: Number(targetPressure.toFixed(2)),
      peerAvgPressure,
      deltaVsPeers,
      peers
    };
  }

  function buildCountyWatchlist() {
    if (!counties?.features?.length) return [];
    const isBaselineMode = pressureWeightsEqual(pressureWeights(), pressureWeightsForProfile("baseline"));
    const baselinePlannedValues = metricValuesFromCounties("Pressure_Score_Planned");
    const plannedValues = isBaselineMode && baselinePlannedValues.length
      ? baselinePlannedValues
      : pressureValuesForScenario("planned");
    return counties.features
      .map((f) => {
        const p = f.properties || {};
        const geoid = String(p.GEOID || "");
        const planned = isBaselineMode
          ? (num(p.Pressure_Score_Planned) ?? (pressureScoreForCounty(geoid, "planned") ?? 0))
          : (pressureScoreForCounty(geoid, "planned") ?? 0);
        const current = isBaselineMode
          ? (num(p.Pressure_Score_Current) ?? (pressureScoreForCounty(geoid, "current") ?? 0))
          : (pressureScoreForCounty(geoid, "current") ?? 0);
        const delta = Number((planned - current).toFixed(2));
        const pressureBench = metricBenchmark(planned, plannedValues, "score");
        const impactBench = metricBenchmark(p.Impact_Score, metricValuesFromCounties("Impact_Score"), "score");
        const econBench = metricBenchmark(p.Economic_Vulnerability_Score, metricValuesFromCounties("Economic_Vulnerability_Score"), "score");
        const annoyance = annoyanceByGeoid.get(geoid);
        const vulnPct = Math.max(impactBench?.percentile ?? 0, econBench?.percentile ?? 0);
        const reasons = [];
        let severity = 0;
        if ((pressureBench?.percentile ?? 0) >= 85) {
          reasons.push("High planned pressure percentile");
          severity += 3;
        }
        if (delta >= 5) {
          reasons.push("Large pressure increase vs current");
          severity += 2;
        }
        if ((pressureBench?.percentile ?? 0) >= 70 && vulnPct >= 70) {
          reasons.push("High pressure + high vulnerability overlap");
          severity += 3;
        }
        if ((annoyance?.score ?? 0) >= Number(annoyanceThreshold)) {
          reasons.push(`Annoyance score >= ${Math.round(Number(annoyanceThreshold))}`);
          severity += 2;
        }
        return {
          geoid,
          name: p.County_Name || `${p.NAME || "Unknown"} County`,
          planned,
          current,
          delta,
          annoyance: annoyance?.score ?? null,
          reasons,
          severity
        };
      })
      .filter((x) => x.reasons.length > 0)
      .sort((a, b) => (b.severity - a.severity) || (b.planned - a.planned));
  }

  function buildWatchlistFallback(limit = 6) {
    if (!counties?.features?.length) return [];
    const isBaselineMode = pressureWeightsEqual(pressureWeights(), pressureWeightsForProfile("baseline"));
    return counties.features
      .map((f) => {
        const p = f.properties || {};
        const geoid = String(p.GEOID || "");
        const planned = isBaselineMode
          ? (num(p.Pressure_Score_Planned) ?? (pressureScoreForCounty(geoid, "planned") ?? 0))
          : (pressureScoreForCounty(geoid, "planned") ?? 0);
        const current = isBaselineMode
          ? (num(p.Pressure_Score_Current) ?? (pressureScoreForCounty(geoid, "current") ?? 0))
          : (pressureScoreForCounty(geoid, "current") ?? 0);
        const delta = Number((planned - current).toFixed(2));
        return {
          geoid,
          name: p.County_Name || `${p.NAME || "Unknown"} County`,
          planned,
          current,
          delta
        };
      })
      .filter((x) => x.planned > 0)
      .sort((a, b) => (b.planned - a.planned) || (b.delta - a.delta))
      .slice(0, limit);
  }

  function watchlistDiagnosticMessage(alerts) {
    if (!counties?.features?.length) return "Watchlist will populate after county data loads.";
    if (alerts?.length) return "";
    const w = pressureWeights();
    const weightTotal = Number((w.existing + w.proposed + w.inventory + w.denied).toFixed(2));
    if (weightTotal === 0) {
      return "No alerts because all Assumption Lab weights are 0 (existing, proposed, inventory, denied). Increase at least one weight above 0 to reactivate watchlist scoring.";
    }
    const isBaselineMode = pressureWeightsEqual(pressureWeights(), pressureWeightsForProfile("baseline"));
    const plannedValues = isBaselineMode
      ? (metricValuesFromCounties("Pressure_Score_Planned").length ? metricValuesFromCounties("Pressure_Score_Planned") : pressureValuesForScenario("planned"))
      : pressureValuesForScenario("planned");
    const nonZero = plannedValues.filter((v) => Number(v) > 0).length;
    if (!nonZero) {
      return "No alerts because all planned pressure scores are currently 0. Increase one or more Assumption Lab weights to activate pressure signals.";
    }
    return "No county crossed current watchlist thresholds (high planned percentile, large delta, or vulnerability overlap). Showing top pressure counties for context.";
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll("\"", "&quot;")
      .replaceAll("'", "&#39;");
  }

  function countyTopIndicators(properties, scenario, maxItems = 3) {
    if (!properties || !counties?.features) return [];
    const evaluated = COUNTY_INDICATOR_DEFS.map((def) => {
      const raw = countyIndicatorValue(def, properties, scenario);
      const missing = indicatorIsMissing(def, raw);
      if (missing) {
        return {
          label: def.label,
          missing: true,
          reason: "Missing or zero-placeholder value."
        };
      }
      const bench = metricBenchmark(raw, countyIndicatorSeries(def, scenario), def.unit);
      return {
        label: def.label,
        missing: false,
        valueLabel: fmt(raw, def.unit),
        band: bench?.band || "Unknown",
        percentile: bench?.percentile ?? null,
        rank: (bench?.percentile ?? 0) + (def.priorityBoost || 0)
      };
    });

    const present = evaluated
      .filter((x) => !x.missing)
      .sort((a, b) => (b.rank - a.rank) || String(a.label).localeCompare(String(b.label)));
    const missing = evaluated.filter((x) => x.missing);
    const out = [...present.slice(0, maxItems)];
    while (out.length < maxItems && missing.length) out.push(missing.shift());
    return out;
  }

  function benchmarkSummary(metricName, bench) {
    if (!bench) return `${metricName}: Context unavailable.`;
    return `${metricName}: ${bench.band} (${bench.percentile}th percentile of ${bench.count} Illinois counties; median ${fmt(bench.median, bench.unit)}, range ${fmt(bench.min, bench.unit)} to ${fmt(bench.max, bench.unit)}).`;
  }

  function weightFmt(v) {
    const n = num(v);
    if (n === null) return "0";
    return n.toFixed(2).replace(/\.?0+$/, "");
  }

  function pressureWeights() {
    return {
      existing: normalizePressureWeight(pressureWeightExisting, DEFAULT_PRESSURE_WEIGHTS.existing),
      proposed: normalizePressureWeight(pressureWeightProposed, DEFAULT_PRESSURE_WEIGHTS.proposed),
      inventory: normalizePressureWeight(pressureWeightInventory, DEFAULT_PRESSURE_WEIGHTS.inventory),
      denied: normalizePressureWeight(pressureWeightDenied, DEFAULT_PRESSURE_WEIGHTS.denied)
    };
  }

  function pressureWeightSignature() {
    const w = pressureWeights();
    return `${w.existing}|${w.proposed}|${w.inventory}|${w.denied}`;
  }

  function pressureFormulaDetails(counts) {
    const weights = pressureWeights();
    const order = ["existing", "proposed", "inventory", "denied"];
    const items = order.map((key) => {
      const count = Number(counts?.[key] || 0);
      const weight = Number(weights?.[key] || 0);
      const points = Number((count * weight).toFixed(2));
      return {
        key,
        label: PRESSURE_STATUS_META[key]?.label || key,
        help: PRESSURE_STATUS_META[key]?.help || "",
        count,
        weight,
        points
      };
    });
    const total = Number(items.reduce((acc, item) => acc + item.points, 0).toFixed(2));
    const itemsWithShare = items.map((item) => ({
      ...item,
      sharePct: total > 0 ? Number(((item.points / total) * 100).toFixed(1)) : 0,
      color: PRESSURE_SEGMENT_COLORS[item.key] || "#7c91ad"
    }));
    const expression = itemsWithShare.map((item) => `${item.count} x ${weightFmt(item.weight)} = ${item.points}`).join(" | ");
    return {
      items: itemsWithShare,
      total,
      expression,
      equation: `Pressure Score = (Existing x ${weightFmt(weights.existing)}) + (Proposed x ${weightFmt(weights.proposed)}) + (Inventory x ${weightFmt(weights.inventory)}) + (Denied x ${weightFmt(weights.denied)})`,
      explainer: "Higher score means greater modeled county pressure from data center footprint and pipeline mix.",
      rationale: order.map((key) => ({
        key,
        label: PRESSURE_STATUS_META[key]?.label || key,
        weight: Number(weights?.[key] || 0),
        text: PRESSURE_WEIGHT_RATIONALE[key] || ""
      }))
    };
  }

  function pressureDetailLines(details) {
    if (!details?.items?.length) return [];
    return details.items.map((item) => `${item.label}: ${item.help} (${item.count} x ${weightFmt(item.weight)} = ${item.points})`);
  }

  function pressureRationaleLines(details) {
    if (!details?.rationale?.length) return [];
    return details.rationale.map((item) => `${item.label} weight ${weightFmt(item.weight)}: ${item.text}`);
  }

  function focusInsight(metric, value, unit, bench) {
    return {
      metric,
      value: fmt(value, unit),
      band: bench?.band || "Unknown",
      percentile: Number.isFinite(Number(bench?.percentile)) ? Number(bench.percentile) : null
    };
  }

  function focusInsightText(item) {
    if (!item) return "";
    if (!Number.isFinite(Number(item.percentile))) return `${item.metric}: ${item.value} (${item.band}).`;
    return `${item.metric}: ${item.value} (${item.band}, ${item.percentile}th percentile).`;
  }

  function buildBriefFocusLens(focus, context) {
    const deltaLabel = `${context.delta >= 0 ? "+" : ""}${context.delta}`;
    const pressureTrend = {
      metric: "Pressure trend",
      value: `${context.rC.score} -> ${context.rP.score}`,
      band: context.delta > 0 ? "Rising" : context.delta < 0 ? "Falling" : "Stable",
      percentile: null
    };
    const focusKey = String(focus || "").toLowerCase();

    if (focusKey.includes("environmental")) {
      return {
        title: "Environmental Stress Focus",
        summary: "Prioritizes air-exposure and cumulative environmental load when interpreting data center expansion risk.",
        insights: [
          focusInsight("AQI P90", context.p.AQI_P90, "aqi", context.aqiBench),
          focusInsight("Ozone Days", context.p.Ozone_Days, "days", context.ozoneBench),
          focusInsight("PM2.5 Days", context.p.PM25_Days, "days", context.pm25Bench),
          pressureTrend
        ],
        actions: [
          "Require phased approvals tied to air-quality and emissions checkpoints.",
          "Attach monitoring conditions for backup generation, construction, and cooling systems.",
          "Publish annual county environmental trend reporting with operator commitments."
        ],
        benchmarkKeys: ["aqi", "ozone", "pm25", "pressure"]
      };
    }

    if (focusKey.includes("economic")) {
      return {
        title: "Economic Vulnerability Focus",
        summary: "Emphasizes social and household-cost sensitivity when evaluating new infrastructure concentration.",
        insights: [
          focusInsight("Poverty", context.p.Poverty_Rate_Percent, "pct", context.povertyBench),
          focusInsight("Minority", context.p.Pct_Minority, "pct", context.minorityBench),
          focusInsight("Energy Burden", context.p.Energy_Burden_PctIncome_disp, "pct", context.energyBurdenBench),
          focusInsight("Avg Energy Cost", context.p.Avg_Annual_Energy_Cost_USD, "usd", context.energyCostBench),
          pressureTrend
        ],
        actions: [
          "Prioritize counties with high vulnerability for targeted mitigation agreements.",
          "Pair approvals with household energy-relief or community benefit commitments.",
          "Track affordability indicators alongside buildout milestones."
        ],
        benchmarkKeys: ["poverty", "minority", "energy_burden", "energy_cost", "pressure"]
      };
    }

    if (focusKey.includes("public hearing")) {
      return {
        title: "Public Hearing Prep Focus",
        summary: "Converts quantitative signals into hearing-ready prompts for evidence-backed decision discussion.",
        insights: [
          focusInsight("Pressure", context.rA.score, "score", context.pressureBench),
          focusInsight("AQI P90", context.p.AQI_P90, "aqi", context.aqiBench),
          focusInsight("Poverty", context.p.Poverty_Rate_Percent, "pct", context.povertyBench),
          focusInsight("Minority", context.p.Pct_Minority, "pct", context.minorityBench),
          pressureTrend
        ],
        actions: [
          "Ask applicants to state expected load, mitigation timeline, and accountability milestones.",
          "Request county-level monitoring and public disclosure commitments before permit expansion.",
          "Document contingency triggers for pausing or reshaping phased buildout."
        ],
        benchmarkKeys: ["pressure", "aqi", "poverty", "minority"]
      };
    }

    return {
      title: "Balanced Overview Focus",
      summary: "Combines pressure, environmental, and community-vulnerability indicators for broad decision context.",
      insights: [
        focusInsight("Pressure", context.rA.score, "score", context.pressureBench),
        focusInsight("Poverty", context.p.Poverty_Rate_Percent, "pct", context.povertyBench),
        focusInsight("Minority", context.p.Pct_Minority, "pct", context.minorityBench),
        focusInsight("AQI P90", context.p.AQI_P90, "aqi", context.aqiBench),
        pressureTrend
      ],
      actions: [
        "Use phased build strategy with county monitoring checkpoints.",
        "Review both environmental and socioeconomic indicators before approval updates.",
        "Reassess county standing after each major project milestone."
      ],
      benchmarkKeys: ["pressure", "poverty", "minority", "aqi"]
    };
  }

  function benchmarkCard(metricLabel, value, unit, bench) {
    if (!bench) {
      return {
        metricLabel,
        valueLabel: "N/A",
        percentile: null,
        band: "Unknown",
        count: 0,
        minLabel: "N/A",
        medianLabel: "N/A",
        maxLabel: "N/A"
      };
    }
    return {
      metricLabel,
      valueLabel: fmt(value, unit),
      percentile: bench.percentile,
      band: bench.band,
      count: bench.count,
      minLabel: fmt(bench.min, unit),
      medianLabel: fmt(bench.median, unit),
      maxLabel: fmt(bench.max, unit)
    };
  }

  function percentileShiftSummary(fromBench, toBench) {
    if (!fromBench || !toBench) return "Context unavailable.";
    const diff = Number((toBench.percentile - fromBench.percentile).toFixed(1));
    if (Math.abs(diff) < 0.1) {
      return `No percentile movement (${fromBench.band} -> ${toBench.band}).`;
    }
    return `${diff > 0 ? "Up" : "Down"} ${Math.abs(diff)} percentile points (${fromBench.band} -> ${toBench.band}).`;
  }

  function color(v, breaks, ramp) {
    if (v === null || !Number.isFinite(v)) return [170, 177, 191, 68];
    const bins = Math.min(ramp.length, Math.max(1, breaks.length - 1));
    let idx = bins - 1;
    for (let i = 0; i < bins; i += 1) {
      if (v <= breaks[i + 1]) {
        idx = i;
        break;
      }
    }
    const c = ramp[Math.min(idx, ramp.length - 1)];
    return [c[0], c[1], c[2], Math.round(255 * countyOpacity)];
  }

  function layers() {
    const out = [];
    const cfg = COUNTY_LAYERS[countyLayer];
    const breaks = quantileBreaksForLayer(countyLayer, mapScenario, 5);
    if (countyLayer !== "none" && cfg && counties) {
      out.push(new GeoJsonLayer({
        id: `county-fill-${countyLayer}-${mapScenario}`,
        data: counties,
        filled: true,
        stroked: showOutlines,
        pickable: true,
        onClick: ({ object }) => {
          selectedCounty = object?.properties || null;
          selectedSite = null;
        },
        getFillColor: (f) => color(countyLayerValue(f.properties, countyLayer, mapScenario), breaks, cfg.colors),
        updateTriggers: {
          getFillColor: [
            countyLayer,
            mapScenario,
            countyOpacity,
            pressureWeightExisting,
            pressureWeightProposed,
            pressureWeightInventory,
            pressureWeightDenied,
            ...breaks
          ]
        },
        getLineColor: (f) =>
          selectedCounty && String(selectedCounty.GEOID) === String(f?.properties?.GEOID)
            ? [24, 36, 58, 255]
            : [80, 80, 80, 130],
        lineWidthMinPixels: (f) =>
          selectedCounty && String(selectedCounty.GEOID) === String(f?.properties?.GEOID)
            ? 2.3
            : 0.8
      }));
    } else if (showOutlines && counties) {
      out.push(
        new GeoJsonLayer({
          id: `county-outline-${countyLayer}-${mapScenario}`,
          data: counties,
          filled: false,
          stroked: true,
          pickable: true,
          onClick: ({ object }) => {
            selectedCounty = object?.properties || null;
            selectedSite = null;
          },
          getLineColor: [80, 80, 80, 140],
          lineWidthMinPixels: 0.8
        })
      );
    }
    if (counties && showAnnoyanceOverlay && annoyanceExceedingSet.size > 0) {
      out.push(
        new GeoJsonLayer({
          id: `annoyance-exceed-outline-${Math.round(Number(annoyanceThreshold))}`,
          data: {
            type: "FeatureCollection",
            features: counties.features.filter((f) => annoyanceExceedingSet.has(String(f?.properties?.GEOID || "")))
          },
          filled: false,
          stroked: true,
          pickable: false,
          getLineColor: [214, 96, 38, 220],
          lineWidthMinPixels: 2.4
        })
      );
    }
    out.push(new ScatterplotLayer({
      id: `sites-${mapScenario}`,
      data: visibleMapSites(),
      pickable: true,
      onClick: ({ object }) => {
        selectedSite = object?.properties || null;
        selectedCounty = null;
      },
      radiusUnits: "pixels",
      getPosition: (d) => [d.geometry.coordinates[0], d.geometry.coordinates[1]],
      getRadius: siteRadius,
      updateTriggers: {
        getRadius: [siteRadius],
        getFillColor: [mapScenario, showExisting, showProposed, showDenied, showInventory, showRegistry]
      },
      radiusMinPixels: 4,
      radiusMaxPixels: 18,
      getFillColor: (d) => SITE_COLORS[d.properties?.status_class] || [90, 90, 90, 190],
      getLineColor: [255, 255, 255, 220],
      lineWidthMinPixels: 1
    }));
    return out;
  }

  function tooltip({ object }) {
    if (!object) return null;
    const p = object.properties || {};
    if (p.status_class) {
      return {
        html: `<div><b>${p.name || "Site"}</b><br/>Status: ${p.status_class}<br/>Operator: ${p.operator || "Unknown"}<br/>County: ${p.County_Name || "N/A"}<br/>Source: ${p.data_source || "N/A"}</div>`,
        style: { backgroundColor: "#0f172a", color: "#fff", borderRadius: "10px", padding: "10px", fontFamily: "Space Grotesk, sans-serif" }
      };
    }
    const cfg = COUNTY_LAYERS[countyLayer];
    const layerValue = countyLayerValue(p, countyLayer, mapScenario);
    const topIndicators = countyTopIndicators(p, mapScenario, 3);
    const quality = countyDataQuality(p, mapScenario);
    const alert = watchlistByGeoid.get(String(p.GEOID || ""));
    const annoyance = annoyanceByGeoid.get(String(p.GEOID || ""));
    const heatIndex = fmt(p.Heat_Climate_Stress_Index, "score");
    const heatRisk = fmt(p.HWAV_RISKS, "score");
    const heatCdd = fmt(p.NOAA_CDD_Recent5yr, "cdd");
    const heatTmax = fmt(p.NOAA_Tmax_Summer_Recent5yr_F, "degf");
    const cleanShare = fmt(p.Grid_Clean_Share_Pct, "pct");
    const fossilShare = fmt(p.Grid_Fossil_Share_Pct, "pct");
    const carbonIntensity = fmt(p.Grid_Carbon_Intensity_kg_per_MWh, "kgco2");
    const co2Load = fmt(p.Grid_Est_CO2_kt_per_100MWyr, "ktco2");
    const topIndicatorsHtml = topIndicators.map((item) => {
      if (item.missing) return `<li><b>${escapeHtml(item.label)}</b>: ${escapeHtml(item.reason)}</li>`;
      const suffix = Number.isFinite(Number(item.percentile)) ? ` (${escapeHtml(item.band)}, ${item.percentile}th pct)` : "";
      return `<li><b>${escapeHtml(item.label)}</b>: ${escapeHtml(item.valueLabel)}${suffix}</li>`;
    }).join("");
    return {
      html:
        `<div><b>${p.County_Name || p.NAME || "County"}</b><br/>` +
        `${cfg?.label || "Layer"}: ${fmt(layerValue, cfg?.unit || "")}<br/>` +
        `<span style="opacity:0.92;">Annoyance score: ${annoyance ? fmt(annoyance.score, "score") : "N/A"}${annoyance && annoyance.score >= annoyanceThreshold ? ` (>= ${Math.round(Number(annoyanceThreshold))} threshold)` : ""}</span><br/>` +
        `<span style="opacity:0.92;">Heat: index ${heatIndex} | FEMA risk ${heatRisk}</span><br/>` +
        `<span style="opacity:0.92;">NOAA: ${heatCdd} | summer Tmax ${heatTmax}</span><br/>` +
        `<span style="opacity:0.92;">Grid mix: clean ${cleanShare} | fossil ${fossilShare}</span><br/>` +
        `<span style="opacity:0.92;">Grid carbon: ${carbonIntensity} | 100 MW est: ${co2Load}</span><br/>` +
        `<span style="opacity:0.92;">Data quality: ${escapeHtml(quality?.confidence || "Unknown")} (${quality?.available || 0}/${quality?.total || 0}, ${quality?.coveragePct ?? 0}%)</span><br/>` +
        `${alert ? `<span style="color:#ffd56a;">Watchlist: ${escapeHtml(alert.reasons[0] || "Flagged county")}</span><br/>` : ""}` +
        `<span style="opacity:0.92;">Top indicators:</span>` +
        `<ul style="margin:6px 0 0 16px;padding:0;">${topIndicatorsHtml}</ul></div>`,
      style: { backgroundColor: "#0f172a", color: "#fff", borderRadius: "10px", padding: "10px", fontFamily: "Space Grotesk, sans-serif" }
    };
  }

  function buildBrief() {
    const c = countyFeature(briefCounty);
    if (!c) {
      briefData = null;
      briefText = "";
      return;
    }
    const p = c.properties || {};
    const current = summarize(scenarioSites("current"));
    const planned = summarize(scenarioSites("planned"));
    const active = summarize(scenarioSites(briefScenario));
    const rC = row0(current, briefCounty), rP = row0(planned, briefCounty), rA = row0(active, briefCounty);
    const delta = Number((rP.score - rC.score).toFixed(2));
    const countySites = scenarioSites(briefScenario).filter((f) => String(f.properties?.GEOID) === String(briefCounty));
    const ops = [...new Map(countySites.map((f) => [f.properties?.operator || "", 0])).keys()].filter(Boolean).slice(0, 3);
    const links = [...new Set(countySites.flatMap((f) => String(f.properties?.sources || "").split(";").map((x) => x.trim()).filter(Boolean)))].slice(0, 12);
    const countyName = p.County_Name || `${p.NAME || "Unknown"} County`;
    const pressureBench = metricBenchmark(rA.score, pressureValuesForScenario(briefScenario), "score");
    const povertyBench = metricBenchmark(p.Poverty_Rate_Percent, metricValuesFromCounties("Poverty_Rate_Percent"), "pct");
    const minorityBench = metricBenchmark(p.Pct_Minority, metricValuesFromCounties("Pct_Minority"), "pct");
    const aqiBench = metricBenchmark(p.AQI_P90, metricValuesFromCounties("AQI_P90"), "aqi");
    const ozoneBench = metricBenchmark(p.Ozone_Days, metricValuesFromCounties("Ozone_Days"), "days");
    const pm25Bench = metricBenchmark(p.PM25_Days, metricValuesFromCounties("PM25_Days"), "days");
    const energyBurdenBench = metricBenchmark(p.Energy_Burden_PctIncome_disp, metricValuesFromCounties("Energy_Burden_PctIncome_disp"), "pct");
    const energyCostBench = metricBenchmark(p.Avg_Annual_Energy_Cost_USD, metricValuesFromCounties("Avg_Annual_Energy_Cost_USD"), "usd");
    const gridFossilBench = metricBenchmark(p.Grid_Fossil_Share_Pct, metricValuesFromCounties("Grid_Fossil_Share_Pct"), "pct");
    const gridCarbonBench = metricBenchmark(
      p.Grid_Carbon_Intensity_kg_per_MWh,
      metricValuesFromCounties("Grid_Carbon_Intensity_kg_per_MWh"),
      "kgco2"
    );
    const heatIndexBench = metricBenchmark(
      p.Heat_Climate_Stress_Index,
      metricValuesFromCounties("Heat_Climate_Stress_Index"),
      "score"
    );
    const heatRiskBench = metricBenchmark(
      p.HWAV_RISKS,
      metricValuesFromCounties("HWAV_RISKS"),
      "score"
    );
    const heatCddBench = metricBenchmark(
      p.NOAA_CDD_Recent5yr,
      metricValuesFromCounties("NOAA_CDD_Recent5yr"),
      "cdd"
    );
    const pressureFormula = pressureFormulaDetails(rA);
    const pressureFormulaLines = pressureDetailLines(pressureFormula);
    const pressureRationale = pressureRationaleLines(pressureFormula);
    const benchmarkCards = {
      pressure: benchmarkCard("Pressure", rA.score, "score", pressureBench),
      poverty: benchmarkCard("Poverty", p.Poverty_Rate_Percent, "pct", povertyBench),
      minority: benchmarkCard("Minority", p.Pct_Minority, "pct", minorityBench),
      aqi: benchmarkCard("AQI P90", p.AQI_P90, "aqi", aqiBench),
      ozone: benchmarkCard("Ozone Days", p.Ozone_Days, "days", ozoneBench),
      pm25: benchmarkCard("PM2.5 Days", p.PM25_Days, "days", pm25Bench),
      energy_burden: benchmarkCard("Energy Burden", p.Energy_Burden_PctIncome_disp, "pct", energyBurdenBench),
      energy_cost: benchmarkCard("Avg Energy Cost", p.Avg_Annual_Energy_Cost_USD, "usd", energyCostBench),
      heat_index: benchmarkCard("Heat+Climate Stress", p.Heat_Climate_Stress_Index, "score", heatIndexBench),
      heat_wave_risk: benchmarkCard("FEMA Heat Wave Risk", p.HWAV_RISKS, "score", heatRiskBench),
      heat_cdd: benchmarkCard("NOAA Cooling Degree Days", p.NOAA_CDD_Recent5yr, "cdd", heatCddBench),
      grid_fossil: benchmarkCard("Grid Fossil Share", p.Grid_Fossil_Share_Pct, "pct", gridFossilBench),
      grid_carbon: benchmarkCard("Grid Carbon Intensity", p.Grid_Carbon_Intensity_kg_per_MWh, "kgco2", gridCarbonBench)
    };
    const focusLens = buildBriefFocusLens(briefFocus, {
      p,
      rC,
      rP,
      rA,
      delta,
      pressureBench,
      povertyBench,
      minorityBench,
      aqiBench,
      ozoneBench,
      pm25Bench,
      energyBurdenBench,
      energyCostBench
    });
    const benchmarks = (focusLens.benchmarkKeys || []).map((key) => benchmarkCards[key]).filter(Boolean);
    const dataQuality = countyDataQuality(p, briefScenario);
    const peerComparison = peerComparisonForCounty(briefCounty, briefScenario, 3);
    const watchAlert = watchlistByGeoid.get(String(briefCounty));
    briefData = {
      countyName,
      scenario: SCENARIOS.find((s) => s.key === briefScenario)?.label || briefScenario,
      current: rC,
      planned: rP,
      active: rA,
      delta,
      ops,
      links,
      p,
      poverty: fmt(p.Poverty_Rate_Percent, "pct"),
      minority: fmt(p.Pct_Minority, "pct"),
      aqi: fmt(p.AQI_P90, "aqi"),
      heatStressIndex: fmt(p.Heat_Climate_Stress_Index, "score"),
      heatWaveRisk: fmt(p.HWAV_RISKS, "score"),
      heatCdd: fmt(p.NOAA_CDD_Recent5yr, "cdd"),
      heatSummerTmax: fmt(p.NOAA_Tmax_Summer_Recent5yr_F, "degf"),
      gridCleanShare: fmt(p.Grid_Clean_Share_Pct, "pct"),
      gridFossilShare: fmt(p.Grid_Fossil_Share_Pct, "pct"),
      gridCarbonIntensity: fmt(p.Grid_Carbon_Intensity_kg_per_MWh, "kgco2"),
      gridCO2LoadEstimate: fmt(p.Grid_Est_CO2_kt_per_100MWyr, "ktco2"),
      focusLens,
      benchmarks,
      dataQuality,
      peerComparison,
      watchAlert,
      pressureContext: benchmarkSummary("Pressure", pressureBench),
      povertyContext: benchmarkSummary("Poverty", povertyBench),
      minorityContext: benchmarkSummary("Minority", minorityBench),
      aqiContext: benchmarkSummary("AQI P90", aqiBench),
      pressureFormula
    };
    briefText =
      `# County Intelligence Briefing: ${countyName}\n\n` +
      `Scenario: ${briefData.scenario}\n\n` +
      `- Active pressure: ${rA.score} (existing=${rA.existing}, proposed=${rA.proposed}, denied=${rA.denied}, inventory=${rA.inventory})\n` +
      `- Current vs planned: ${rC.score} -> ${rP.score} (delta ${delta >= 0 ? "+" : ""}${delta})\n` +
      `- Poverty: ${fmt(p.Poverty_Rate_Percent, "pct")} | Minority: ${fmt(p.Pct_Minority, "pct")} | AQI P90: ${fmt(p.AQI_P90, "aqi")}\n` +
      `- Heat context: index ${fmt(p.Heat_Climate_Stress_Index, "score")} | FEMA heat-wave risk ${fmt(p.HWAV_RISKS, "score")} | NOAA CDD ${fmt(p.NOAA_CDD_Recent5yr, "cdd")} | summer Tmax ${fmt(p.NOAA_Tmax_Summer_Recent5yr_F, "degf")}\n` +
      `- Grid mix: clean ${fmt(p.Grid_Clean_Share_Pct, "pct")} | fossil ${fmt(p.Grid_Fossil_Share_Pct, "pct")} | carbon intensity ${fmt(p.Grid_Carbon_Intensity_kg_per_MWh, "kgco2")} | est 100 MW load ${fmt(p.Grid_Est_CO2_kt_per_100MWyr, "ktco2")}\n` +
      `- ${benchmarkSummary("Pressure", pressureBench)}\n` +
      `- ${benchmarkSummary("Poverty", povertyBench)}\n` +
      `- ${benchmarkSummary("Minority", minorityBench)}\n` +
      `- ${benchmarkSummary("AQI P90", aqiBench)}\n` +
      `- ${benchmarkSummary("Heat+climate stress", heatIndexBench)}\n` +
      `- ${benchmarkSummary("FEMA heat-wave risk", heatRiskBench)}\n` +
      `- ${benchmarkSummary("NOAA cooling degree days", heatCddBench)}\n` +
      `- ${benchmarkSummary("Grid fossil share", gridFossilBench)}\n` +
      `- ${benchmarkSummary("Grid carbon intensity", gridCarbonBench)}\n` +
      `- ${pressureFormula.equation}\n` +
      `- ${pressureFormula.explainer}\n` +
      pressureRationale.map((line) => `- ${line}\n`).join("") +
      `- Active scenario weighted points: ${pressureFormula.expression}\n` +
      pressureFormulaLines.map((line) => `- ${line}\n`).join("") +
      `- Active scenario pressure total: ${pressureFormula.total}\n` +
      `- Data quality: ${dataQuality?.confidence || "Unknown"} confidence (${dataQuality?.available || 0}/${dataQuality?.total || 0} fields, ${dataQuality?.coveragePct ?? 0}% coverage)\n` +
      `${peerComparison ? `- Peer comparison: pressure ${peerComparison.targetPressure} vs peer average ${peerComparison.peerAvgPressure} (delta ${peerComparison.deltaVsPeers >= 0 ? "+" : ""}${peerComparison.deltaVsPeers})\n` : ""}` +
      `${watchAlert ? `- Watchlist flag: ${watchAlert.reasons.join("; ")}\n` : ""}` +
      `- Focus lens: ${briefFocus}\n` +
      `- Focus summary: ${focusLens.summary}\n` +
      focusLens.insights.map((item) => `- Focus insight: ${focusInsightText(item)}\n`).join("") +
      focusLens.actions.map((line) => `- Focus action: ${line}\n`).join("") +
      `- Operators in scope: ${ops.join(", ") || "N/A"}\n\n` +
      `Evidence Keys:\n- data/processed/il_sites_enhanced.csv\n- data/processed/il_county_stats_enhanced.csv\n- data/raw/annual_aqi_by_county_2025.csv\n- data/raw/LEADTool_Data Counties.csv + data/raw/2016cityandcountyenergyprofiles.xlsb\n- data/processed/il_county_grid_emissions.csv (derived from EPA eGRID 2023 subregions + PLNT23)\n- data/processed/il_county_heat_climate.csv (NOAA Climate-at-a-Glance county series + FEMA National Risk Index)\n`;
  }

  function runStudio() {
    const c = countyFeature(studioCounty);
    if (!c) {
      studioData = null;
      studioText = "";
      return;
    }
    const base = summarize(scenarioSites(studioScenario));
    const b = row0(base, studioCounty);
    const w = pressureWeights();
    const p = {
      existing: Math.max(b.existing - Number(retireExisting), 0),
      proposed: Math.max(b.proposed - Number(cancelProposed), 0) + Number(addProposed),
      inventory: Math.max(b.inventory - Number(removeInventory), 0) + Number(addInventory),
      denied: b.denied + Number(addDenied)
    };
    p.total = p.existing + p.proposed + p.inventory + p.denied;
    p.score = Number((p.existing * w.existing + p.proposed * w.proposed + p.denied * w.denied + p.inventory * w.inventory).toFixed(2));
    const countyName = c.properties?.County_Name || `${c.properties?.NAME || "Unknown"} County`;
    const delta = Number((p.score - b.score).toFixed(2));
    const pressureValues = pressureValuesForScenario(studioScenario);
    const baselineBench = metricBenchmark(b.score, pressureValues, "score");
    const projectedBench = metricBenchmark(p.score, pressureValues, "score");
    const baselineFormula = pressureFormulaDetails(b);
    const projectedFormula = pressureFormulaDetails(p);
    const baselineFormulaLines = pressureDetailLines(baselineFormula);
    const projectedFormulaLines = pressureDetailLines(projectedFormula);
    const pressureRationale = pressureRationaleLines(baselineFormula);
    const pressureFormula = {
      equation: baselineFormula.equation,
      explainer: baselineFormula.explainer,
      baseline: baselineFormula,
      projected: projectedFormula
    };
    const countyHeatStress = num(c.properties?.Heat_Climate_Stress_Index);
    const countyHeatRisk = num(c.properties?.HWAV_RISKS);
    const countyCdd = num(c.properties?.NOAA_CDD_Recent5yr);
    const countyTmax = num(c.properties?.NOAA_Tmax_Summer_Recent5yr_F);
    const countyCarbonIntensity = num(c.properties?.Grid_Carbon_Intensity_kg_per_MWh);
    const countyCO2LoadEstimate = num(c.properties?.Grid_Est_CO2_kt_per_100MWyr);
    const baselineHeatFeedback = countyHeatStress === null ? null : Number((b.score * countyHeatStress).toFixed(2));
    const projectedHeatFeedback = countyHeatStress === null ? null : Number((p.score * countyHeatStress).toFixed(2));
    const heatFeedbackDelta =
      baselineHeatFeedback === null || projectedHeatFeedback === null
        ? null
        : Number((projectedHeatFeedback - baselineHeatFeedback).toFixed(2));
    const baselineCarbonExposure = countyCarbonIntensity === null ? null : Number((b.score * countyCarbonIntensity).toFixed(2));
    const projectedCarbonExposure = countyCarbonIntensity === null ? null : Number((p.score * countyCarbonIntensity).toFixed(2));
    const carbonExposureDelta =
      baselineCarbonExposure === null || projectedCarbonExposure === null
        ? null
        : Number((projectedCarbonExposure - baselineCarbonExposure).toFixed(2));
    const dataQuality = countyDataQuality(c.properties || {}, studioScenario);
    const peerComparison = peerComparisonForCounty(studioCounty, studioScenario, 3);
    const watchAlert = watchlistByGeoid.get(String(studioCounty));
    studioData = {
      countyName,
      scenario: SCENARIOS.find((s) => s.key === studioScenario)?.label || studioScenario,
      baseline: b,
      projected: p,
      delta,
      benchmarkCards: [
        benchmarkCard("Baseline pressure", b.score, "score", baselineBench),
        benchmarkCard("Projected pressure", p.score, "score", projectedBench)
      ],
      dataQuality,
      peerComparison,
      watchAlert,
      baselineContext: benchmarkSummary("Baseline pressure", baselineBench),
      projectedContext: benchmarkSummary("Projected pressure", projectedBench),
      standingShift: percentileShiftSummary(baselineBench, projectedBench),
      pressureFormula,
      heatStressIndex: fmt(countyHeatStress, "score"),
      heatWaveRisk: fmt(countyHeatRisk, "score"),
      heatCdd: fmt(countyCdd, "cdd"),
      heatSummerTmax: fmt(countyTmax, "degf"),
      baselineHeatFeedback,
      projectedHeatFeedback,
      heatFeedbackDelta,
      gridCarbonIntensity: fmt(countyCarbonIntensity, "kgco2"),
      gridCO2LoadEstimate: fmt(countyCO2LoadEstimate, "ktco2"),
      baselineCarbonExposure,
      projectedCarbonExposure,
      carbonExposureDelta
    };
    studioText =
      `# Impact Scenario Studio Note - ${countyName}\n\n` +
      `Base scenario: ${studioData.scenario}\n` +
      `Baseline pressure: ${b.score}\nProjected pressure: ${p.score}\nPressure delta: ${delta >= 0 ? "+" : ""}${delta}\n\n` +
      `Heat+climate index: ${fmt(countyHeatStress, "score")} | FEMA heat-wave risk: ${fmt(countyHeatRisk, "score")}\n` +
      `NOAA cooling degree days: ${fmt(countyCdd, "cdd")} | NOAA summer Tmax: ${fmt(countyTmax, "degf")}\n` +
      `${baselineHeatFeedback === null ? "" : `Baseline heat feedback proxy: ${baselineHeatFeedback}\n`}` +
      `${projectedHeatFeedback === null ? "" : `Projected heat feedback proxy: ${projectedHeatFeedback}\n`}` +
      `${heatFeedbackDelta === null ? "" : `Heat feedback delta: ${heatFeedbackDelta >= 0 ? "+" : ""}${heatFeedbackDelta}\n`}` +
      `Grid carbon intensity: ${fmt(countyCarbonIntensity, "kgco2")}\n` +
      `Estimated CO2 for 100 MW regional load: ${fmt(countyCO2LoadEstimate, "ktco2")}\n` +
      `${baselineCarbonExposure === null ? "" : `Baseline carbon exposure proxy: ${baselineCarbonExposure}\n`}` +
      `${projectedCarbonExposure === null ? "" : `Projected carbon exposure proxy: ${projectedCarbonExposure}\n`}` +
      `${carbonExposureDelta === null ? "" : `Carbon exposure delta: ${carbonExposureDelta >= 0 ? "+" : ""}${carbonExposureDelta}\n\n`}` +
      `${benchmarkSummary("Baseline pressure", baselineBench)}\n` +
      `${benchmarkSummary("Projected pressure", projectedBench)}\n` +
      `Standing shift: ${percentileShiftSummary(baselineBench, projectedBench)}\n` +
      `Data quality: ${dataQuality?.confidence || "Unknown"} confidence (${dataQuality?.available || 0}/${dataQuality?.total || 0} fields, ${dataQuality?.coveragePct ?? 0}% coverage)\n` +
      `${peerComparison ? `Peer comparison: pressure ${peerComparison.targetPressure} vs peer average ${peerComparison.peerAvgPressure} (delta ${peerComparison.deltaVsPeers >= 0 ? "+" : ""}${peerComparison.deltaVsPeers})\n` : ""}` +
      `${watchAlert ? `Watchlist flag: ${watchAlert.reasons.join("; ")}\n` : ""}` +
      `${pressureFormula.equation}\n` +
      `${pressureFormula.explainer}\n` +
      pressureRationale.map((line) => `- ${line}\n`).join("") +
      `Baseline weighted points: ${baselineFormula.expression} (total ${baselineFormula.total})\n` +
      baselineFormulaLines.map((line) => `- Baseline ${line}\n`).join("") +
      `Projected weighted points: ${projectedFormula.expression} (total ${projectedFormula.total})\n\n` +
      projectedFormulaLines.map((line) => `- Projected ${line}\n`).join("") +
      `Inputs:\n- Retire existing: ${retireExisting}\n- Add proposed: ${addProposed}\n- Cancel proposed: ${cancelProposed}\n- Add inventory: ${addInventory}\n- Remove inventory: ${removeInventory}\n- Add denied: ${addDenied}\n`;
  }

  function downloadText(fileName, text, type = "text/plain;charset=utf-8") {
    const blob = new Blob([text], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = fileName; document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }

  async function downloadPDF(fileName, title, text) {
    if (!jsPdfPromise) jsPdfPromise = import("jspdf");
    const { jsPDF } = await jsPdfPromise;
    const doc = new jsPDF({ unit: "pt", format: "letter" });
    const w = doc.internal.pageSize.getWidth();
    const h = doc.internal.pageSize.getHeight();
    const m = 42;
    let y = m;
    doc.setFont("helvetica", "bold"); doc.setFontSize(14); doc.text(title, m, y); y += 22;
    doc.setFont("helvetica", "normal"); doc.setFontSize(10);
    for (const line of doc.splitTextToSize(text, w - m * 2)) {
      if (y > h - m) { doc.addPage(); y = m; }
      doc.text(line, m, y); y += 14;
    }
    doc.save(fileName);
  }

  function briefFileBase() {
    const countyName = briefData?.countyName || "county";
    return countyName.replaceAll(" ", "_").toLowerCase();
  }

  function studioFileBase() {
    const countyName = studioData?.countyName || "county";
    return countyName.replaceAll(" ", "_").toLowerCase();
  }

  function downloadBriefMarkdown() {
    if (!briefData || !briefText) return;
    downloadText(`${briefFileBase()}_impact_brief.md`, briefText, "text/markdown;charset=utf-8");
  }

  async function downloadBriefPdf() {
    if (!briefData || !briefText) return;
    await downloadPDF(`${briefFileBase()}_impact_brief.pdf`, `County Intelligence Briefing - ${briefData.countyName}`, briefText);
  }

  function downloadStudioMarkdown() {
    if (!studioData || !studioText) return;
    downloadText(`${studioFileBase()}_scenario_note.md`, studioText, "text/markdown;charset=utf-8");
  }

  async function downloadStudioPdf() {
    if (!studioData || !studioText) return;
    await downloadPDF(`${studioFileBase()}_scenario_note.pdf`, `Impact Scenario Studio - ${studioData.countyName}`, studioText);
  }

  async function downloadPresentationPackPdf() {
    if (canBuildBrief && !briefData) buildBrief();
    if (canRunStudio && !studioData) runStudio();

    if (!jsPdfPromise) jsPdfPromise = import("jspdf");
    const { jsPDF } = await jsPdfPromise;
    const doc = new jsPDF({ unit: "pt", format: "letter" });
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();
    const margin = 40;
    let y = margin;

    const ensurePage = (needed = 16) => {
      if (y + needed > pageH - margin) {
        doc.addPage();
        y = margin;
      }
    };
    const writeTitle = (text) => {
      ensurePage(24);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(14);
      doc.text(text, margin, y);
      y += 20;
    };
    const writePara = (text, size = 10) => {
      doc.setFont("helvetica", "normal");
      doc.setFontSize(size);
      const lines = doc.splitTextToSize(String(text), pageW - margin * 2);
      for (const line of lines) {
        ensurePage(14);
        doc.text(line, margin, y);
        y += 13;
      }
    };

    const countyName = briefData?.countyName || studioData?.countyName || "Illinois County";
    const now = new Date();
    writeTitle("Presentation Pack | The People v. Hasty AI Development");
    writePara(`County: ${countyName}`);
    writePara(`Generated: ${now.toLocaleString()}`);
    y += 6;

    if (briefData) {
      writeTitle("County Intelligence Snapshot");
      writePara(`Scenario: ${briefData.scenario}`);
      writePara(`Active pressure: ${briefData.active.score} from ${briefData.active.total} records.`);
      writePara(`Current vs planned pressure: ${briefData.current.score} vs ${briefData.planned.score} (delta ${briefData.delta >= 0 ? "+" : ""}${briefData.delta}).`);
      if (briefData.dataQuality) {
        writePara(`Data quality: ${briefData.dataQuality.confidence} confidence (${briefData.dataQuality.available}/${briefData.dataQuality.total} fields, ${briefData.dataQuality.coveragePct}% coverage).`);
      }
      if (briefData.peerComparison) {
        writePara(`Peer comparison: county pressure ${briefData.peerComparison.targetPressure} vs peer average ${briefData.peerComparison.peerAvgPressure} (delta ${briefData.peerComparison.deltaVsPeers >= 0 ? "+" : ""}${briefData.peerComparison.deltaVsPeers}).`);
      }
      writePara(`Focus: ${briefFocus}`);
      for (const line of briefData.focusLens?.actions || []) {
        writePara(`- ${line}`);
      }
      y += 6;
    }

    if (studioData) {
      writeTitle("Impact Scenario Studio Snapshot");
      writePara(`Base scenario: ${studioData.scenario}`);
      writePara(`Baseline pressure: ${studioData.baseline.score}`);
      writePara(`Projected pressure: ${studioData.projected.score}`);
      writePara(`Pressure delta: ${studioData.delta >= 0 ? "+" : ""}${studioData.delta}`);
      writePara(`Standing shift: ${studioData.standingShift}`);
      if (studioData.dataQuality) {
        writePara(`Data quality: ${studioData.dataQuality.confidence} confidence (${studioData.dataQuality.available}/${studioData.dataQuality.total} fields, ${studioData.dataQuality.coveragePct}% coverage).`);
      }
      y += 6;
    }

    const relatedAlert = watchlistByGeoid.get(briefCounty || studioCounty || "");
    if (relatedAlert) {
      writeTitle("County Watchlist Alert");
      writePara(`${relatedAlert.name}: planned pressure ${relatedAlert.planned}, delta ${relatedAlert.delta >= 0 ? "+" : ""}${relatedAlert.delta}.`);
      for (const reason of relatedAlert.reasons) writePara(`- ${reason}`);
      y += 6;
    }

    if (map?.getCanvas) {
      try {
        const imgData = map.getCanvas().toDataURL("image/png");
        writeTitle("Map Snapshot");
        const boxW = pageW - margin * 2;
        const boxH = 240;
        ensurePage(boxH + 10);
        doc.addImage(imgData, "PNG", margin, y, boxW, boxH);
        y += boxH + 8;
      } catch (_) {
        writePara("Map snapshot unavailable in this browser context.");
      }
    }

    const file = `${countyName.replaceAll(" ", "_").toLowerCase()}_presentation_pack.pdf`;
    doc.save(file);
  }

  $: {
    sites;
    pressureWeightExisting; pressureWeightProposed; pressureWeightInventory; pressureWeightDenied;
    pressureSummaryCurrent = summarize(scenarioSites("current"));
    pressureSummaryPlanned = summarize(scenarioSites("planned"));
  }
  $: {
    const currentWeights = pressureWeights();
    if (pressureWeightsEqual(currentWeights, pressureWeightsForProfile("baseline"))) selectedPressureProfile = "baseline";
    else if (pressureWeightsEqual(currentWeights, pressureWeightsForProfile("cautious"))) selectedPressureProfile = "cautious";
    else if (pressureWeightsEqual(currentWeights, pressureWeightsForProfile("growthHeavy"))) selectedPressureProfile = "growthHeavy";
    else selectedPressureProfile = "custom";
  }
  $: briefOptions = countyOptions(briefScenario, briefOnlyWithSites);
  $: if (briefOptions.length && !briefOptions.find((x) => x.geoid === briefCounty)) briefCounty = briefOptions[0].geoid;
  $: if (!briefOptions.length) briefCounty = "";
  $: studioOptions = countyOptions(studioScenario, studioOnlyWithSites);
  $: if (studioOptions.length && !studioOptions.find((x) => x.geoid === studioCounty)) studioCounty = studioOptions[0].geoid;
  $: if (!studioOptions.length) studioCounty = "";
  $: canBuildBrief = briefOptions.length > 0 && Boolean(briefCounty);
  $: canRunStudio = studioOptions.length > 0 && Boolean(studioCounty);
  $: countyLayerGroupsForSelect = groupedCountyLayerOptions();
  $: activeCountyCfg = COUNTY_LAYERS[countyLayer];
  $: activeBreaks = quantileBreaksForLayer(countyLayer, mapScenario, 5);
  $: activeLegendEntries = legendEntriesForLayer(activeCountyCfg, activeBreaks);
  $: selectedCountyLayerValue = selectedCounty ? countyLayerValue(selectedCounty, countyLayer, mapScenario) : null;
  $: selectedCountyIndicators = selectedCounty ? countyTopIndicators(selectedCounty, mapScenario, 3) : [];
  $: selectedCountyQuality = selectedCounty ? countyDataQuality(selectedCounty, mapScenario) : null;
  $: {
    counties;
    annoyanceByGeoid = new Map(
      (counties?.features || [])
        .map((f) => {
          const geoid = String(f?.properties?.GEOID || "");
          if (!geoid) return null;
          const breakdown = annoyanceBreakdownForProperties(f.properties || {});
          if (!breakdown) return null;
          return [
            geoid,
            {
              geoid,
              name: f?.properties?.County_Name || `${f?.properties?.NAME || "Unknown"} County`,
              score: breakdown.score,
              breakdown
            }
          ];
        })
        .filter(Boolean)
    );
  }
  $: annoyanceExceeding = [...annoyanceByGeoid.values()]
    .filter((x) => Number.isFinite(Number(x.score)) && Number(x.score) >= Number(annoyanceThreshold))
    .sort((a, b) => Number(b.score) - Number(a.score));
  $: annoyanceExceedingSet = new Set(annoyanceExceeding.map((x) => String(x.geoid)));
  $: {
    counties;
    pressureWeightExisting; pressureWeightProposed; pressureWeightInventory; pressureWeightDenied;
    annoyanceThreshold; annoyanceByGeoid;
    const baselineMode = pressureWeightsEqual(pressureWeights(), pressureWeightsForProfile("baseline"));
    watchlistModeLabel = baselineMode ? "Recommended baseline" : "Custom Assumption Lab weights";
    countyWatchlistAll = counties?.features ? buildCountyWatchlist() : [];
    countyWatchlist = countyWatchlistAll.slice(0, 8);
    watchlistByGeoid = new Map((countyWatchlistAll || []).map((x) => [String(x.geoid), x]));
    watchlistFallback = countyWatchlistAll.length ? [] : (counties?.features ? buildWatchlistFallback(6) : []);
    watchlistEmptyMessage = watchlistDiagnosticMessage(countyWatchlistAll);
  }
  $: visibleSiteCount = visibleMapSites().length;
  $: mapCountyOptions = counties?.features
    ? counties.features
        .map((f) => ({
          geoid: String(f.properties?.GEOID || ""),
          name: f.properties?.County_Name || `${f.properties?.NAME || "Unknown"} County`
        }))
        .sort((a, b) => a.name.localeCompare(b.name))
    : [];
  $: if (mapCountyOptions.length && (!mapZoomCounty || !mapCountyOptions.find((x) => x.geoid === mapZoomCounty))) {
    mapZoomCounty = mapCountyOptions[0].geoid;
  }
  $: if (!mapCountyOptions.length) mapZoomCounty = "";

  $: if (workspace === WORKSPACE.BRIEF && !BriefWorkspaceComponent) void ensureRouteComponent(WORKSPACE.BRIEF);
  $: if (workspace === WORKSPACE.STUDIO && !StudioWorkspaceComponent) void ensureRouteComponent(WORKSPACE.STUDIO);
  $: if (workspace === WORKSPACE.REGISTRY && !RegistryWorkspaceComponent) void ensureRouteComponent(WORKSPACE.REGISTRY);
  $: if (workspace !== WORKSPACE.MAP && narrativeAutoplay) {
    stopNarrativeAutoplay(false);
  }
  $: if (narrativeAutoplay) {
    workspace; layeredNarrativeStep; narrativeAutoplaySeconds;
    scheduleNarrativeAutoplay();
  } else {
    clearNarrativeAutoplayTimer();
  }
  $: if (briefData && canBuildBrief) {
    const signature = `${briefCounty}|${briefScenario}|${briefFocus}|${pressureWeightSignature()}`;
    if (signature !== lastBriefAutoSignature) {
      lastBriefAutoSignature = signature;
      buildBrief();
    }
  }

  $: {
    const nextSignature = `${countyLayer}|${mapScenario}`;
    if (!lastMapLayerSignature) {
      lastMapLayerSignature = nextSignature;
    } else if (nextSignature !== lastMapLayerSignature) {
      lastMapLayerSignature = nextSignature;
      selectedCounty = null;
      selectedSite = null;
      if (workspace === WORKSPACE.MAP) {
        const scenarioLabel = SCENARIOS.find((s) => s.key === mapScenario)?.label || mapScenario;
        showMapToast(`Updated map: ${COUNTY_LAYERS[countyLayer]?.label || "Layer"} | ${scenarioLabel}`);
      }
    }
  }

  $: if (mapQueryReady && workspace === WORKSPACE.MAP) {
    mapScenario; countyLayer; baseStyle; countyOpacity; siteRadius;
    showExisting; showProposed; showDenied; showInventory; showRegistry; showOutlines; mapZoomCounty;
    layeredNarrativeStep; annoyanceThreshold; showAnnoyanceOverlay;
    writeMapStateToUrl(true);
  }

  // Critical fix: explicit dependencies for map updates.
  $: if (overlay && counties && sites) {
    mapScenario; countyLayer; showExisting; showProposed; showDenied; showInventory; showRegistry; showOutlines; countyOpacity; siteRadius; selectedCounty;
    pressureWeightExisting; pressureWeightProposed; pressureWeightInventory; pressureWeightDenied;
    annoyanceThreshold; showAnnoyanceOverlay; annoyanceExceeding.length;
    overlay.setProps({ layers: layers(), getTooltip: tooltip });
  }

  $: if (workspace === WORKSPACE.MAP && map) setTimeout(() => map.resize(), 20);

  $: if (map) {
    const nextStyle = BASEMAP_STYLES[baseStyle];
    if (nextStyle && nextStyle !== currentStyleUrl) {
      currentStyleUrl = nextStyle;
      map.setStyle(nextStyle);
      map.once("styledata", () => {
        if (overlay) overlay.setProps({ layers: layers(), getTooltip: tooltip });
      });
    }
  }

  function jump(name) {
    if (!map || !VIEWS[name]) return;
    const [lng, lat, zoom] = VIEWS[name];
    map.flyTo({ center: [lng, lat], zoom, speed: 0.85, curve: 1.2 });
  }

  onMount(async () => {
    try {
      syncViewportMode();
      onResize = () => syncViewportMode();
      window.addEventListener("resize", onResize, { passive: true });
      const initialWorkspace = workspaceFromPath(window.location.pathname);
      workspace = initialWorkspace;
      applyWorkspaceTabMeta(initialWorkspace);
      if (initialWorkspace === WORKSPACE.MAP) {
        applyMapStateFromQuery(window.location.search);
      }
      navigateWorkspace(initialWorkspace, true);
      mapQueryReady = true;
      onPopState = () => {
        const nextWorkspace = workspaceFromPath(window.location.pathname);
        workspace = nextWorkspace;
        applyWorkspaceTabMeta(nextWorkspace);
        if (nextWorkspace === WORKSPACE.MAP) {
          applyMapStateFromQuery(window.location.search);
        }
      };
      window.addEventListener("popstate", onPopState);

      const [c, s, m, g] = await Promise.all([
        fetch("/data/il_counties.geojson"),
        fetch("/data/il_sites.geojson"),
        fetch("/data/map_metadata.json"),
        fetch("/data/global_datacenters_registry.geojson"),
      ]);
      if (!c.ok || !s.ok || !m.ok || !g.ok) throw new Error("Failed to load /web/public/data assets.");
      counties = await c.json();
      sites = await s.json();
      metadata = await m.json();
      globalRegistry = await g.json();
      metricSeriesCache = {};
      peerMetricStatsCache = {};
      setPressureWeights(configuredPressureWeights());
      if (!mapZoomCounty && counties?.features?.length) {
        mapZoomCounty = String(counties.features[0]?.properties?.GEOID || "");
      }
      map = new maplibregl.Map({ container: mapEl, style: currentStyleUrl, center: [-89.2, 40.05], zoom: 6.25, attributionControl: true });
      map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
      map.on("load", () => { overlay = new MapboxOverlay({ interleaved: true, layers: layers(), getTooltip: tooltip }); map.addControl(overlay); });
    } catch (e) {
      error = e instanceof Error ? e.message : "Unknown load error.";
    } finally {
      loading = false;
    }
  });

  onDestroy(() => {
    if (onPopState) window.removeEventListener("popstate", onPopState);
    if (onResize) window.removeEventListener("resize", onResize);
    clearTimeout(mapToastTimer);
    clearNarrativeAutoplayTimer();
    if (overlay) overlay.finalize();
    if (map) map.remove();
  });

  $: applyWorkspaceTabMeta(workspace);
</script>

<main class="layout high-contrast" class:home-theme={workspace===WORKSPACE.HOME} class:panel-open={mobilePanelOpen}>
  <button
    class="mobile-nav-toggle"
    type="button"
    on:click={toggleMobilePanel}
    aria-label={mobilePanelOpen ? "Hide workspace sidebar" : "Show workspace sidebar"}
    aria-expanded={mobilePanelOpen}
  >
    {#if mobilePanelOpen}
      <svg class="mobile-nav-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M6 6L18 18M18 6L6 18" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
      </svg>
    {:else}
      <svg class="mobile-nav-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4 7H20M4 12H20M4 17H20" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
      </svg>
    {/if}
  </button>
  {#if mobilePanelOpen}
    <button class="mobile-nav-backdrop" type="button" on:click={closeMobilePanel} aria-label="Close workspace sidebar"></button>
  {/if}
  <aside class="panel">
    <h1>SoReMo '26</h1>
    <p>
      <b>The People v. Hasty AI Development</b>
      <span class="panel-subline">Illinois Data Center Impact Platform</span>
    </p>

    <section class="card">
      <h3>Workspace</h3>
      <button class:active={workspace===WORKSPACE.HOME} on:click={() => openWorkspace(WORKSPACE.HOME)}>Home</button>
      <button class:active={workspace===WORKSPACE.MAP} on:click={() => openWorkspace(WORKSPACE.MAP)}>Illinois Map</button>
      <button class:active={workspace===WORKSPACE.BRIEF} on:click={() => openWorkspace(WORKSPACE.BRIEF)}>County Intelligence Briefing</button>
      <button class:active={workspace===WORKSPACE.STUDIO} on:click={() => openWorkspace(WORKSPACE.STUDIO)}>Impact Scenario Studio</button>
      <button class:active={workspace===WORKSPACE.REGISTRY} on:click={() => openWorkspace(WORKSPACE.REGISTRY)}>Data Center Registry</button>
    </section>

    {#if workspace===WORKSPACE.MAP}
      <section class="card">
        <h3>Scenario</h3>
        <select bind:value={mapScenario}>{#each SCENARIOS as s}<option value={s.key}>{s.label}</option>{/each}</select>
        <label>Basemap
          <select bind:value={baseStyle}>
            {#each Object.entries(BASEMAP_LABELS) as [key, label]}
              <option value={key}>{label}</option>
            {/each}
          </select>
        </label>
      </section>
      <section class="card narrative-card">
        <div class="narrative-head">
          <h3>Layered Narrative</h3>
          <p class="mini-note narrative-intro">Follow a simple 4-step story: where data centers are, current county stress, who may be affected, and the added burden from AI growth.</p>
        </div>
        <label>Narrative step
          <select bind:value={layeredNarrativeStep} on:change={(e) => applyNarrativeStep(e.currentTarget.value, true)}>
            {#each LAYERED_NARRATIVE_STEPS as step}
              <option value={step.key}>{step.label}</option>
            {/each}
          </select>
        </label>
        <div class="narrative-current">
          <div class="narrative-current-title">{LAYERED_NARRATIVE_STEPS.find((x) => x.key === layeredNarrativeStep)?.label || "Step"}</div>
          <p class="mini-note narrative-current-summary">{LAYERED_NARRATIVE_STEPS.find((x) => x.key === layeredNarrativeStep)?.summary || ""}</p>
        </div>
        <label class="narrative-slider">Autoplay interval (seconds)
          <input type="range" min="3" max="12" step="1" bind:value={narrativeAutoplaySeconds}/>
        </label>
        <div class="narrative-status-row">
          <div class="narrative-status-chip"><b>Status</b><span>{narrativeAutoplay ? "Running" : "Paused"}</span></div>
          <div class="narrative-status-chip"><b>Step interval</b><span>{Number(narrativeAutoplaySeconds).toFixed(0)}s</span></div>
        </div>
        <div class="narrative-actions">
          <button class="cta" on:click={startNarrativeAutoplay} disabled={narrativeAutoplay}>Start Autoplay</button>
          <button class="ghost" on:click={() => stopNarrativeAutoplay(true)} disabled={!narrativeAutoplay}>Pause Autoplay</button>
          <button class="ghost" on:click={nextNarrativeStepManual}>Next Step</button>
        </div>
      </section>
      <section class="card">
        <h3>County Layer</h3>
        <select bind:value={countyLayer}>
          {#each countyLayerGroupsForSelect as group}
            <optgroup label={group.label}>
              {#each group.options as opt}
                <option value={opt.key}>{opt.label}</option>
              {/each}
            </optgroup>
          {/each}
        </select>
        <p class="mini-note layer-help">{activeCountyCfg?.help || "Select a county layer to view what each county value represents."}</p>
        <label>Layer opacity
          <input type="range" min="0.2" max="1" step="0.05" bind:value={countyOpacity}/>
        </label>
        {#if countyLayer !== "none" && activeCountyCfg}
          <div class="legend">
            <div class="legend-title">{activeCountyCfg.label}</div>
            <div class="legend-strip">
              {#each activeCountyCfg.colors as c}
                <span style={`background: rgb(${c[0]}, ${c[1]}, ${c[2]})`}></span>
              {/each}
            </div>
            <div class="legend-bins">
              {#each activeLegendEntries as entry}
                <div class="legend-bin">
                  <small class="quantile">{entry.quantile}</small>
                  <small>{entry.rangeLabel}</small>
                </div>
              {/each}
            </div>
            <small class="legend-note">Gray counties indicate missing values.</small>
          </div>
        {/if}
      </section>
      <section class="card">
        <h3>Annoyance Threshold</h3>
        <p class="mini-note">Annoyance Score = AQI level + Water stress + Energy burden + Social vulnerability (equal-weight percentile blend).</p>
        <label>Threshold X (0-100)
          <input type="range" min="0" max="100" step="1" bind:value={annoyanceThreshold}/>
        </label>
        <p class="mini-note"><b>Current threshold:</b> {Math.round(Number(annoyanceThreshold))}</p>
        <label><input type="checkbox" bind:checked={showAnnoyanceOverlay}/> Highlight counties exceeding threshold X</label>
        <div class="chip">Counties >= X: {annoyanceExceeding.length}</div>
        {#if annoyanceExceeding.length}
          <ul class="watchlist">
            {#each annoyanceExceeding.slice(0, 6) as item}
              <li>
                <b>{item.name}</b>
                <span>Annoyance score {fmt(item.score, "score")} (threshold {Math.round(Number(annoyanceThreshold))})</span>
                <small>{item.breakdown.availableCount}/{item.breakdown.totalCount} components available</small>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="mini-note">No counties exceed the current threshold.</p>
        {/if}
      </section>
      <section class="card">
        <h3>Site Layers</h3>
        <label><input type="checkbox" bind:checked={showExisting}/> Existing</label>
        <label><input type="checkbox" bind:checked={showProposed}/> Proposed</label>
        <label><input type="checkbox" bind:checked={showDenied}/> Denied</label>
        <label><input type="checkbox" bind:checked={showInventory}/> Inventory</label>
        <label><input type="checkbox" bind:checked={showRegistry}/> Registry (all known IL)</label>
        <label><input type="checkbox" bind:checked={showOutlines}/> County outlines</label>
        <p class="mini-note">Registry points are reference-only and are excluded from pressure scoring formulas.</p>
        <label>Point size
          <input type="range" min="4" max="16" step="1" bind:value={siteRadius}/>
        </label>
      </section>
      <section class="card">
        <h3>County Explorer</h3>
        <label>Zoom to county
          <select bind:value={mapZoomCounty} on:change={() => zoomToCounty(mapZoomCounty)} disabled={mapCountyOptions.length === 0}>
            <option value="" disabled>Select a county</option>
            {#each mapCountyOptions as c}
              <option value={c.geoid}>{c.name}</option>
            {/each}
            {#if mapCountyOptions.length === 0}
              <option value="">No counties loaded</option>
            {/if}
          </select>
        </label>
        <button class="ghost" on:click={() => zoomToCounty(mapZoomCounty)} disabled={!mapZoomCounty}>Zoom to County</button>
        {#if mapCountyOptions.length === 0}
          <p class="mini-note">County boundaries are still loading.</p>
        {/if}
      </section>
      <section class="card assumption-lab">
        <h3>Assumption Lab</h3>
        <p class="mini-note">
          Tune how much each site status contributes to the pressure score. Changes apply to map pressure fill,
          county briefing, and scenario studio outputs.
        </p>
        <label>Quick profile
          <select bind:value={selectedPressureProfile} on:change={(e) => applyPressureProfile(e.currentTarget.value)}>
            <option value="baseline">{PRESSURE_WEIGHT_PROFILES.baseline.label}</option>
            <option value="cautious">{PRESSURE_WEIGHT_PROFILES.cautious.label}</option>
            <option value="growthHeavy">{PRESSURE_WEIGHT_PROFILES.growthHeavy.label}</option>
            <option value="custom">Custom manual setup</option>
          </select>
        </label>
        <label>Existing sites
          <div class="weight-control">
            <input type="range" min={PRESSURE_WEIGHT_LIMITS.min} max={PRESSURE_WEIGHT_LIMITS.max} step={PRESSURE_WEIGHT_LIMITS.step} bind:value={pressureWeightExisting}/>
            <input class="weight-number" type="number" min={PRESSURE_WEIGHT_LIMITS.min} max={PRESSURE_WEIGHT_LIMITS.max} step={PRESSURE_WEIGHT_LIMITS.step} bind:value={pressureWeightExisting}/>
          </div>
        </label>
        <label>Proposed sites
          <div class="weight-control">
            <input type="range" min={PRESSURE_WEIGHT_LIMITS.min} max={PRESSURE_WEIGHT_LIMITS.max} step={PRESSURE_WEIGHT_LIMITS.step} bind:value={pressureWeightProposed}/>
            <input class="weight-number" type="number" min={PRESSURE_WEIGHT_LIMITS.min} max={PRESSURE_WEIGHT_LIMITS.max} step={PRESSURE_WEIGHT_LIMITS.step} bind:value={pressureWeightProposed}/>
          </div>
        </label>
        <label>Inventory sites
          <div class="weight-control">
            <input type="range" min={PRESSURE_WEIGHT_LIMITS.min} max={PRESSURE_WEIGHT_LIMITS.max} step={PRESSURE_WEIGHT_LIMITS.step} bind:value={pressureWeightInventory}/>
            <input class="weight-number" type="number" min={PRESSURE_WEIGHT_LIMITS.min} max={PRESSURE_WEIGHT_LIMITS.max} step={PRESSURE_WEIGHT_LIMITS.step} bind:value={pressureWeightInventory}/>
          </div>
        </label>
        <label>Denied sites
          <div class="weight-control">
            <input type="range" min={PRESSURE_WEIGHT_LIMITS.min} max={PRESSURE_WEIGHT_LIMITS.max} step={PRESSURE_WEIGHT_LIMITS.step} bind:value={pressureWeightDenied}/>
            <input class="weight-number" type="number" min={PRESSURE_WEIGHT_LIMITS.min} max={PRESSURE_WEIGHT_LIMITS.max} step={PRESSURE_WEIGHT_LIMITS.step} bind:value={pressureWeightDenied}/>
          </div>
        </label>
        <p class="equation-mini">
          <b>Live formula:</b> Existing x {weightFmt(pressureWeightExisting)} + Proposed x {weightFmt(pressureWeightProposed)} +
          Inventory x {weightFmt(pressureWeightInventory)} + Denied x {weightFmt(pressureWeightDenied)}
        </p>
        <div class="assumption-guide">
          <p><b>How to choose weights</b></p>
          <ol>
            <li>Start with <b>Recommended baseline</b>.</li>
            <li>Increase <b>Proposed</b> if you expect approvals/construction soon; reduce it for conservative planning.</li>
            <li>Keep <b>Existing</b> near 1.0 for current footprint pressure unless operations are unusually intensive.</li>
            <li>Keep <b>Inventory</b> and <b>Denied</b> lower when project certainty is low.</li>
            <li>After edits, click <b>Generate County Brief</b> or <b>Run Simulation</b> to compare outcomes.</li>
          </ol>
        </div>
        <button class="ghost weight-reset" on:click={resetPressureWeights}>Reset to Recommended Baseline</button>
      </section>
      <section class="card">
        <h3>County Watchlist Alerts</h3>
        <p class="mini-note">Flags counties with high planned pressure, large pressure increase, or pressure-vulnerability overlap.</p>
        <div class="mini-note watchlist-help">
          <span class="info-pill">i</span>
          <div class="watchlist-help-lines">
            <p class="formula-line"><b>Planned pressure = (Existing x {weightFmt(pressureWeightExisting)}) + (Proposed x {weightFmt(pressureWeightProposed)}) + (Inventory x {weightFmt(pressureWeightInventory)}) + (Denied x {weightFmt(pressureWeightDenied)})</b></p>
            <p class="formula-line"><b>Current pressure = (Existing x {weightFmt(pressureWeightExisting)})</b></p>
            <p class="formula-line"><b>Delta = Planned pressure - Current pressure</b></p>
            <p class="formula-line">Larger positive delta means larger projected increase.</p>
          </div>
        </div>
        <p class="mini-note"><b>Mode:</b> {watchlistModeLabel}</p>
        <p class="mini-note"><b>Weights:</b> E {weightFmt(pressureWeightExisting)} | P {weightFmt(pressureWeightProposed)} | I {weightFmt(pressureWeightInventory)} | D {weightFmt(pressureWeightDenied)}</p>
        {#if countyWatchlist.length}
          <ul class="watchlist">
            {#each countyWatchlist.slice(0, 6) as item}
              <li>
                <b>{item.name}</b>
                <span>Planned {item.planned} | Current {item.current} | Delta {item.delta >= 0 ? "+" : ""}{item.delta}</span>
                <small>{item.reasons[0]}</small>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="mini-note">{watchlistEmptyMessage || "No counties currently trigger watchlist thresholds."}</p>
          {#if watchlistFallback.length}
            <ul class="watchlist fallback">
              {#each watchlistFallback as item}
                <li>
                  <b>{item.name}</b>
                  <span>Planned {item.planned} | Current {item.current} | Delta {item.delta >= 0 ? "+" : ""}{item.delta}</span>
                  <small>Top pressure county under current assumptions</small>
                </li>
              {/each}
            </ul>
          {/if}
        {/if}
      </section>
      <section class="card">
        <h3>Jump Views</h3>
        {#each Object.keys(VIEWS) as v}<button on:click={() => jump(v)}>{v}</button>{/each}
      </section>
      {#if selectedCounty}
        <section class="card selected">
          <h3>Selected County</h3>
          <p><b>{selectedCounty.County_Name || selectedCounty.NAME}</b></p>
          <p>Layer value: {fmt(selectedCountyLayerValue, activeCountyCfg?.unit || "")}</p>
          <p>Pressure: {fmt(pressureScoreForCounty(selectedCounty.GEOID, mapScenario), "score")}</p>
          <p>Annoyance score: {fmt(annoyanceByGeoid.get(String(selectedCounty.GEOID || ""))?.score, "score")} (threshold {Math.round(Number(annoyanceThreshold))})</p>
          <p>Heat: index {fmt(selectedCounty.Heat_Climate_Stress_Index, "score")} | FEMA risk {fmt(selectedCounty.HWAV_RISKS, "score")}</p>
          <p>NOAA: {fmt(selectedCounty.NOAA_CDD_Recent5yr, "cdd")} | summer Tmax {fmt(selectedCounty.NOAA_Tmax_Summer_Recent5yr_F, "degf")}</p>
          <p>Grid mix: clean {fmt(selectedCounty.Grid_Clean_Share_Pct, "pct")} | fossil {fmt(selectedCounty.Grid_Fossil_Share_Pct, "pct")}</p>
          <p>Grid carbon: {fmt(selectedCounty.Grid_Carbon_Intensity_kg_per_MWh, "kgco2")} | 100 MW est: {fmt(selectedCounty.Grid_Est_CO2_kt_per_100MWyr, "ktco2")}</p>
          {#if selectedCountyQuality}
            <p>Data quality: <b>{selectedCountyQuality.confidence}</b> ({selectedCountyQuality.available}/{selectedCountyQuality.total}, {selectedCountyQuality.coveragePct}%)</p>
          {/if}
          {#if watchlistByGeoid.get(String(selectedCounty.GEOID || ""))}
            <p class="alert-note">Watchlist: {watchlistByGeoid.get(String(selectedCounty.GEOID || "")).reasons[0]}</p>
          {/if}
          {#if selectedCountyIndicators.length}
            <p><b>Top indicators</b></p>
            <ul class="indicator-list">
              {#each selectedCountyIndicators as item}
                {#if item.missing}
                  <li><b>{item.label}:</b> {item.reason}</li>
                {:else}
                  <li><b>{item.label}:</b> {item.valueLabel} ({item.band}{#if Number.isFinite(Number(item.percentile))}, {item.percentile}th pct{/if})</li>
                {/if}
              {/each}
            </ul>
          {/if}
          <button class="ghost" on:click={() => (selectedCounty = null)}>Clear Selection</button>
        </section>
      {/if}
      {#if selectedSite}
        <section class="card selected">
          <h3>Selected Site</h3>
          <p><b>{selectedSite.name}</b></p>
          <p>Status: {selectedSite.status_class}</p>
          <p>Operator: {selectedSite.operator || "N/A"}</p>
          <p>County: {selectedSite.County_Name || "N/A"}</p>
          <p>Source: {selectedSite.data_source || "N/A"}</p>
          <button class="ghost" on:click={() => (selectedSite = null)}>Clear Selection</button>
        </section>
      {/if}
    {/if}

    {#if workspace===WORKSPACE.BRIEF}
      <section class="card">
        <h3>Brief Settings</h3>
        <label>Scenario
          <select bind:value={briefScenario}>{#each SCENARIOS as s}<option value={s.key}>{s.label}</option>{/each}</select>
        </label>
        <label>Primary focus
          <select bind:value={briefFocus}>{#each FOCUS as f}<option value={f}>{f}</option>{/each}</select>
        </label>
        <label><input type="checkbox" bind:checked={briefOnlyWithSites}/> Show only counties with site records</label>
        <label>County
          <select bind:value={briefCounty} disabled={briefOptions.length === 0}>
            {#if briefOptions.length === 0}
              <option value="">No counties available</option>
            {:else}
              {#each briefOptions as c}<option value={c.geoid}>{c.name} ({c.count})</option>{/each}
            {/if}
          </select>
        </label>
        {#if briefOptions.length === 0}
          <p class="mini-note">No counties match this filter. Uncheck county-only filtering or use planned scenario.</p>
        {/if}
        <button class="cta brief-run" on:click={buildBrief} disabled={!canBuildBrief}>Generate County Brief</button>
      </section>
    {/if}

    {#if workspace===WORKSPACE.STUDIO}
      <section class="card">
        <h3>Studio Controls</h3>
        <label>Base scenario
          <select bind:value={studioScenario}>{#each SCENARIOS as s}<option value={s.key}>{s.label}</option>{/each}</select>
        </label>
        <label><input type="checkbox" bind:checked={studioOnlyWithSites}/> Show only counties with site records</label>
        <label>County
          <select bind:value={studioCounty} disabled={studioOptions.length === 0}>
            {#if studioOptions.length === 0}
              <option value="">No counties available</option>
            {:else}
              {#each studioOptions as c}<option value={c.geoid}>{c.name} ({c.count})</option>{/each}
            {/if}
          </select>
        </label>
        <label>Retire existing<input type="number" min="0" bind:value={retireExisting}/></label>
        <label>Add proposed<input type="number" min="0" bind:value={addProposed}/></label>
        <label>Cancel proposed<input type="number" min="0" bind:value={cancelProposed}/></label>
        <label>Add inventory<input type="number" min="0" bind:value={addInventory}/></label>
        <label>Remove inventory<input type="number" min="0" bind:value={removeInventory}/></label>
        <label>Add denied<input type="number" min="0" bind:value={addDenied}/></label>
        {#if studioOptions.length === 0}
          <p class="mini-note">No counties available for this setup. Adjust filters or scenario.</p>
        {/if}
        <button class="cta studio-run" on:click={runStudio} disabled={!canRunStudio}>Run Simulation</button>
      </section>
    {/if}
  </aside>

  <section
    class="content"
    role="main"
    aria-label="Workspace content"
    bind:this={contentEl}
    on:mousemove={handleAmbientMove}
    on:mouseleave={resetAmbient}
    style={`--ambient-x:${ambientX}%; --ambient-y:${ambientY}%`}
  >
    <div
      class="ambient-layer"
      class:home={workspace===WORKSPACE.HOME}
      class:briefbg={workspace===WORKSPACE.BRIEF}
      class:registrybg={workspace===WORKSPACE.REGISTRY}
      class:studiobg={workspace===WORKSPACE.STUDIO}
      aria-hidden="true"
    >
      <span class="ambient-orb orb-a"></span>
      <span class="ambient-orb orb-b"></span>
      <span class="ambient-orb orb-c"></span>
      <span class="ambient-cursor"></span>
      <span class="ambient-sheen"></span>
    </div>

    {#if loading}<div class="status">Loading...</div>{/if}
    {#if error}<div class="status error">{error}</div>{/if}
    {#if routeLoadError}<div class="status error route">{routeLoadError}</div>{/if}
    {#if mapToast && workspace===WORKSPACE.MAP}<div class="status toast">{mapToast}</div>{/if}

    <section class:active={workspace===WORKSPACE.HOME} class="workspace pad home-workspace">
      <div class="home-project-bg" aria-hidden="true">
        <span class="home-bg-mesh"></span>
        <span class="home-bg-wave wave-1"></span>
        <span class="home-bg-wave wave-2"></span>
        <span class="home-bg-wave wave-3"></span>
        <span class="home-bg-core"></span>
        <span class="home-bg-dot dot-1"></span>
        <span class="home-bg-dot dot-2"></span>
        <span class="home-bg-dot dot-3"></span>
        <span class="home-bg-dot dot-4"></span>
        <span class="home-bg-dot dot-5"></span>
        <span class="home-bg-dot dot-6"></span>
        <span class="home-bg-dot dot-7"></span>
      </div>
      <div class="home-hero">
        <div class="home-badge">SoReMo '26</div>
        <h2>The People v. Hasty AI Development</h2>
        <p class="home-subtitle">
          Illinois Data Center Impact Platform for mapping infrastructure growth and interpreting community, environmental,
          and energy burden signals with explainable analytics.
        </p>
      </div>

      <div class="home-intro">
        <div class="home-info-card">
          <h4>What You Can Do</h4>
          <ul>
            <li>Inspect county-level risk and burden layers on an interactive Illinois map.</li>
            <li>Generate county-specific intelligence briefs with evidence references.</li>
            <li>Run what-if scenario simulations and export notes for presentations.</li>
            <li>Explore expanded Illinois and global data-center registry records.</li>
          </ul>
        </div>
        <div class="home-info-card">
          <h4>Suggested Flow</h4>
          <ul>
            <li>Start with <b>Illinois Map</b> to identify concentration and hotspot counties.</li>
            <li>Open <b>County Intelligence Briefing</b> for county narrative and exportable brief files.</li>
            <li>Use <b>Impact Scenario Studio</b> to test policy/project changes before decisions.</li>
            <li>Open <b>Data Center Registry</b> to browse broader US/global facility coverage.</li>
          </ul>
        </div>
      </div>

      <h3 class="home-workspace-title">Open a Workspace</h3>
      <div class="home-grid">
        <button class="home-card" on:click={() => openWorkspace(WORKSPACE.MAP)}>
          <div class="home-card-top">
            <b>Illinois Map</b>
          </div>
          <span>Interactive county layers, scenario toggles, hotspots, and county zoom explorer.</span>
          <em>Explore spatial patterns</em>
        </button>
        <button class="home-card" on:click={() => openWorkspace(WORKSPACE.BRIEF)}>
          <div class="home-card-top">
            <b>County Intelligence Briefing</b>
          </div>
          <span>Generate county briefs with scenario context and export .md/.pdf outputs.</span>
          <em>Create narrative evidence briefs</em>
        </button>
        <button class="home-card" on:click={() => openWorkspace(WORKSPACE.STUDIO)}>
          <div class="home-card-top">
            <b>Impact Scenario Studio</b>
          </div>
          <span>Run what-if simulations and compare projected pressure before policy decisions.</span>
          <em>Test adjustments and tradeoffs</em>
        </button>
        <button class="home-card" on:click={() => openWorkspace(WORKSPACE.REGISTRY)}>
          <div class="home-card-top">
            <b>Data Center Registry</b>
          </div>
          <span>Browse expanded Illinois and global data-center records with search and provider filters.</span>
          <em>Investigate wider infrastructure footprint</em>
        </button>
      </div>
    </section>

    <section class:active={workspace===WORKSPACE.MAP} class="workspace map-workspace">
      <div bind:this={mapEl} class="map"></div>
      <div class="map-ambient" aria-hidden="true">
        <span class="map-ring ring-a"></span>
        <span class="map-ring ring-b"></span>
        <span class="map-sweep"></span>
      </div>
    </section>

    <section class:active={workspace===WORKSPACE.BRIEF} class="workspace pad">
      {#if BriefWorkspaceComponent}
        <svelte:component
          this={BriefWorkspaceComponent}
          briefData={briefData}
          briefFocus={briefFocus}
          canGenerate={canBuildBrief}
          onDownloadMarkdown={downloadBriefMarkdown}
          onDownloadPdf={downloadBriefPdf}
        />
      {:else}
        <p>Loading briefing workspace...</p>
      {/if}
    </section>

    <section class:active={workspace===WORKSPACE.STUDIO} class="workspace pad">
      {#if StudioWorkspaceComponent}
        <svelte:component
          this={StudioWorkspaceComponent}
          studioData={studioData}
          canRun={canRunStudio}
          onDownloadMarkdown={downloadStudioMarkdown}
          onDownloadPdf={downloadStudioPdf}
        />
      {:else}
        <p>Loading studio workspace...</p>
      {/if}
    </section>

    <section class:active={workspace===WORKSPACE.REGISTRY} class="workspace pad registry-workspace">
      {#if RegistryWorkspaceComponent}
        <svelte:component
          this={RegistryWorkspaceComponent}
          globalRegistry={globalRegistry}
          registryMeta={metadata?.datacenter_registry}
          active={workspace===WORKSPACE.REGISTRY}
        />
      {:else}
        <p>Loading registry workspace...</p>
      {/if}
    </section>
  </section>
</main>

<style>
  :global(:root) {
    --font-sans: "Plus Jakarta Sans", "Space Grotesk", sans-serif;
    --text-main: #0f223a;
    --text-soft: #35587f;
    --panel-border: #c5d5ea;
    --card-border: #c5d6eb;
    --card-bg: rgba(255, 255, 255, 0.92);
    --primary-strong: #0d2744;
    --primary-mid: #0f3054;
    --accent-bg: linear-gradient(135deg, #1d76f5 0%, #1559b9 100%);
    --cta-bg: linear-gradient(135deg, #0aa5a9 0%, #1273c5 100%);
    --ghost-bg: #f3f8ff;
    --status-bg: #10243d;
    --status-error: #9a1d1d;
    --status-toast: #0f7f87;
  }

  :global(html),
  :global(body),
  :global(#app) {
    height: 100%;
    min-height: 100%;
    overflow-x: hidden;
  }

  :global(body) {
    margin: 0;
    font-family: var(--font-sans);
    color: var(--text-main);
    background: #edf4fd;
    overflow: hidden;
  }

  .layout {
    height: 100vh;
    height: 100dvh;
    min-height: 100vh;
    min-height: 100dvh;
    width: 100%;
    max-width: 100%;
    display: grid;
    grid-template-columns: minmax(300px, 370px) minmax(0, 1fr);
    background: #edf4fd;
    align-items: stretch;
    position: relative;
    overflow: hidden;
  }

  .layout > * {
    position: relative;
    z-index: 1;
  }

  .mobile-nav-toggle,
  .mobile-nav-backdrop {
    display: none;
  }

  .mobile-nav-toggle {
    align-items: center;
    justify-content: center;
    position: fixed;
    top: 12px;
    left: 12px;
    z-index: 42;
    width: 42px;
    height: 42px;
    padding: 0;
    border: 1px solid #b6cdea;
    border-radius: 12px;
    background: rgba(245, 250, 255, 0.92);
    color: #133a63;
    box-shadow: 0 4px 14px rgba(18, 58, 99, 0.14);
    backdrop-filter: blur(5px);
    cursor: pointer;
  }

  .mobile-nav-toggle:hover {
    background: rgba(239, 247, 255, 0.96);
  }

  .mobile-nav-toggle:active {
    transform: translateY(1px);
  }

  .mobile-nav-icon {
    width: 20px;
    height: 20px;
    color: #114c7a;
  }

  .layout.home-theme {
    background:
      radial-gradient(circle at 12% 18%, rgba(30, 138, 205, 0.14) 0%, rgba(30, 138, 205, 0) 30%),
      radial-gradient(circle at 24% 74%, rgba(27, 175, 165, 0.12) 0%, rgba(27, 175, 165, 0) 34%),
      radial-gradient(circle at 78% 24%, rgba(35, 164, 168, 0.14) 0%, rgba(35, 164, 168, 0) 34%),
      radial-gradient(circle at 82% 78%, rgba(229, 165, 82, 0.12) 0%, rgba(229, 165, 82, 0) 38%),
      linear-gradient(140deg, #eaf2fb 0%, #edf4fd 42%, #e8f2f8 100%);
  }

  .layout.home-theme::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
      repeating-linear-gradient(
        -9deg,
        rgba(25, 101, 162, 0.03) 0px,
        rgba(25, 101, 162, 0.03) 1px,
        transparent 1px,
        transparent 48px
      );
    opacity: 0.55;
    z-index: 0;
  }

  .panel {
    overflow-y: auto;
    overflow-x: hidden;
    padding: 18px;
    background-color: #edf4fd;
    background-image: none;
    border-right: 1px solid var(--panel-border);
    box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.6);
    min-height: 0;
    position: relative;
    min-width: 0;
  }

  .layout.home-theme .panel {
    background-color: rgba(233, 242, 252, 0.72);
    backdrop-filter: blur(1.2px);
  }

  .layout.home-theme .panel::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    background:
      radial-gradient(circle at 18% 14%, rgba(27, 141, 205, 0.16) 0%, rgba(27, 141, 205, 0) 38%),
      radial-gradient(circle at 72% 86%, rgba(30, 175, 163, 0.12) 0%, rgba(30, 175, 163, 0) 44%),
      repeating-linear-gradient(
        -14deg,
        rgba(28, 108, 168, 0.04) 0px,
        rgba(28, 108, 168, 0.04) 1px,
        transparent 1px,
        transparent 42px
      );
    opacity: 0.85;
  }

  .layout.home-theme .panel > * {
    position: relative;
    z-index: 1;
  }

  .layout.home-theme .panel .card {
    background: rgba(255, 255, 255, 0.76);
    backdrop-filter: blur(1.2px);
    border-color: rgba(147, 183, 220, 0.7);
  }

  .panel h1 {
    margin: 0;
    font-size: clamp(40px, 4.2vw, 52px);
    line-height: 0.9;
    letter-spacing: -0.03em;
    font-weight: 800;
    color: var(--primary-strong);
    white-space: nowrap;
  }

  .panel p {
    margin: 10px 0 0;
    color: var(--text-soft);
    font-size: clamp(14px, 1.3vw, 15px);
    line-height: 1.32;
  }

  .panel p b {
    display: block;
    margin-bottom: 2px;
  }

  .panel-subline {
    display: block;
    margin-top: 8px;
    line-height: 1.28;
  }

  .card {
    margin-top: 14px;
    padding: 14px;
    border: 1px solid var(--card-border);
    border-radius: 16px;
    background: var(--card-bg);
    box-shadow: 0 6px 20px rgba(30, 67, 116, 0.08);
  }

  .card h3 {
    margin: 0 0 10px;
    color: var(--primary-mid);
    font-size: clamp(22px, 2.6vw, 28px);
    line-height: 0.98;
    letter-spacing: -0.015em;
  }

  .card label {
    display: block;
    font-size: 13px;
    margin-top: 9px;
    color: var(--text-soft);
    font-weight: 600;
    overflow: hidden;
  }

  .card select,
  .card input[type="number"],
  .card input[type="range"],
  .card button {
    width: 100%;
    margin-top: 6px;
    padding: 9px 12px;
    border: 1px solid #bfd1e8;
    border-radius: 10px;
    background: #ffffff;
    color: #122b48;
    font-family: inherit;
    font-size: 14px;
    box-sizing: border-box;
  }

  .card input[type="checkbox"] {
    width: auto;
    margin: 0 8px 0 0;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: none;
    vertical-align: middle;
  }

  .card input[type="range"] {
    padding: 0;
    margin-top: 8px;
  }

  .card button {
    cursor: pointer;
    text-align: left;
    font-weight: 600;
    line-height: 1.25;
    transition: transform 120ms ease, background 120ms ease, border-color 120ms ease;
  }

  .card button:hover {
    transform: translateY(-1px);
    background: #f1f7ff;
    border-color: #99b8dd;
  }

  .card button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
    transform: none;
  }

  .card select:disabled,
  .card input:disabled {
    opacity: 0.65;
    cursor: not-allowed;
  }

  .card button.active {
    background: var(--accent-bg);
    color: #fff;
    border-color: #1559b9;
  }

  .cta {
    background: var(--cta-bg) !important;
    color: #fff !important;
    border-color: #1273c5 !important;
    font-weight: 700 !important;
    text-align: center !important;
  }

  .ghost {
    background: var(--ghost-bg) !important;
    border-color: #b8cbe5 !important;
    color: #173b62 !important;
    text-align: center !important;
  }

  .layout.high-contrast {
    --text-main: #081a2f;
    --text-soft: #1a4873;
    --panel-border: #97b9de;
    --card-border: #9fc0e5;
    --card-bg: rgba(255, 255, 255, 0.98);
    --ghost-bg: #e5f0ff;
    --status-bg: #091d35;
    --status-toast: #056f84;
    background: #dce9fb;
  }

  .layout.high-contrast .panel {
    background-color: #e6f0ff;
    box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.9);
  }

  .layout.high-contrast .card {
    box-shadow: 0 8px 24px rgba(8, 52, 106, 0.16);
    border-color: #a5c2e4;
  }

  .layout.high-contrast .ambient-layer::after {
    opacity: 0.7;
  }

  .layout.high-contrast .ambient-layer.home {
    background:
      radial-gradient(circle at var(--ambient-x) var(--ambient-y), rgba(16, 121, 213, 0.4), transparent 38%),
      radial-gradient(circle at 12% 24%, rgba(28, 169, 158, 0.36), transparent 34%),
      radial-gradient(circle at 84% 78%, rgba(237, 153, 64, 0.32), transparent 34%),
      linear-gradient(160deg, #deecff 0%, #ebf5ff 56%, #dcf1f9 100%);
  }

  .layout.high-contrast .ambient-layer.briefbg {
    background:
      radial-gradient(circle at var(--ambient-x) var(--ambient-y), rgba(19, 114, 202, 0.38), transparent 40%),
      radial-gradient(circle at 82% 18%, rgba(18, 166, 160, 0.34), transparent 36%),
      repeating-linear-gradient(
        0deg,
        rgba(21, 64, 112, 0.09) 0px,
        rgba(21, 64, 112, 0.09) 1px,
        transparent 1px,
        transparent 18px
      ),
      linear-gradient(180deg, #e4f0ff 0%, #d7e8ff 100%);
  }

  .layout.high-contrast .ambient-layer.registrybg {
    background:
      radial-gradient(circle at 84% 14%, rgba(80, 170, 216, 0.2), transparent 34%),
      linear-gradient(180deg, #eaf3ff 0%, #e6effc 100%);
  }

  .layout.high-contrast .ambient-layer.registrybg::after {
    opacity: 0.16;
    animation: none;
  }

  .layout.high-contrast .ambient-layer.studiobg {
    background:
      radial-gradient(circle at var(--ambient-x) var(--ambient-y), rgba(18, 170, 173, 0.4), transparent 40%),
      radial-gradient(circle at 80% 80%, rgba(26, 100, 201, 0.3), transparent 36%),
      linear-gradient(135deg, rgba(22, 108, 210, 0.2) 0%, transparent 48%),
      linear-gradient(180deg, #deebff 0%, #d3e2fb 100%);
  }

  .layout.high-contrast .ambient-orb {
    opacity: 0.95;
    filter: none;
  }

  .layout.high-contrast .ambient-cursor {
    background: radial-gradient(circle, rgba(255, 255, 255, 0.74) 0%, rgba(255, 255, 255, 0) 67%);
  }

  .layout.high-contrast .map-ring {
    border-color: rgba(9, 120, 190, 0.75);
  }

  .layout.high-contrast .map-ring.ring-b {
    border-color: rgba(0, 160, 156, 0.62);
  }

  .layout.high-contrast .map-sweep {
    background: linear-gradient(90deg, rgba(255, 255, 255, 0) 0%, rgba(116, 222, 255, 0.34) 50%, rgba(255, 255, 255, 0) 100%);
  }

  .layout.high-contrast .pad {
    background:
      radial-gradient(circle at 80% 10%, rgba(194, 228, 255, 0.36), transparent 35%),
      rgba(238, 246, 255, 0.78);
    backdrop-filter: blur(1.6px);
  }

  .layout.high-contrast .home-project-bg .home-bg-mesh {
    opacity: 1;
    filter: saturate(145%);
  }

  .layout.high-contrast .home-project-bg .home-bg-wave {
    opacity: 0.92;
    filter: drop-shadow(0 0 10px rgba(10, 128, 196, 0.46));
  }

  .layout.high-contrast .home-project-bg .home-bg-core {
    opacity: 1;
  }

  .layout.high-contrast .home-project-bg .home-bg-dot {
    box-shadow: 0 0 0 10px rgba(17, 130, 197, 0.2), 0 0 28px rgba(17, 130, 197, 0.68);
  }

  .studio-run {
    margin-top: 14px !important;
  }

  .brief-run {
    margin-top: 14px !important;
  }

  .assumption-lab .mini-note {
    margin-top: 0;
  }

  .weight-control {
    margin-top: 6px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 82px;
    gap: 8px;
    align-items: center;
  }

  .weight-control input[type="range"] {
    width: 100%;
    min-width: 0;
  }

  .weight-control .weight-number {
    margin-top: 0;
    text-align: center;
    font-weight: 700;
    padding: 8px 6px;
  }

  .equation-mini {
    margin: 10px 0 0;
    font-size: 12px;
    line-height: 1.45;
    color: #214a75;
  }

  .assumption-guide {
    margin-top: 10px;
    border: 1px dashed #bcd3ee;
    border-radius: 10px;
    background: #f7fbff;
    padding: 8px 10px;
  }

  .assumption-guide p {
    margin: 0 0 4px;
    font-size: 12px;
    color: #143a63;
  }

  .assumption-guide ol {
    margin: 0;
    padding-left: 18px;
    display: grid;
    gap: 3px;
    color: #2c547d;
    font-size: 12px;
    line-height: 1.35;
  }

  .weight-reset {
    margin-top: 16px;
    text-align: center !important;
  }

  .legend {
    margin-top: 10px;
    padding: 10px;
    border-radius: 10px;
    background: #f8fbff;
    border: 1px solid #d6e3f4;
    overflow: hidden;
  }

  .legend-title {
    font-size: 12px;
    font-weight: 700;
    color: #2a4f78;
    margin-bottom: 6px;
  }

  .legend-strip {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    border-radius: 999px;
    overflow: hidden;
    border: 1px solid #cedcf0;
    width: 100%;
    box-sizing: border-box;
  }

  .legend-strip span {
    height: 10px;
  }

  .legend-bins {
    margin-top: 5px;
    display: grid;
    grid-template-columns: 1fr;
    color: #3c5f86;
    gap: 8px;
    overflow: hidden;
  }

  .legend-bin {
    display: flex;
    justify-content: space-between;
    gap: 10px;
  }

  .legend-bin small {
    white-space: nowrap;
  }

  .legend-bin .quantile {
    font-weight: 700;
  }

  .legend-note {
    margin-top: 6px;
    display: block;
    color: #4f7197;
  }

  .mini-note {
    margin: 8px 0 0;
    color: #4d6f95;
    font-size: 12px;
    line-height: 1.35;
  }

  .layer-help {
    margin-top: 8px;
    padding: 7px 8px;
    border-radius: 8px;
    background: #f7fbff;
    border: 1px solid #d3e3f5;
    color: #355d86;
  }

  .narrative-card {
    display: grid;
    gap: 12px;
  }

  .narrative-head {
    display: grid;
    gap: 4px;
  }

  .narrative-head h3 {
    margin: 0;
  }

  .narrative-card label {
    margin-top: 0;
  }

  .narrative-intro {
    margin: 0;
    font-size: 12.5px;
    line-height: 1.32;
  }

  .narrative-current {
    margin-top: 12px;
    padding: 10px 11px 9px;
    border: 1px solid #cfe0f3;
    border-radius: 10px;
    background: #f7fbff;
    display: grid;
    gap: 1px;
  }

  .narrative-current-title {
    color: #173f6b;
    font-weight: 800;
    font-size: 14px;
    line-height: 1.28;
    letter-spacing: -0.01em;
    margin: 0;
    padding-bottom: 2px;
    border-bottom: 1px solid #d8e7f7;
  }

  .narrative-current-summary {
    margin: 0;
    padding-top: 0;
  }

  .narrative-slider {
    margin-top: 0;
  }

  .narrative-status-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .narrative-status-chip {
    border: 1px solid #cfe0f3;
    border-radius: 10px;
    background: #f7fbff;
    padding: 7px 8px;
    display: grid;
    gap: 2px;
    color: #335982;
  }

  .narrative-status-chip b {
    font-size: 12px;
    color: #1c4a79;
  }

  .narrative-status-chip span {
    font-size: 13px;
    font-weight: 700;
    color: #193f68;
  }

  .narrative-actions {
    margin-top: 4px;
    display: grid;
    gap: 7px;
  }

  .narrative-actions button {
    text-align: center !important;
  }

  .watchlist-help {
    margin-top: 6px;
    padding: 7px 8px;
    border-radius: 8px;
    border: 1px dashed #bfd3ec;
    background: #f6fbff;
    color: #365d86;
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }

  .info-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 15px;
    height: 15px;
    border-radius: 999px;
    background: #dceeff;
    color: #1f4f82;
    font-size: 10px;
    font-weight: 700;
    margin-top: 1px;
    flex: 0 0 auto;
  }

  .watchlist-help-lines {
    min-width: 0;
  }

  .watchlist-help-lines p {
    margin: 0;
  }

  .watchlist-help-lines p + p {
    margin-top: 4px;
  }

  .watchlist-help .formula-line {
    font-family: "Space Grotesk", "Plus Jakarta Sans", sans-serif;
    color: #244f79;
  }

  .watchlist {
    margin: 8px 0 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 8px;
  }

  .watchlist li {
    border: 1px solid #d5e2f3;
    border-radius: 10px;
    padding: 8px;
    background: #f8fbff;
    display: grid;
    gap: 3px;
  }

  .watchlist b {
    color: #173f6b;
    font-size: 13px;
  }

  .watchlist span {
    color: #2f577f;
    font-size: 12px;
  }

  .watchlist small {
    color: #8b4a00;
    font-size: 11px;
  }

  .watchlist.fallback li small {
    color: #2f5a83;
  }

  .chip {
    margin-top: 10px;
    display: inline-block;
    font-size: 12px;
    font-weight: 700;
    background: #e9f3ff;
    color: #1b4f86;
    border: 1px solid #c2daf5;
    border-radius: 999px;
    padding: 4px 10px;
  }

  .selected p {
    margin: 6px 0;
    font-size: 13px;
    color: #2a4c73;
  }

  .indicator-list {
    margin: 6px 0 10px 16px;
    padding: 0;
    color: #2a4c73;
    font-size: 12px;
  }

  .indicator-list li {
    margin: 5px 0;
    line-height: 1.35;
  }

  .alert-note {
    color: #8b4a00 !important;
    background: #fff4dd;
    border: 1px solid #f2d8a4;
    border-radius: 8px;
    padding: 6px 8px;
  }

  .content {
    position: relative;
    min-height: 0;
    overflow: hidden;
    isolation: isolate;
    min-width: 0;
  }

  .workspace {
    display: none;
    height: 100%;
    min-width: 0;
  }

  .workspace.active {
    display: block;
    position: relative;
    z-index: 1;
  }

  .ambient-layer {
    position: absolute;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    overflow: hidden;
    opacity: 0;
    transition: opacity 240ms ease;
  }

  .ambient-layer.home,
  .ambient-layer.briefbg,
  .ambient-layer.registrybg,
  .ambient-layer.studiobg {
    opacity: 1;
  }

  .ambient-layer.home {
    background:
      radial-gradient(circle at var(--ambient-x) var(--ambient-y), rgba(31, 145, 204, 0.3), transparent 36%),
      radial-gradient(circle at 12% 24%, rgba(55, 178, 171, 0.28), transparent 34%),
      radial-gradient(circle at 84% 78%, rgba(241, 174, 92, 0.24), transparent 32%),
      linear-gradient(160deg, #e9f2ff 0%, #f2f8ff 56%, #e6f4f9 100%);
  }

  .ambient-layer.briefbg {
    background:
      radial-gradient(circle at var(--ambient-x) var(--ambient-y), rgba(30, 120, 210, 0.28), transparent 38%),
      radial-gradient(circle at 82% 18%, rgba(40, 176, 172, 0.22), transparent 34%),
      repeating-linear-gradient(
        0deg,
        rgba(22, 64, 111, 0.05) 0px,
        rgba(22, 64, 111, 0.05) 1px,
        transparent 1px,
        transparent 20px
      ),
      linear-gradient(180deg, #edf5ff 0%, #e3eeff 100%);
  }

  .ambient-layer.studiobg {
    background:
      radial-gradient(circle at var(--ambient-x) var(--ambient-y), rgba(37, 170, 175, 0.32), transparent 38%),
      radial-gradient(circle at 80% 80%, rgba(35, 118, 210, 0.2), transparent 34%),
      linear-gradient(135deg, rgba(25, 115, 210, 0.12) 0%, transparent 46%),
      linear-gradient(180deg, #eaf3ff 0%, #e1ebfb 100%);
  }

  .ambient-layer.registrybg {
    background:
      radial-gradient(circle at 80% 12%, rgba(118, 190, 229, 0.17), transparent 34%),
      radial-gradient(circle at 18% 84%, rgba(130, 178, 228, 0.1), transparent 38%),
      linear-gradient(180deg, #eef5ff 0%, #e8f1ff 60%, #edf5ff 100%);
  }

  .ambient-layer.registrybg::after {
    opacity: 0.14;
    animation: none;
  }

  .ambient-layer.registrybg .ambient-orb,
  .ambient-layer.registrybg .ambient-cursor,
  .ambient-layer.registrybg .ambient-sheen {
    display: none;
  }

  .ambient-layer.studiobg::before {
    content: "";
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba(23, 86, 139, 0.07) 1px, transparent 1px),
      linear-gradient(90deg, rgba(23, 86, 139, 0.07) 1px, transparent 1px);
    background-size: 34px 34px;
    opacity: 0.52;
  }

  .ambient-layer::after {
    content: "";
    position: absolute;
    inset: -10%;
    background:
      radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.4), transparent 45%),
      radial-gradient(circle at 70% 65%, rgba(255, 255, 255, 0.26), transparent 50%);
    animation: ambient-drift 16s ease-in-out infinite alternate;
    opacity: 0.48;
  }

  .ambient-orb {
    position: absolute;
    border-radius: 999px;
    filter: blur(1px);
    opacity: 0.75;
    animation: float-orb 9s ease-in-out infinite;
  }

  .ambient-orb.orb-a {
    width: 340px;
    height: 340px;
    left: -80px;
    top: 10%;
    background: radial-gradient(circle, rgba(22, 126, 191, 0.38) 0%, rgba(22, 126, 191, 0) 72%);
  }

  .ambient-orb.orb-b {
    width: 280px;
    height: 280px;
    right: -60px;
    top: 48%;
    animation-delay: -3.2s;
    background: radial-gradient(circle, rgba(64, 183, 160, 0.34) 0%, rgba(64, 183, 160, 0) 72%);
  }

  .ambient-orb.orb-c {
    width: 250px;
    height: 250px;
    left: 42%;
    bottom: -90px;
    animation-delay: -6.4s;
    background: radial-gradient(circle, rgba(241, 170, 86, 0.3) 0%, rgba(241, 170, 86, 0) 72%);
  }

  .ambient-cursor {
    position: absolute;
    width: 420px;
    height: 420px;
    left: calc(var(--ambient-x) - 210px);
    top: calc(var(--ambient-y) - 210px);
    border-radius: 999px;
    background: radial-gradient(circle, rgba(255, 255, 255, 0.58) 0%, rgba(255, 255, 255, 0) 66%);
    mix-blend-mode: screen;
    transition: left 110ms ease, top 110ms ease;
  }

  .ambient-sheen {
    position: absolute;
    width: 58%;
    height: 140%;
    top: -18%;
    right: -24%;
    transform: rotate(17deg);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.48), rgba(255, 255, 255, 0));
    opacity: 0.35;
  }

  .map-workspace {
    z-index: 1;
  }

  .map-ambient {
    position: absolute;
    inset: 0;
    z-index: 2;
    pointer-events: none;
    overflow: hidden;
    mix-blend-mode: screen;
  }

  .map-ring {
    position: absolute;
    border: 1px solid rgba(20, 131, 186, 0.55);
    border-radius: 999px;
    animation: pulse-ring 3.2s ease-out infinite;
  }

  .map-ring.ring-a {
    width: 180px;
    height: 180px;
    left: calc(var(--ambient-x) - 90px);
    top: calc(var(--ambient-y) - 90px);
  }

  .map-ring.ring-b {
    width: 320px;
    height: 320px;
    left: calc(var(--ambient-x) - 160px);
    top: calc(var(--ambient-y) - 160px);
    animation-delay: -1.2s;
    border-color: rgba(68, 170, 162, 0.42);
  }

  .map-sweep {
    position: absolute;
    top: -20%;
    left: -18%;
    width: 42%;
    height: 140%;
    background: linear-gradient(90deg, rgba(255, 255, 255, 0) 0%, rgba(122, 214, 233, 0.22) 50%, rgba(255, 255, 255, 0) 100%);
    transform: rotate(8deg);
    animation: map-sweep 6.5s linear infinite;
  }

  .map {
    width: 100%;
    height: 100%;
  }

  .pad {
    height: 100%;
    padding: 24px;
    overflow-y: auto;
    overflow-x: hidden;
    background:
      radial-gradient(circle at 80% 10%, rgba(194, 228, 255, 0.3), transparent 35%),
      rgba(242, 247, 255, 0.6);
    box-sizing: border-box;
    backdrop-filter: blur(1px);
    min-width: 0;
  }

  .pad h2 {
    margin: 0 0 8px;
    font-size: clamp(32px, 4vw, 46px);
    letter-spacing: -0.02em;
    color: #13365c;
  }

  .home-workspace {
    position: relative;
    overflow-y: auto;
    overflow-x: hidden;
    background:
      radial-gradient(circle at 82% 12%, rgba(118, 190, 229, 0.14), transparent 34%),
      radial-gradient(circle at 20% 82%, rgba(130, 178, 228, 0.1), transparent 38%),
      linear-gradient(180deg, #edf4ff 0%, #e8f1ff 58%, #edf4ff 100%);
  }

  .home-workspace > * {
    position: relative;
    z-index: 1;
  }

  .registry-workspace {
    position: relative;
    overflow-y: auto;
    overflow-x: hidden;
  }

  .panel,
  .pad,
  .home-workspace,
  .registry-workspace {
    scrollbar-width: none;
    -ms-overflow-style: none;
  }

  .panel::-webkit-scrollbar,
  .pad::-webkit-scrollbar,
  .home-workspace::-webkit-scrollbar,
  .registry-workspace::-webkit-scrollbar {
    width: 0;
    height: 0;
    display: none;
  }

  .registry-workspace > * {
    position: relative;
    z-index: 1;
  }

  .home-project-bg {
    position: fixed;
    inset: 0;
    min-height: 100dvh;
    z-index: 0;
    pointer-events: none;
    overflow: hidden;
    background:
      radial-gradient(circle at 14% 18%, rgba(31, 137, 206, 0.15) 0%, rgba(31, 137, 206, 0) 34%),
      radial-gradient(circle at 28% 72%, rgba(32, 178, 167, 0.13) 0%, rgba(32, 178, 167, 0) 36%),
      radial-gradient(circle at 82% 24%, rgba(26, 173, 164, 0.16) 0%, rgba(26, 173, 164, 0) 38%),
      radial-gradient(circle at 86% 78%, rgba(238, 163, 77, 0.13) 0%, rgba(238, 163, 77, 0) 40%);
  }

  .layout.high-contrast .home-workspace {
    background:
      radial-gradient(circle at 84% 14%, rgba(95, 184, 230, 0.2), transparent 36%),
      radial-gradient(circle at 18% 84%, rgba(139, 188, 233, 0.14), transparent 40%),
      linear-gradient(180deg, #e7f1ff 0%, #e2edff 58%, #e9f2ff 100%);
  }

  .home-project-bg .home-bg-mesh {
    position: absolute;
    inset: -10% -12% -10% -8%;
    background:
      radial-gradient(circle at 28% 24%, rgba(21, 132, 206, 0.28) 0%, rgba(21, 132, 206, 0) 38%),
      radial-gradient(circle at 74% 18%, rgba(26, 182, 172, 0.24) 0%, rgba(26, 182, 172, 0) 40%),
      radial-gradient(circle at 66% 72%, rgba(236, 160, 74, 0.2) 0%, rgba(236, 160, 74, 0) 44%),
      linear-gradient(140deg, rgba(22, 121, 199, 0.12), rgba(39, 183, 173, 0.11) 45%, rgba(95, 152, 226, 0.05));
    filter: saturate(120%);
    opacity: 0.66;
    animation: mesh-shift 14s ease-in-out infinite alternate;
  }

  .home-project-bg .home-bg-wave {
    position: absolute;
    right: -6%;
    width: min(66vw, 900px);
    height: 2px;
    --wave-rotate: 20deg;
    background: linear-gradient(90deg, rgba(20, 129, 202, 0), rgba(20, 129, 202, 0.9), rgba(33, 180, 170, 0.9), rgba(20, 129, 202, 0));
    filter: drop-shadow(0 0 8px rgba(20, 129, 202, 0.34));
    opacity: 0.45;
    transform: rotate(var(--wave-rotate));
    animation: wave-slide 6.4s linear infinite;
  }

  .home-project-bg .home-bg-wave.wave-1 {
    top: 14%;
    --wave-rotate: 20deg;
  }

  .home-project-bg .home-bg-wave.wave-2 {
    top: 32%;
    --wave-rotate: 8deg;
    animation-delay: -2s;
    opacity: 0.62;
  }

  .home-project-bg .home-bg-wave.wave-3 {
    top: 52%;
    --wave-rotate: -6deg;
    animation-delay: -4.1s;
    opacity: 0.56;
  }

  .home-project-bg .home-bg-core {
    position: absolute;
    right: 38%;
    top: 10%;
    width: min(26vw, 320px);
    aspect-ratio: 1 / 1;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(255, 255, 255, 0.62) 0%, rgba(81, 179, 225, 0.28) 28%, rgba(42, 132, 203, 0) 70%);
    mix-blend-mode: screen;
    opacity: 0.52;
    animation: core-pulse 4.2s ease-in-out infinite;
  }

  .home-project-bg .home-bg-dot {
    position: absolute;
    width: 13px;
    height: 13px;
    border-radius: 999px;
    background: #0e7fc1;
    box-shadow: 0 0 0 8px rgba(17, 130, 197, 0.11), 0 0 20px rgba(17, 130, 197, 0.3);
    animation: dot-ping 2.4s ease-in-out infinite;
  }

  .home-project-bg .home-bg-dot.dot-1 {
    right: 14%;
    top: 19%;
  }

  .home-project-bg .home-bg-dot.dot-2 {
    right: 8%;
    top: 26%;
    animation-delay: -0.6s;
  }

  .home-project-bg .home-bg-dot.dot-3 {
    right: 18%;
    top: 36%;
    animation-delay: -1.2s;
  }

  .home-project-bg .home-bg-dot.dot-4 {
    right: 11%;
    top: 49%;
    animation-delay: -1.8s;
  }

  .home-project-bg .home-bg-dot.dot-5 {
    right: 20%;
    top: 60%;
    animation-delay: -2.2s;
  }

  .home-project-bg .home-bg-dot.dot-6 {
    right: 52%;
    top: 24%;
    animation-delay: -1.1s;
  }

  .home-project-bg .home-bg-dot.dot-7 {
    right: 60%;
    top: 46%;
    animation-delay: -1.7s;
  }

  .home-hero {
    max-width: 1240px;
    border: 1px solid #c9daef;
    border-radius: 18px;
    background:
      radial-gradient(circle at 88% 18%, rgba(41, 183, 191, 0.16), transparent 30%),
      radial-gradient(circle at 10% 85%, rgba(40, 115, 213, 0.1), transparent 36%),
      linear-gradient(180deg, #ffffff 0%, #f4f9ff 100%);
    padding: 20px 22px;
    box-shadow: 0 10px 30px rgba(25, 78, 139, 0.08);
  }

  .home-badge {
    display: inline-block;
    font-size: 12px;
    font-weight: 700;
    color: #17508a;
    background: #e6f2ff;
    border: 1px solid #bdd8f5;
    border-radius: 999px;
    padding: 4px 10px;
    margin-bottom: 10px;
  }

  .home-subtitle {
    margin: 16px 0 14px;
    color: #2d4f75;
    line-height: 1.5;
    font-size: clamp(16px, 1.8vw, 18px);
    max-width: 1120px;
  }

  .home-intro {
    display: grid;
    grid-template-columns: repeat(2, minmax(240px, 1fr));
    gap: 12px;
    max-width: 1120px;
    margin: 14px 0 12px;
  }

  .home-info-card {
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #cadcf3;
    border-radius: 14px;
    padding: 12px 14px;
  }

  .home-intro h4 {
    margin: 0 0 8px;
    font-size: 16px;
    color: #173c66;
  }

  .home-intro ul {
    margin: 0;
    padding-left: 20px;
    background: transparent;
    border: 0;
    border-radius: 0;
  }

  .home-intro li {
    margin: 6px 0;
    color: #2f537b;
  }

  .home-workspace-title {
    margin: 10px 0 10px;
    color: #1b446f;
    font-size: 24px;
    letter-spacing: -0.01em;
  }

  .pad ul {
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #cadef6;
    border-radius: 12px;
    padding: 12px 16px 12px 26px;
  }

  .pad li {
    margin: 7px 0;
    color: #24476f;
  }

  .home-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 14px;
    max-width: 1120px;
    width: 100%;
    min-width: 0;
  }

  .home-card {
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
    padding: 16px;
    border: 1px solid #c8d8ef;
    background: linear-gradient(180deg, #ffffff 0%, #f6fbff 100%);
    border-radius: 14px;
    cursor: pointer;
    text-align: left;
    box-sizing: border-box;
    min-width: 0;
  }

  .home-card-top {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
  }

  .home-card b {
    font-size: clamp(17px, 1.9vw, 18px);
    color: #163a63;
    overflow-wrap: anywhere;
  }

  .home-card span {
    font-size: 13px;
    color: #35587f;
    overflow-wrap: anywhere;
  }

  .home-card em {
    color: #2f5f95;
    font-size: 12px;
    font-style: normal;
    font-weight: 700;
    margin-top: 2px;
    overflow-wrap: anywhere;
  }

  .home-card:hover {
    background: linear-gradient(180deg, #edf7ff 0%, #e7f2ff 100%);
  }

  .status {
    position: absolute;
    top: 12px;
    left: 12px;
    z-index: 3;
    padding: 9px 11px;
    background: var(--status-bg);
    color: #fff;
    border-radius: 10px;
    font-weight: 600;
  }

  .status.error {
    background: var(--status-error);
  }

  .status.toast {
    background: var(--status-toast);
    top: 62px;
    animation: toast-fade 0.95s ease forwards;
    pointer-events: none;
  }

  .status.route {
    top: 112px;
  }

  @keyframes toast-fade {
    0% { opacity: 0; transform: translateY(-6px); }
    15% { opacity: 1; transform: translateY(0); }
    85% { opacity: 1; transform: translateY(0); }
    100% { opacity: 0; transform: translateY(-8px); }
  }

  @keyframes float-orb {
    0% { transform: translate3d(0, 0, 0) scale(1); }
    50% { transform: translate3d(18px, -14px, 0) scale(1.08); }
    100% { transform: translate3d(0, 0, 0) scale(1); }
  }

  @keyframes pulse-ring {
    0% { opacity: 0.5; transform: scale(0.92); }
    70% { opacity: 0; transform: scale(1.16); }
    100% { opacity: 0; transform: scale(1.16); }
  }

  @keyframes map-sweep {
    0% { transform: translateX(-8%) rotate(8deg); }
    100% { transform: translateX(290%) rotate(8deg); }
  }

  @keyframes ambient-drift {
    0% { transform: translate3d(0, 0, 0) scale(1); }
    100% { transform: translate3d(-2%, 1.5%, 0) scale(1.04); }
  }

  @keyframes mesh-shift {
    0% { transform: translate3d(0, 0, 0) scale(1); }
    100% { transform: translate3d(-2.5%, 2.2%, 0) scale(1.04); }
  }

  @keyframes wave-slide {
    0% { transform: translateX(-8%) rotate(var(--wave-rotate)); }
    100% { transform: translateX(20%) rotate(var(--wave-rotate)); }
  }

  @keyframes core-pulse {
    0% { transform: scale(0.95); opacity: 0.74; }
    50% { transform: scale(1.05); opacity: 1; }
    100% { transform: scale(0.95); opacity: 0.74; }
  }

  @keyframes dot-ping {
    0% { transform: scale(0.88); opacity: 0.65; }
    45% { transform: scale(1.18); opacity: 1; }
    100% { transform: scale(0.88); opacity: 0.65; }
  }

  @media (max-width: 1920px) {
    .home-hero,
    .home-intro,
    .home-grid {
      max-width: 1180px;
    }
  }

  @media (max-width: 1440px) {
    .layout {
      grid-template-columns: minmax(290px, 340px) minmax(0, 1fr);
    }

    .pad {
      padding: 20px;
    }

    .home-grid {
      grid-template-columns: repeat(2, minmax(220px, 1fr));
    }
  }

  @media (max-width: 1366px) {
    .layout {
      grid-template-columns: minmax(280px, 320px) minmax(0, 1fr);
    }

    .panel {
      padding: 16px;
    }

    .home-intro {
      grid-template-columns: 1fr;
    }

    .home-hero {
      max-width: 100%;
    }
  }

  @media (max-width: 1024px) {
    .layout {
      height: 100vh;
      height: 100dvh;
      min-height: 100vh;
      min-height: 100dvh;
      grid-template-columns: 1fr;
      grid-template-rows: auto minmax(0, 1fr);
      overflow: hidden;
    }

    .mobile-nav-toggle {
      display: inline-flex;
      position: relative;
      top: auto;
      left: auto;
      margin: 10px 0 0 10px;
      z-index: 33;
    }

    .content {
      grid-row: 2;
      min-height: 0;
    }

    .panel {
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      width: min(86vw, 380px);
      max-height: none;
      min-height: 0;
      z-index: 35;
      transform: translateX(-104%);
      transition: transform 200ms ease;
      box-shadow: 10px 0 32px rgba(15, 44, 74, 0.22);
    }

    .layout.panel-open .panel {
      transform: translateX(0);
    }

    .mobile-nav-backdrop {
      display: block;
      position: fixed;
      inset: 0;
      z-index: 34;
      border: 0;
      margin: 0;
      padding: 0;
      background: rgba(10, 25, 43, 0.34);
      backdrop-filter: blur(1.5px);
      cursor: pointer;
    }

    .home-grid {
      grid-template-columns: 1fr;
    }

    .home-intro {
      grid-template-columns: 1fr;
    }

    .home-project-bg .home-bg-mesh {
      inset: -12% -20% -10% -14%;
      opacity: 0.82;
    }

    .home-project-bg .home-bg-wave {
      width: min(70vw, 360px);
      right: -10%;
      opacity: 0.54;
    }

    .home-project-bg .home-bg-core {
      width: min(40vw, 220px);
      right: 10%;
      top: 16%;
      opacity: 0.7;
    }

    .home-project-bg .home-bg-dot {
      width: 10px;
      height: 10px;
      box-shadow: 0 0 0 6px rgba(17, 130, 197, 0.14), 0 0 18px rgba(17, 130, 197, 0.38);
    }

  }

  @media (max-width: 768px) {
    .panel {
      padding: 14px;
      max-height: none;
    }

    .pad {
      padding: 16px;
    }

    .card {
      padding: 12px;
      border-radius: 14px;
    }

    .home-workspace-title {
      font-size: 22px;
    }

    .narrative-status-row {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 430px) {
    .mobile-nav-toggle {
      top: 10px;
      left: 10px;
      width: 40px;
      height: 40px;
      border-radius: 11px;
    }

    .panel {
      padding: 10px;
      max-height: none;
    }

    .panel h1 {
      white-space: normal;
      font-size: 40px;
      line-height: 0.92;
    }

    .panel p {
      margin-top: 8px;
      font-size: 13.5px;
      line-height: 1.24;
    }

    .card {
      margin-top: 10px;
      padding: 10px;
      border-radius: 12px;
    }

    .card h3 {
      font-size: 22px;
      margin-bottom: 8px;
    }

    .card label {
      font-size: 12px;
      margin-top: 7px;
    }

    .card button,
    .card select,
    .card input[type="number"] {
      font-size: 15.5px;
      padding: 10px 11px;
    }

    .pad {
      padding: 14px;
    }

    .home-hero {
      padding: 14px;
      border-radius: 14px;
    }

    .home-card {
      padding: 12px;
      border-radius: 12px;
    }

    .home-card-top {
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
    }

    .home-card span {
      font-size: 12.5px;
    }

    .home-card em {
      font-size: 11.5px;
    }

    .home-subtitle {
      line-height: 1.35;
      font-size: 15px;
    }

    .home-workspace-title {
      font-size: 21px;
      margin-top: 8px;
    }

    .home-intro {
      gap: 10px;
    }

    .home-grid {
      gap: 8px;
    }

    .narrative-current-title {
      font-size: 13px;
    }
  }

  @media (max-width: 390px) {
    .panel {
      padding: 10px;
      max-height: none;
    }

    .panel h1 {
      font-size: 36px;
    }

    .panel p {
      font-size: 12.5px;
    }

    .card {
      padding: 9px;
      border-radius: 12px;
    }

    .card h3 {
      font-size: 20px;
    }

    .card button,
    .card select,
    .card input[type="number"] {
      font-size: 15px;
    }

    .pad {
      padding: 12px;
    }

    .home-card-top {
      gap: 2px;
    }

    .home-workspace-title {
      font-size: 20px;
    }

    .home-subtitle {
      font-size: 14px;
    }
  }
</style>
