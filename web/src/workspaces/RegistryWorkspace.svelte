<script>
  import { onDestroy, onMount, tick } from "svelte";
  import maplibregl from "maplibre-gl";
  import {
    confidenceClass,
    dedupeRegistryRows,
    featuresFrom,
    fmtNum,
    norm,
    num,
    registryFeatureCollection,
    rowRegistryId,
    rowsFromGeojson,
    sourceTierLabel,
    upper,
    verifiedFeatureCollection,
    verifiedRowsFromGeojson
  } from "./registryUtils.js";

  export let globalRegistry = null;
  export let registryMeta = null;
  export let active = false;

  let fallbackGlobalRegistry = null;
  let illinoisRegistry = null;
  let supplementalOpenRegistry = null;
  let verifiedCloudRegions = null;
  let scope = "world";
  let provider = "all";
  let confidenceFilter = "all";
  let sourceTierFilter = "all";
  let search = "";
  let showVerifiedLayer = true;
  let limit = 200;
  let recordsExpanded = false;
  let mapInitError = "";
  let dataLoading = false;
  let dataLoadError = "";
  let dataLoadAttempted = false;
  let zeroDataRecoveryAttempts = 0;
  let defaultResetDone = false;
  let mapEl;
  let map;
  let mapReady = false;
  let lastAutoFitSignature = "";
  let selectedRegistryId = "";
  let activePopup = null;

  const REGISTRY_MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
  const REGISTRY_SOURCE_ID = "registry-points";
  const VERIFIED_SOURCE_ID = "verified-cloud-regions";
  const DEFAULT_WORLD_VIEW = { center: [8, 20], zoom: 1.25 };
  const COUNTRY_NAME_BY_CODE = {
    US: "United States",
    DE: "Germany",
    BR: "Brazil",
    GB: "United Kingdom",
    UK: "United Kingdom",
    FR: "France",
    IN: "India",
    ID: "Indonesia",
    CA: "Canada",
    AU: "Australia",
    JP: "Japan",
    SG: "Singapore",
    NL: "Netherlands",
    ES: "Spain",
    IT: "Italy",
    IE: "Ireland",
    CH: "Switzerland",
    SE: "Sweden",
    NO: "Norway",
    FI: "Finland",
    DK: "Denmark",
    BE: "Belgium",
    PL: "Poland",
    AT: "Austria",
    MX: "Mexico",
    ZA: "South Africa",
    AE: "United Arab Emirates",
  };
  const esc = (s) =>
    String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  function countryDisplayName(value) {
    const raw = norm(value);
    if (!raw) return "Unknown";
    const code = upper(raw);
    const full = COUNTRY_NAME_BY_CODE[code];
    if (full) return full;
    return raw;
  }

  $: rawRows = [
    ...rowsFromGeojson(globalRegistry, "Global preload"),
    ...rowsFromGeojson(fallbackGlobalRegistry, "Global fallback"),
    ...rowsFromGeojson(illinoisRegistry, "Illinois merged"),
    ...rowsFromGeojson(supplementalOpenRegistry, "Open supplemental"),
  ];
  $: dedupeOutput = dedupeRegistryRows(rawRows);
  $: rows = dedupeOutput.rows;
  $: dedupeStats = dedupeOutput.stats;
  $: verifiedRows = verifiedRowsFromGeojson(verifiedCloudRegions);
  $: usRows = rows.filter((r) => upper(r.country) === "US");
  $: ilRows = rows.filter((r) => upper(r.country) === "US" && ["IL", "ILLINOIS"].includes(upper(r.state)));
  $: sourceRows = scope === "us" ? usRows : scope === "illinois" ? ilRows : rows;

  $: providerOptions = [
    "all",
    ...Array.from(new Set(sourceRows.map((r) => norm(r.provider_family)).filter(Boolean))).sort((a, b) => a.localeCompare(b))
  ];
  $: if (provider !== "all" && !providerOptions.includes(provider)) provider = "all";

  $: filteredRows = sourceRows
    .filter((r) => (provider === "all" ? true : norm(r.provider_family) === provider))
    .filter((r) => (confidenceFilter === "all" ? true : upper(r.confidence_band) === upper(confidenceFilter)))
    .filter((r) => (sourceTierFilter === "all" ? true : norm(r.source_tier) === sourceTierFilter))
    .filter((r) => {
      const q = norm(search).toLowerCase();
      if (!q) return true;
      const hay =
        `${norm(r.name)} ${norm(r.operator)} ${norm(r.address)} ${norm(r.city)} ${norm(r.state)} ${norm(r.country)} ${norm(r.provider_family)} ${norm(r.source_system)}`.toLowerCase();
      return hay.includes(q);
    });

  $: visibleRows = filteredRows.slice(0, limit);
  $: canLoadMore = filteredRows.length > limit;
  $: avgConfidence = rows.length
    ? Math.round(rows.reduce((sum, r) => sum + (Number.isFinite(Number(r.confidence_score)) ? Number(r.confidence_score) : 0), 0) / rows.length)
    : 0;
  $: highConfidenceShare = rows.length
    ? Math.round((rows.filter((r) => r.confidence_band === "High").length / rows.length) * 100)
    : 0;
  $: dedupeReductionPct = dedupeStats.rawCount
    ? Math.round(((dedupeStats.rawCount - dedupeStats.dedupedCount) / dedupeStats.rawCount) * 100)
    : 0;
  $: officialRowsCount = rows.filter((r) => r.source_tier === "official").length;
  $: openRowsCount = rows.filter((r) => r.source_tier === "open").length;
  $: curatedRowsCount = rows.filter((r) => r.source_tier === "curated").length;
  $: topCountries = Array.from(
    filteredRows.reduce((m, r) => {
      const key = norm(r.country) || "Unknown";
      m.set(key, (m.get(key) || 0) + 1);
      return m;
    }, new Map())
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  $: topOperators = Array.from(
    filteredRows.reduce((m, r) => {
      const key = norm(r.operator) || "Unknown";
      m.set(key, (m.get(key) || 0) + 1);
      return m;
    }, new Map())
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  $: if (selectedRegistryId && !filteredRows.some((r) => rowRegistryId(r) === selectedRegistryId)) {
    selectedRegistryId = "";
  }

  function currentMapData() {
    return registryFeatureCollection(filteredRows);
  }

  function currentVerifiedData() {
    return verifiedFeatureCollection(verifiedRows);
  }

  function popupHtml(p) {
    const isVerifiedRegion = Boolean(norm(p.region_name)) || norm(p.source_system).toLowerCase().includes("official cloud region");
    const title = p.region_name || p.name || "Cloud region";
    const location = `${p.city || "N/A"}${p.state ? `, ${p.state}` : ""}${p.country ? ` (${p.country})` : ""}`;
    const sourceLink = p.source_url
      ? `<a class="registry-popup-link" href="${esc(p.source_url)}" target="_blank" rel="noreferrer">Source link</a>`
      : "";
    const confidence = Number.isFinite(Number(p.confidence_score))
      ? `${p.confidence_band} (${Number(p.confidence_score)} / 100)`
      : "";
    const capacity = Number.isFinite(Number(p.estimated_mw))
      ? `${fmtNum(p.estimated_mw, 1)} MW est`
      : "";
    if (isVerifiedRegion) {
      return `
        <div class="registry-popup-card">
          <div class="registry-popup-title">${esc(title)}</div>
          <div><span class="k">Layer:</span> Verified cloud region</div>
          <div><span class="k">Provider:</span> ${esc(p.provider_family || "Unknown")}</div>
          <div><span class="k">Location:</span> ${esc(location)}</div>
          <div><span class="k">Source:</span> ${esc(p.source_system || "Official provider page")}</div>
          ${sourceLink}
        </div>
      `;
    }

    return `
      <div class="registry-popup-card">
        <div class="registry-popup-title">${esc(title)}</div>
        ${p.operator && p.operator !== "Unknown" ? `<div><span class="k">Operator:</span> ${esc(p.operator)}</div>` : ""}
        ${p.address ? `<div><span class="k">Address:</span> ${esc(p.address)}</div>` : ""}
        <div><span class="k">Location:</span> ${esc(location)}</div>
        <div><span class="k">Provider:</span> ${esc(p.provider_family || "Other/Unknown")}</div>
        ${confidence ? `<div><span class="k">Confidence:</span> ${esc(confidence)}</div>` : ""}
        ${capacity ? `<div><span class="k">Capacity proxy:</span> ${esc(capacity)}</div>` : ""}
        ${Number.isFinite(Number(p.carrier_count)) && Number.isFinite(Number(p.ix_count)) ? `<div><span class="k">Connectivity:</span> carriers ${esc(String(p.carrier_count))} | IX ${esc(String(p.ix_count))}</div>` : ""}
        ${p.source_tier_label ? `<div><span class="k">Source tier:</span> ${esc(p.source_tier_label)}</div>` : ""}
        <div><span class="k">Source:</span> ${esc(p.source_system || "Unknown")}</div>
        ${sourceLink}
      </div>
    `;
  }

  function rowIsSelected(row) {
    return rowRegistryId(row) !== "" && rowRegistryId(row) === selectedRegistryId;
  }

  function openPopupAt(lon, lat, properties) {
    if (!map) return;
    if (activePopup) activePopup.remove();
    activePopup = new maplibregl.Popup({ closeButton: true, closeOnClick: true, className: "registry-popup-shell" })
      .setLngLat([lon, lat])
      .setHTML(popupHtml(properties || {}))
      .addTo(map);
  }

  function focusRow(row) {
    if (!row || !map) return;
    const lat = num(row.latitude);
    const lon = num(row.longitude);
    if (lat === null || lon === null) return;
    selectedRegistryId = rowRegistryId(row);
    map.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), 8.8), speed: 0.9 });
    openPopupAt(lon, lat, row);
  }

  function refreshMapData() {
    if (!mapReady || !map) return;
    const source = map.getSource(REGISTRY_SOURCE_ID);
    if (!source) return;
    source.setData(currentMapData());
  }

  function refreshVerifiedLayerData() {
    if (!mapReady || !map) return;
    const source = map.getSource(VERIFIED_SOURCE_ID);
    if (!source) return;
    source.setData(currentVerifiedData());
  }

  function setVerifiedVisibility() {
    if (!mapReady || !map) return;
    const visibility = showVerifiedLayer ? "visible" : "none";
    if (map.getLayer("verified-cloud-layer")) {
      map.setLayoutProperty("verified-cloud-layer", "visibility", visibility);
    }
  }

  function fitMapToFiltered() {
    if (!mapReady || !map) return;
    const rowsIn = filteredRows;
    if (!rowsIn.length) return;
    const points = rowsIn
      .map((r) => [num(r.longitude), num(r.latitude)])
      .filter((p) => p[0] !== null && p[1] !== null);
    if (!points.length) return;
    if (points.length === 1) {
      map.flyTo({ center: points[0], zoom: 8.5, speed: 0.8 });
      return;
    }
    const b = new maplibregl.LngLatBounds(points[0], points[0]);
    for (const p of points.slice(1)) b.extend(p);
    map.fitBounds(b, { padding: 46, duration: 700, maxZoom: 8.8 });
  }

  function isDefaultWorldState() {
    return (
      scope === "world" &&
      provider === "all" &&
      confidenceFilter === "all" &&
      sourceTierFilter === "all" &&
      !norm(search)
    );
  }

  function showDefaultWorldView(duration = 700) {
    if (!map) return;
    map.easeTo({
      center: DEFAULT_WORLD_VIEW.center,
      zoom: DEFAULT_WORLD_VIEW.zoom,
      bearing: 0,
      pitch: 0,
      duration,
    });
  }

  function applyDefaultFilters() {
    scope = "world";
    provider = "all";
    confidenceFilter = "all";
    sourceTierFilter = "all";
    search = "";
    showVerifiedLayer = true;
  }

  async function loadSupplementalData(forceFresh = false) {
    if (dataLoading) return;
    dataLoading = true;
    dataLoadError = "";
    dataLoadAttempted = true;
    try {
      async function fetchJson(url, optional = false) {
        const withBust = forceFresh ? `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}` : url;
        const response = await fetch(withBust, { cache: "no-store" });
        if (!response.ok) {
          if (optional) return null;
          throw new Error(`${url} returned ${response.status}`);
        }
        return response.json();
      }

      const shouldFetchGlobal = !featuresFrom(globalRegistry).length;
      const requests = [
        fetchJson("/data/il_datacenters_registry.geojson"),
        shouldFetchGlobal ? fetchJson("/data/global_datacenters_registry.geojson") : Promise.resolve(null),
        fetchJson("/data/verified_cloud_regions.geojson", true),
        fetchJson("/data/open_registry_supplemental.geojson", true),
      ];

      const [ilData, globalData, verifiedData, openRegistryData] = await Promise.all(requests);
      illinoisRegistry = ilData;
      if (globalData) {
        fallbackGlobalRegistry = globalData;
      }
      if (verifiedData) {
        verifiedCloudRegions = verifiedData;
      }
      if (openRegistryData) {
        supplementalOpenRegistry = openRegistryData;
      }
    } catch (err) {
      dataLoadError = err instanceof Error ? err.message : "Failed to load registry dataset.";
    } finally {
      dataLoading = false;
    }
  }

  onMount(async () => {
    applyDefaultFilters();
    setTimeout(() => {
      applyDefaultFilters();
      defaultResetDone = true;
    }, 0);
    requestAnimationFrame(() => applyDefaultFilters());

    await loadSupplementalData();
    await tick();
    if (!mapEl) return;
    try {
      map = new maplibregl.Map({
        container: mapEl,
        style: REGISTRY_MAP_STYLE,
        center: DEFAULT_WORLD_VIEW.center,
        zoom: DEFAULT_WORLD_VIEW.zoom,
        attributionControl: true,
        renderWorldCopies: false,
      });
    } catch (err) {
      mapInitError = err instanceof Error ? err.message : "Map failed to initialize.";
      return;
    }
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
    map.on("error", (e) => {
      const msg = String(e?.error?.message || "Map rendering error.");
      mapInitError = msg;
    });

    map.on("load", () => {
      map.addSource(REGISTRY_SOURCE_ID, {
        type: "geojson",
        data: currentMapData(),
        cluster: true,
        clusterRadius: 46,
        clusterMaxZoom: 8,
      });

      map.addLayer({
        id: "registry-clusters",
        type: "circle",
        source: REGISTRY_SOURCE_ID,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": [
            "step",
            ["get", "point_count"],
            "#2b7de5",
            30,
            "#1f5cad",
            120,
            "#153f76",
          ],
          "circle-radius": [
            "step",
            ["get", "point_count"],
            17,
            30,
            22,
            120,
            28,
          ],
          "circle-stroke-color": "#dceaff",
          "circle-stroke-width": 1.5,
        },
      });

      map.addLayer({
        id: "registry-cluster-count",
        type: "symbol",
        source: REGISTRY_SOURCE_ID,
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-size": 12,
          "text-font": ["Open Sans Bold"],
        },
        paint: { "text-color": "#ffffff" },
      });

      map.addLayer({
        id: "registry-unclustered",
        type: "circle",
        source: REGISTRY_SOURCE_ID,
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "match",
            ["get", "confidence_band"],
            "High", "#1d9d77",
            "Medium", "#2c72d6",
            "#f29b1d",
          ],
          "circle-radius": 5.5,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.1,
          "circle-opacity": 0.9,
        },
      });

      map.addSource(VERIFIED_SOURCE_ID, {
        type: "geojson",
        data: currentVerifiedData(),
      });

      map.addLayer({
        id: "verified-cloud-layer",
        type: "circle",
        source: VERIFIED_SOURCE_ID,
        paint: {
          "circle-color": [
            "match",
            ["get", "provider_family"],
            "Amazon AWS", "#ff9900",
            "Microsoft Azure", "#0078d4",
            "Google Cloud", "#34a853",
            "Meta", "#4267b2",
            "#6e7fa0",
          ],
          "circle-radius": 7.2,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.4,
          "circle-opacity": 0.86,
        },
      });

      map.on("click", "registry-clusters", (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const clusterId = feature.properties?.cluster_id;
        const source = map.getSource(REGISTRY_SOURCE_ID);
        if (!source || typeof source.getClusterExpansionZoom !== "function") return;
        source.getClusterExpansionZoom(clusterId, (err, zoom) => {
          if (err) return;
          map.easeTo({ center: feature.geometry.coordinates, zoom });
        });
      });

      map.on("click", "registry-unclustered", (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const p = feature.properties || {};
        selectedRegistryId = String(p.row_key || p.registry_id || p.source_record_id || "");
        openPopupAt(feature.geometry.coordinates[0], feature.geometry.coordinates[1], p);
      });

      map.on("click", "verified-cloud-layer", (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        openPopupAt(feature.geometry.coordinates[0], feature.geometry.coordinates[1], feature.properties || {});
      });

      map.on("mouseenter", "registry-clusters", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "registry-clusters", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("mouseenter", "registry-unclustered", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "registry-unclustered", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("mouseenter", "verified-cloud-layer", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "verified-cloud-layer", () => {
        map.getCanvas().style.cursor = "";
      });

      if (typeof map.setRenderWorldCopies === "function") {
        map.setRenderWorldCopies(false);
      }

      mapReady = true;
      mapInitError = "";
      map.resize();
      setVerifiedVisibility();
      if (isDefaultWorldState()) {
        showDefaultWorldView(0);
      } else {
        fitMapToFiltered();
      }
    });
  });

  onDestroy(() => {
    if (activePopup) activePopup.remove();
    if (map) map.remove();
  });

  $: if (mapReady) {
    filteredRows;
    refreshMapData();
  }

  $: if (mapReady) {
    verifiedRows;
    refreshVerifiedLayerData();
  }

  $: if (mapReady) {
    showVerifiedLayer;
    setVerifiedVisibility();
  }

  $: if (!dataLoading && !rows.length && !dataLoadError && !dataLoadAttempted) {
    loadSupplementalData();
  }

  $: if (defaultResetDone && !dataLoading && !dataLoadError && rows.length === 0 && zeroDataRecoveryAttempts < 1) {
    zeroDataRecoveryAttempts += 1;
    loadSupplementalData(true);
  }

  $: fitSignature = `${scope}|${provider}|${confidenceFilter}|${sourceTierFilter}|${norm(search)}|${filteredRows.length}`;

  $: if (mapReady && fitSignature !== lastAutoFitSignature) {
    lastAutoFitSignature = fitSignature;
    setTimeout(() => {
      if (isDefaultWorldState()) {
        showDefaultWorldView(350);
      } else {
        fitMapToFiltered();
      }
    }, 40);
  }

  $: if (mapReady && active) {
    setTimeout(() => map?.resize(), 30);
  }
</script>

<h2>Data Center Registry Explorer</h2>
<p class="subtitle">
  Global and US registry view with advanced dedupe, confidence scoring, capacity proxies, and a separate verified cloud-region layer.
</p>

<section class="toolbar">
  <label>Scope
    <select bind:value={scope}>
      <option value="world">World</option>
      <option value="us">United States</option>
      <option value="illinois">Illinois</option>
    </select>
  </label>
  <label>Provider family
    <select bind:value={provider}>
      {#each providerOptions as p}
        <option value={p}>{p === "all" ? "All providers" : p}</option>
      {/each}
    </select>
  </label>
  <label>Confidence
    <select bind:value={confidenceFilter}>
      <option value="all">All confidence levels</option>
      <option value="High">High confidence</option>
      <option value="Medium">Medium confidence</option>
      <option value="Low">Low confidence</option>
    </select>
  </label>
  <label>Source quality
    <select bind:value={sourceTierFilter}>
      <option value="all">All source tiers</option>
      <option value="official">Official sources</option>
      <option value="open">Open registries</option>
      <option value="curated">Curated records</option>
      <option value="other">Other sources</option>
    </select>
  </label>
  <label>Search
    <input type="text" bind:value={search} placeholder="Name, operator, city, country"/>
  </label>
  <label class="checkbox-row">
    <input type="checkbox" bind:checked={showVerifiedLayer}/>
    Show verified cloud regions layer
  </label>
</section>
{#if dataLoading}
  <p class="hint">Loading registry data...</p>
{/if}
{#if dataLoadError}
  <div class="data-error">
    <span>Registry data load issue: {dataLoadError}</span>
    <button class="retry-btn" on:click={loadSupplementalData}>Retry Load</button>
  </div>
{/if}

<section class="stats">
  <article class="stat-card stat-deduped">
    <b>{rows.length.toLocaleString()}</b>
    <span>Deduped records</span>
    <small class="metric-help">Unique facilities after duplicate merging.</small>
  </article>
  <article class="stat-card stat-raw">
    <b>{dedupeStats.rawCount.toLocaleString()}</b>
    <span>Raw source rows</span>
    <small class="metric-help">All rows pulled before cleanup.</small>
  </article>
  <article class="stat-card stat-merged">
    <b>{dedupeStats.mergedVariants.toLocaleString()}</b>
    <span>Merged variants ({dedupeReductionPct}%)</span>
    <small class="metric-help">Rows collapsed because they match the same facility.</small>
  </article>
  <article class="stat-card stat-confidence">
    <b>{avgConfidence}</b>
    <span>Average confidence</span>
    <small class="metric-help">Mean record confidence score out of 100.</small>
  </article>
  <article class="stat-card stat-highshare">
    <b>{highConfidenceShare}%</b>
    <span>High-confidence share</span>
    <small class="metric-help">Percent of records marked High confidence.</small>
  </article>
  <article class="stat-card stat-verified">
    <b>{verifiedRows.length.toLocaleString()}</b>
    <span>Verified cloud regions</span>
    <small class="metric-help">Official provider region points in this layer.</small>
  </article>
</section>

<section class="split">
  <div class="card">
    <h3>Source Quality Mix</h3>
    <p class="hint">Breakdown by where each record came from.</p>
    <ul>
      <li class="mix-row mix-official">
        <div>
          <span>Official sources</span>
          <small class="metric-help">Provider/government pages or official systems.</small>
        </div>
        <b>{officialRowsCount.toLocaleString()}</b>
      </li>
      <li class="mix-row mix-open">
        <div>
          <span>Open registries</span>
          <small class="metric-help">Public datasets like PeeringDB/OSM.</small>
        </div>
        <b>{openRowsCount.toLocaleString()}</b>
      </li>
      <li class="mix-row mix-curated">
        <div>
          <span>Curated records</span>
          <small class="metric-help">Project-maintained records added manually.</small>
        </div>
        <b>{curatedRowsCount.toLocaleString()}</b>
      </li>
      <li class="mix-row mix-filtered">
        <div>
          <span>Filtered records</span>
          <small class="metric-help">Rows currently visible under your active filters.</small>
        </div>
        <b>{filteredRows.length.toLocaleString()}</b>
      </li>
    </ul>
  </div>
  <div class="card">
    <h3>How To Read These Numbers</h3>
    <p class="hint">We clean and score records in two steps so counts are easier to trust.</p>
    <ul class="plain-steps">
      <li>
        <b>Step 1: Remove duplicates</b>
        <small class="metric-help">If two rows likely describe the same site (similar name/operator + nearby location), we keep one clean record.</small>
      </li>
      <li>
        <b>Step 2: Score confidence</b>
        <small class="metric-help">Each record gets High/Medium/Low confidence based on source reliability, coordinate precision, and multi-source agreement.</small>
      </li>
    </ul>
    <div class="mini-note">
      <b>Quick takeaway:</b> Higher confidence and fewer merged variants usually mean cleaner, more reliable registry results.
    </div>
  </div>
</section>

<section class="map-card">
  <div class="map-head">
    <h3>Registry Map</h3>
    <button on:click={fitMapToFiltered}>Fit To Filtered Points</button>
  </div>
  <p class="hint">Map reflects active scope/provider/search filters. Click points for confidence, source tier, and capacity proxy details.</p>
  <p class="hint">Blue circles are cluster counts. Colored non-cluster points use confidence classes; verified cloud markers are shown when enabled.</p>
  <div class="cluster-legend" aria-label="Cluster color legend">
    <span class="legend-title">Cluster legend:</span>
    <span class="legend-item">
      <i class="legend-dot light"></i>
      1-29 sites
    </span>
    <span class="legend-item">
      <i class="legend-dot mid"></i>
      30-119 sites
    </span>
    <span class="legend-item">
      <i class="legend-dot dark"></i>
      120+ sites
    </span>
    <span class="legend-item">
      <i class="legend-dot aws"></i>
      AWS verified
    </span>
    <span class="legend-item">
      <i class="legend-dot azure"></i>
      Azure verified
    </span>
    <span class="legend-item">
      <i class="legend-dot gcp"></i>
      GCP verified
    </span>
    <span class="legend-item">
      <i class="legend-dot meta"></i>
      Meta verified
    </span>
  </div>
  {#if mapInitError}
    <p class="hint error-hint">Map error: {mapInitError}</p>
  {/if}
  <div class="map-shell">
    <div class="registry-map" bind:this={mapEl}></div>
  </div>
</section>

<section class="split">
  <div class="card">
    <h3>Top Countries</h3>
    <ul>
      {#each topCountries as row}
        <li><span>{countryDisplayName(row[0])}</span><b>{row[1]}</b></li>
      {/each}
    </ul>
  </div>
  <div class="card">
    <h3>Top Operators</h3>
    <ul>
      {#each topOperators as row}
        <li><span>{row[0]}</span><b>{row[1]}</b></li>
      {/each}
    </ul>
  </div>
</section>

<section class="table-card">
  <div class="records-head">
    <h3>Registry Records</h3>
    <button class="collapse-btn" on:click={() => (recordsExpanded = !recordsExpanded)}>
      {recordsExpanded ? "Hide records" : "Show records"}
    </button>
  </div>
  <p class="hint">Showing {visibleRows.length} of {filteredRows.length} filtered deduped records.</p>
  {#if recordsExpanded}
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Operator</th>
            <th>Location</th>
            <th>Confidence</th>
            <th>Capacity Proxy</th>
            <th>Connectivity</th>
            <th>Provider</th>
            <th>Source Tier</th>
          </tr>
        </thead>
        <tbody>
          {#if visibleRows.length}
            {#each visibleRows as r}
              <tr
                class:selected={rowIsSelected(r)}
                on:click={() => focusRow(r)}
                title="Click to zoom this site on the map"
              >
                <td>
                  <div class="name-cell">
                    <b>{r.name || "Unknown"}</b>
                    {#if r.source_url}
                      <a href={r.source_url} target="_blank" rel="noreferrer" on:click|stopPropagation>Source link</a>
                    {/if}
                  </div>
                </td>
                <td>{r.operator || "Unknown"}</td>
                <td>{r.city || "N/A"}{r.state ? `, ${r.state}` : ""}{r.country ? ` (${r.country})` : ""}</td>
                <td>
                  <span class={`badge ${confidenceClass(r.confidence_band)}`}>{r.confidence_band || "Low"}</span>
                  <div class="tiny">{Number.isFinite(Number(r.confidence_score)) ? `${r.confidence_score}/100` : "N/A"}</div>
                </td>
                <td>
                  <div>{fmtNum(r.estimated_mw, 1)} MW</div>
                  <div class="tiny">
                    {Math.round((r.building_size_low_sqft || 0) / 1000)}k-{Math.round((r.building_size_high_sqft || 0) / 1000)}k sqft
                  </div>
                </td>
                <td>
                  <div>Carriers: {Number.isFinite(r.carrier_count) ? r.carrier_count : "N/A"}</div>
                  <div class="tiny">IX: {Number.isFinite(r.ix_count) ? r.ix_count : "N/A"}</div>
                </td>
                <td>{r.provider_family || "Other/Unknown"}</td>
                <td>
                  <div>{sourceTierLabel(r.source_tier)}</div>
                  <div class="tiny">{(r.source_systems || []).join(" + ")}</div>
                </td>
              </tr>
            {/each}
          {:else}
            <tr>
              <td colspan="8">No records match the current filters.</td>
            </tr>
          {/if}
        </tbody>
      </table>
    </div>
    {#if canLoadMore}
      <button on:click={() => (limit += 200)}>Load 200 more</button>
    {/if}
  {/if}
</section>

<section class="sources">
  <h3>Data Sources</h3>
  <ul>
    <li class="meta-row">
      {#if registryMeta}
        Metadata count snapshot: IL {registryMeta.illinois_count}, Global {registryMeta.global_count}
      {:else}
        Metadata count snapshot: loading...
      {/if}
    </li>
    <li>PeeringDB facilities API (global baseline, open registry)</li>
    <li>OpenStreetMap Overpass (`data_center` tags) for Illinois augmentation (open registry)</li>
    <li>SoReMo curated Illinois site records</li>
    <li>Official cloud-provider region pages (AWS, Azure, Google Cloud, Meta) as a separate verified layer</li>
    <li>Optional `open_registry_supplemental.geojson` support is enabled for additional license-eligible open registries</li>
  </ul>
</section>

<style>
  h2 {
    margin: 0 0 6px;
    font-size: clamp(30px, 4vw, 42px);
    color: #13365c;
    letter-spacing: -0.02em;
  }

  .subtitle {
    margin: 0 0 12px;
    color: #345b85;
  }

  .toolbar {
    display: grid;
    grid-template-columns: repeat(3, minmax(180px, 1fr));
    gap: 10px;
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #cadef6;
    border-radius: 12px;
    padding: 12px;
  }

  label {
    display: grid;
    gap: 6px;
    color: #224a75;
    font-weight: 600;
    font-size: 13px;
  }

  .checkbox-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-top: 20px;
    font-weight: 600;
  }

  .checkbox-row input {
    width: 16px;
    height: 16px;
  }

  select,
  input[type="text"] {
    width: 100%;
    border: 1px solid #b8cfe9;
    border-radius: 10px;
    background: #fff;
    color: #173b62;
    padding: 10px 11px;
    font-family: inherit;
    font-size: 14px;
    box-sizing: border-box;
  }

  .stats {
    margin-top: 10px;
    display: grid;
    grid-template-columns: repeat(6, minmax(130px, 1fr));
    gap: 10px;
  }

  .stats article {
    border: 1px solid #cadef6;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.9);
    padding: 10px 12px;
    display: grid;
    gap: 2px;
  }

  .stats article.stat-card {
    border-left-style: solid;
    border-left-width: 6px;
  }

  .stats article.stat-deduped {
    border-color: #9bc4ef;
    border-left-color: #2382d8;
    background: #eaf4ff;
  }

  .stats article.stat-raw {
    border-color: #b9c7db;
    border-left-color: #6d89ad;
    background: #eff4fa;
  }

  .stats article.stat-merged {
    border-color: #efcd9b;
    border-left-color: #d8892b;
    background: #fff4e3;
  }

  .stats article.stat-confidence {
    border-color: #a9dcbf;
    border-left-color: #2f9a6f;
    background: #e8f9ef;
  }

  .stats article.stat-highshare {
    border-color: #9fded8;
    border-left-color: #1fa59a;
    background: #e7f8f6;
  }

  .stats article.stat-verified {
    border-color: #cbbcf7;
    border-left-color: #7d60d8;
    background: #f1ecff;
  }

  .stats article.stat-deduped b { color: #1a5fa8; }
  .stats article.stat-raw b { color: #3e5f86; }
  .stats article.stat-merged b { color: #a66516; }
  .stats article.stat-confidence b { color: #1d7c53; }
  .stats article.stat-highshare b { color: #147a70; }
  .stats article.stat-verified b { color: #5a3eb0; }

  .stats article.stat-card span {
    color: #254f7f;
  }

  .stats b {
    font-size: 24px;
    color: #113a63;
  }

  .stats span {
    color: #3b618a;
    font-size: 13px;
  }

  .metric-help {
    margin-top: 1px;
    color: #5a799b;
    font-size: 11.5px;
    line-height: 1.3;
    font-weight: 500;
  }

  .split {
    margin-top: 10px;
    display: grid;
    grid-template-columns: repeat(2, minmax(240px, 1fr));
    gap: 10px;
    align-items: start;
  }

  .map-card {
    margin-top: 10px;
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #cadef6;
    border-radius: 12px;
    padding: 12px;
  }

  .map-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .map-head h3 {
    margin: 0;
    color: #173d68;
    font-size: 20px;
  }

  .map-head button {
    margin-top: 0;
  }

  .map-shell {
    border: 1px solid #d9e6f7;
    border-radius: 10px;
    overflow: hidden;
    background: #f5faff;
  }

  .cluster-legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 14px;
    margin: 0 0 10px;
    padding: 8px 10px;
    border: 1px solid #d4e3f5;
    border-radius: 10px;
    background: #f8fbff;
    color: #2b4f75;
    font-size: 12px;
  }

  .legend-title {
    font-weight: 700;
    color: #1c4775;
  }

  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .legend-dot {
    width: 12px;
    height: 12px;
    border-radius: 999px;
    border: 1px solid #dceaff;
    display: inline-block;
    flex: 0 0 auto;
  }

  .legend-dot.light { background: #2b7de5; }
  .legend-dot.mid { background: #1f5cad; }
  .legend-dot.dark { background: #153f76; }
  .legend-dot.aws { background: #ff9900; }
  .legend-dot.azure { background: #0078d4; }
  .legend-dot.gcp { background: #34a853; }
  .legend-dot.meta { background: #4267b2; }

  .registry-map {
    width: 100%;
    height: 420px;
  }

  .card {
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #cadef6;
    border-radius: 12px;
    padding: 12px;
    height: fit-content;
  }

  .card h3,
  .table-card h3,
  .sources h3 {
    margin: 0 0 8px;
    color: #173d68;
    font-size: 20px;
  }

  .card ul,
  .sources ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 6px;
  }

  .card li {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 10px;
    border: 1px solid #d8e5f5;
    border-radius: 8px;
    padding: 7px 9px;
    color: #284f79;
    background: #f8fbff;
  }

  .mix-row > div {
    display: grid;
    gap: 2px;
  }

  .card li.mix-row {
    border-left-style: solid;
    border-left-width: 6px;
  }

  .card li.mix-official {
    border-color: #a9c2eb;
    border-left-color: #3368c3;
    background: #eef4ff;
  }

  .card li.mix-open {
    border-color: #a8d9be;
    border-left-color: #2f9a6f;
    background: #ebf9f1;
  }

  .card li.mix-curated {
    border-color: #ccb8ef;
    border-left-color: #8c66c7;
    background: #f4efff;
  }

  .card li.mix-filtered {
    border-color: #efcf9d;
    border-left-color: #d8892b;
    background: #fff5e8;
  }

  .sources li {
    border: 1px solid #d8e5f5;
    border-radius: 8px;
    padding: 8px 10px;
    color: #284f79;
    background: #f8fbff;
    font-size: 13px;
  }

  .sources li.meta-row {
    background: #eaf3ff;
    border-color: #c9dcf3;
    color: #174777;
    font-weight: 700;
  }

  .card li b {
    color: #123b66;
  }

  .plain-steps {
    margin: 0;
    padding-left: 18px;
    display: grid;
    gap: 8px;
  }

  .plain-steps li {
    color: #284f79;
    border: 1px solid #d8e5f5;
    border-radius: 8px;
    background: #f8fbff;
    padding: 8px 10px;
  }

  .plain-steps li b {
    display: block;
    margin-bottom: 3px;
    color: #173f69;
  }

  .mini-note {
    margin-top: 8px;
    border: 1px dashed #b8cfe8;
    background: #f3f8ff;
    color: #2b537c;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 12.5px;
    line-height: 1.35;
  }

  .table-card,
  .sources {
    margin-top: 10px;
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #cadef6;
    border-radius: 12px;
    padding: 12px;
  }

  .records-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
  }

  .collapse-btn {
    margin-top: 0;
    padding: 8px 11px;
  }

  .hint {
    margin: 0 0 8px;
    color: #456a91;
    font-size: 13px;
  }

  .tiny {
    color: #53749b;
    font-size: 12px;
  }

  .badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.2;
  }

  .badge.high {
    background: #dff6ea;
    color: #0f6949;
  }

  .badge.medium {
    background: #e4eefc;
    color: #1d4f9f;
  }

  .badge.low {
    background: #fff0df;
    color: #8f4f12;
  }

  .error-hint {
    color: #8f1f1f;
    font-weight: 700;
  }

  .data-error {
    margin-top: 10px;
    border: 1px solid #efc7c7;
    background: #fff1f1;
    color: #7a1f1f;
    border-radius: 10px;
    padding: 8px 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 13px;
  }

  .retry-btn {
    margin-top: 0;
    padding: 7px 10px;
    background: #ffe4e4;
    border-color: #efb7b7;
    color: #7a1f1f;
  }

  .table-wrap {
    overflow: auto;
    border: 1px solid #d9e6f7;
    border-radius: 10px;
    background: #fff;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    min-width: 1120px;
  }

  th,
  td {
    text-align: left;
    padding: 9px 10px;
    border-bottom: 1px solid #ebf1f9;
    color: #234c76;
    vertical-align: top;
    font-size: 13px;
  }

  tbody tr {
    cursor: pointer;
  }

  tbody tr:hover {
    background: #f4f9ff;
  }

  tbody tr.selected {
    background: #e7f1ff;
  }

  thead th {
    position: sticky;
    top: 0;
    background: #f2f8ff;
    color: #173d68;
    z-index: 1;
  }

  .name-cell {
    display: grid;
    gap: 4px;
  }

  .name-cell b {
    color: #143860;
  }

  .name-cell a {
    color: #0e73b9;
    font-size: 12px;
    text-decoration: none;
  }

  button {
    margin-top: 10px;
    border: 1px solid #9ebbe0;
    border-radius: 10px;
    background: #e7f1ff;
    color: #1b446f;
    padding: 9px 12px;
    font-family: inherit;
    font-weight: 700;
    cursor: pointer;
  }

  :global(.registry-popup-shell .maplibregl-popup-content) {
    padding: 0;
    position: relative;
    width: min(340px, calc(100vw - 64px));
    max-width: calc(100vw - 32px);
    box-sizing: border-box;
    border-radius: 14px;
    background: transparent;
    border: none;
    box-shadow: none;
    overflow: hidden;
  }

  :global(.registry-popup-shell.maplibregl-popup-anchor-top .maplibregl-popup-tip) {
    border-bottom-color: #ffffff;
  }

  :global(.registry-popup-shell.maplibregl-popup-anchor-bottom .maplibregl-popup-tip) {
    border-top-color: #ffffff;
  }

  :global(.registry-popup-shell.maplibregl-popup-anchor-left .maplibregl-popup-tip) {
    border-right-color: #ffffff;
  }

  :global(.registry-popup-shell.maplibregl-popup-anchor-right .maplibregl-popup-tip) {
    border-left-color: #ffffff;
  }

  :global(.registry-popup-shell .maplibregl-popup-close-button) {
    position: absolute !important;
    top: 8px;
    right: 8px;
    margin: 0 !important;
    width: 24px;
    height: 24px;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    border: 1px solid #cadef6;
    background: #f2f8ff;
    color: #33577f;
    font-size: 18px;
    line-height: 20px;
    transform: none !important;
    z-index: 3;
  }

  :global(.registry-popup-shell .maplibregl-popup-close-button:hover) {
    background: #e6f1ff;
    color: #173f67;
  }

  :global(.registry-popup-card) {
    width: 100%;
    min-width: 0;
    max-width: 100%;
    display: grid;
    gap: 6px;
    padding: 14px 14px 12px;
    padding-right: 44px;
    border-radius: 14px;
    border: 1px solid #cadef6;
    background: #ffffff;
    color: #173a62;
    box-shadow: 0 12px 28px rgba(14, 47, 88, 0.18);
    line-height: 1.35;
    font-size: 13px;
    box-sizing: border-box;
  }

  :global(.registry-popup-title) {
    font-weight: 800;
    font-size: 19px;
    letter-spacing: -0.01em;
    color: #123a65;
    margin-bottom: 2px;
    margin-right: 6px;
  }

  :global(.registry-popup-card .k) {
    font-weight: 700;
    color: #1f4f7f;
  }

  :global(.registry-popup-link) {
    margin-top: 2px;
    color: #0b6fc2;
    text-decoration: none;
    font-weight: 700;
    width: fit-content;
  }

  :global(.registry-popup-link:hover) {
    text-decoration: underline;
  }

  @media (max-width: 1280px) {
    .toolbar,
    .stats {
      grid-template-columns: repeat(2, minmax(180px, 1fr));
    }

    .split {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 680px) {
    .toolbar,
    .stats {
      grid-template-columns: 1fr;
    }

    .registry-map {
      height: 340px;
    }
  }
</style>
