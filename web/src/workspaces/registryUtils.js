export const DEDUPE_DISTANCE_KM = 2.2;
export const DEDUPE_THRESHOLD = 0.78;

const STOP_WORDS = new Set([
  "data",
  "center",
  "centers",
  "datacenter",
  "datacenters",
  "facility",
  "facilities",
  "site",
  "campus",
  "the",
  "and",
  "dc",
  "llc",
  "inc",
  "corp",
  "corporation",
]);

const OFFICIAL_DOMAIN_TOKENS = [
  "aws.amazon.com",
  "azure.microsoft.com",
  "cloud.google.com",
  "datacenters.atmeta.com",
  "google.com",
  "microsoft.com",
  "amazon.com",
  "meta.com",
];

const HYPERSCALE_TOKENS = ["amazon", "aws", "microsoft", "azure", "google", "meta"];

export const norm = (v) => String(v ?? "").trim();
export const upper = (v) => norm(v).toUpperCase();
export const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export const featuresFrom = (geojson) => (Array.isArray(geojson?.features) ? geojson.features : []);

export const fmtNum = (v, d = 1) => (Number.isFinite(Number(v)) ? Number(v).toFixed(d).replace(/\.?0+$/, "") : "N/A");

const slug = (v) =>
  norm(v)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

function valueTokens(value) {
  return slug(value)
    .split(" ")
    .filter((t) => t.length > 1 && !STOP_WORDS.has(t));
}

function tokenSimilarity(a, b) {
  const aa = valueTokens(a);
  const bb = valueTokens(b);
  if (!aa.length || !bb.length) return 0;
  const setA = new Set(aa);
  const setB = new Set(bb);
  let intersection = 0;
  for (const t of setA) {
    if (setB.has(t)) intersection += 1;
  }
  const union = new Set([...setA, ...setB]).size;
  return union ? intersection / union : 0;
}

function decimalPlaces(rawValue) {
  const s = String(rawValue ?? "").trim();
  if (!s.includes(".")) return 0;
  const frac = s.split(".")[1]?.replace(/[^0-9]/g, "") ?? "";
  const trimmed = frac.replace(/0+$/, "");
  return trimmed.length;
}

function coordinatePrecisionScore(latRaw, lonRaw) {
  const d = Math.min(decimalPlaces(latRaw), decimalPlaces(lonRaw));
  if (d >= 5) return 1;
  if (d === 4) return 0.92;
  if (d === 3) return 0.82;
  if (d === 2) return 0.66;
  if (d === 1) return 0.46;
  return 0.26;
}

function domainFromUrl(url) {
  const raw = norm(url);
  if (!raw) return "";
  try {
    return new URL(raw).hostname.toLowerCase();
  } catch {
    return "";
  }
}

export function isOfficialSource(row) {
  const domains = [domainFromUrl(row?.source_url), domainFromUrl(row?.website)].filter(Boolean);
  if ((row?.source_system || "").toLowerCase().includes("official")) return true;
  return domains.some((host) => OFFICIAL_DOMAIN_TOKENS.some((token) => host.includes(token)));
}

function sourceQualityScore(row) {
  if (isOfficialSource(row)) return 1;
  const source = norm(row?.source_system).toLowerCase();
  if (source.includes("peeringdb")) return 0.82;
  if (source.includes("openstreetmap") || source.includes("overpass")) return 0.72;
  if (source.includes("curated")) return 0.7;
  return 0.58;
}

export function sourceTier(row) {
  if (isOfficialSource(row)) return "official";
  const source = norm(row?.source_system).toLowerCase();
  if (source.includes("peeringdb") || source.includes("openstreetmap") || source.includes("overpass")) return "open";
  if (source.includes("curated")) return "curated";
  return "other";
}

export function sourceTierLabel(tier) {
  if (tier === "official") return "Official";
  if (tier === "open") return "Open registry";
  if (tier === "curated") return "Curated";
  return "Other";
}

export function confidenceBandFromScore(score) {
  const n = Number(score);
  if (!Number.isFinite(n)) return "Low";
  if (n >= 75) return "High";
  if (n >= 55) return "Medium";
  return "Low";
}

export function confidenceClass(band) {
  if (band === "High") return "high";
  if (band === "Medium") return "medium";
  return "low";
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (v) => (v * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return 6371 * c;
}

export function normalizeProviderFamily(row) {
  const base = norm(row.provider_family).toLowerCase();
  const op = norm(row.operator).toLowerCase();
  const name = norm(row.name).toLowerCase();
  const text = `${base} ${op} ${name}`;
  if (text.includes("amazon") || text.includes("aws")) return "Amazon AWS";
  if (text.includes("azure") || text.includes("microsoft")) return "Microsoft Azure";
  if (text.includes("google")) return "Google Cloud";
  if (text.includes("meta")) return "Meta";
  if (text.includes("equinix")) return "Equinix";
  if (text.includes("digital realty")) return "Digital Realty";
  if (text.includes("qts")) return "QTS";
  return norm(row.provider_family) || "Other/Unknown";
}

export function rowRegistryId(row) {
  return String(
    row?.registry_id ||
    row?.source_record_id ||
    `${norm(row?.name)}|${norm(row?.latitude)}|${norm(row?.longitude)}`
  );
}

export function rowsFromGeojson(geojson, origin = "") {
  const rows = [];
  for (const [idx, feature] of featuresFrom(geojson).entries()) {
    if (!feature || typeof feature !== "object") continue;
    const p = feature.properties || {};
    const coords = Array.isArray(feature.geometry?.coordinates) ? feature.geometry.coordinates : [];
    const lonRaw = p.longitude ?? coords[0];
    const latRaw = p.latitude ?? coords[1];
    const lon = num(lonRaw);
    const lat = num(latRaw);
    const name =
      norm(p.name) ||
      norm(p.fac_name) ||
      norm(p.site_name) ||
      norm(p.operator) ||
      `Registry site ${idx + 1}`;

    const row = {
      registry_id: norm(p.registry_id),
      source_record_id: norm(p.source_record_id),
      name,
      operator: norm(p.operator) || "Unknown",
      address: norm(p.address) || norm(p.street_address) || norm(p.location),
      city: norm(p.city),
      state: norm(p.state),
      country: norm(p.country),
      region_continent: norm(p.region_continent),
      provider_family: norm(p.provider_family) || "Other/Unknown",
      status: norm(p.status),
      source_system: norm(p.source_system) || origin || "Unknown",
      source_url: norm(p.source_url),
      website: norm(p.website),
      record_scope: norm(p.record_scope),
      is_us: num(p.is_us),
      is_illinois: num(p.is_illinois),
      net_count: num(p.net_count),
      ix_count: num(p.ix_count),
      carrier_count: num(p.carrier_count),
      latitude: lat,
      longitude: lon,
      lat_raw: latRaw,
      lon_raw: lonRaw,
    };
    row.provider_family = normalizeProviderFamily(row);
    rows.push(row);
  }
  return rows;
}

export function verifiedRowsFromGeojson(geojson) {
  return featuresFrom(geojson)
    .map((feature) => {
      const p = feature?.properties || {};
      const coords = Array.isArray(feature?.geometry?.coordinates) ? feature.geometry.coordinates : [];
      const lon = num(coords[0]);
      const lat = num(coords[1]);
      if (lat === null || lon === null) return null;
      return {
        region_id: norm(p.region_id) || `${norm(p.provider_family)}-${norm(p.region_name)}`,
        region_name: norm(p.region_name) || "Cloud Region",
        provider_family: normalizeProviderFamily({
          provider_family: norm(p.provider_family),
          operator: norm(p.provider_family),
          name: norm(p.region_name),
        }),
        city: norm(p.city),
        state: norm(p.state),
        country: norm(p.country),
        source_system: norm(p.source_system) || "Official Cloud Region Page",
        source_url: norm(p.source_url),
        latitude: lat,
        longitude: lon,
      };
    })
    .filter(Boolean);
}

function candidateBucketKeys(row) {
  const loc = `${upper(row.country)}|${upper(row.state)}|${slug(row.city).slice(0, 16)}`;
  const keys = [
    `n:${slug(row.name).slice(0, 22)}|${loc}`,
    `o:${slug(row.operator).slice(0, 22)}|${loc}`,
  ];
  const addr = slug(row.address);
  if (addr) keys.push(`a:${addr.slice(0, 30)}|${loc}`);
  if (row.latitude !== null && row.longitude !== null) {
    keys.push(`g2:${loc}|${row.latitude.toFixed(2)}|${row.longitude.toFixed(2)}`);
    keys.push(`g1:${loc}|${row.latitude.toFixed(1)}|${row.longitude.toFixed(1)}`);
  }
  if (norm(row.registry_id)) keys.push(`id:${norm(row.registry_id)}`);
  return Array.from(new Set(keys));
}

function dedupeScore(a, b) {
  if (upper(a.country) && upper(b.country) && upper(a.country) !== upper(b.country)) return 0;
  const nameSim = tokenSimilarity(a.name, b.name);
  const opSim = tokenSimilarity(a.operator, b.operator);
  const addrSim = tokenSimilarity(a.address, b.address);
  if (nameSim < 0.45 && opSim < 0.5) return 0;
  const sameCity = slug(a.city) && slug(a.city) === slug(b.city) ? 1 : 0;
  const sameState = upper(a.state) && upper(a.state) === upper(b.state) ? 1 : 0;

  let dist = null;
  if (a.latitude !== null && a.longitude !== null && b.latitude !== null && b.longitude !== null) {
    dist = haversineKm(a.latitude, a.longitude, b.latitude, b.longitude);
    if (dist > 4 && nameSim < 0.92 && opSim < 0.92) return 0;
  }

  const distScore =
    dist === null ? 0.55 :
    dist <= 0.4 ? 1 :
    dist <= 1.0 ? 0.9 :
    dist <= DEDUPE_DISTANCE_KM ? 0.75 :
    0.25;

  const score =
    nameSim * 0.44 +
    opSim * 0.14 +
    addrSim * 0.12 +
    sameCity * 0.16 +
    Math.max(sameState, 0.5) * 0.04 +
    distScore * 0.1;
  return Number(score.toFixed(4));
}

function preferText(current, incoming) {
  if (!norm(current)) return norm(incoming);
  if (!norm(incoming)) return norm(current);
  return norm(incoming).length > norm(current).length ? norm(incoming) : norm(current);
}

function maxNum(a, b) {
  const aa = num(a);
  const bb = num(b);
  if (aa === null) return bb;
  if (bb === null) return aa;
  return Math.max(aa, bb);
}

function initAggregate(row) {
  return {
    ...row,
    _rows: [row],
    _sourceSystems: new Set([norm(row.source_system) || "Unknown"]),
    _sourceUrls: new Set(norm(row.source_url) ? [norm(row.source_url)] : []),
    _registryIds: new Set(norm(row.registry_id) ? [norm(row.registry_id)] : []),
    _recordIds: new Set(norm(row.source_record_id) ? [norm(row.source_record_id)] : []),
    _nameVariants: new Set(norm(row.name) ? [norm(row.name)] : []),
    _bestPrecision: coordinatePrecisionScore(row.lat_raw, row.lon_raw),
  };
}

function mergeAggregate(base, row) {
  base._rows.push(row);
  base._sourceSystems.add(norm(row.source_system) || "Unknown");
  if (norm(row.source_url)) base._sourceUrls.add(norm(row.source_url));
  if (norm(row.registry_id)) base._registryIds.add(norm(row.registry_id));
  if (norm(row.source_record_id)) base._recordIds.add(norm(row.source_record_id));
  if (norm(row.name)) base._nameVariants.add(norm(row.name));

  base.name = preferText(base.name, row.name);
  base.operator = preferText(base.operator, row.operator);
  base.address = preferText(base.address, row.address);
  base.city = preferText(base.city, row.city);
  base.state = preferText(base.state, row.state);
  base.country = preferText(base.country, row.country);
  base.provider_family = normalizeProviderFamily({
    provider_family: preferText(base.provider_family, row.provider_family),
    operator: preferText(base.operator, row.operator),
    name: preferText(base.name, row.name),
  });
  base.source_system = preferText(base.source_system, row.source_system);
  base.source_url = preferText(base.source_url, row.source_url);
  base.website = preferText(base.website, row.website);
  base.status = preferText(base.status, row.status);
  base.record_scope = preferText(base.record_scope, row.record_scope);
  base.region_continent = preferText(base.region_continent, row.region_continent);

  base.net_count = maxNum(base.net_count, row.net_count);
  base.ix_count = maxNum(base.ix_count, row.ix_count);
  base.carrier_count = maxNum(base.carrier_count, row.carrier_count);
  base.is_us = maxNum(base.is_us, row.is_us);
  base.is_illinois = maxNum(base.is_illinois, row.is_illinois);

  const incomingPrecision = coordinatePrecisionScore(row.lat_raw, row.lon_raw);
  if (base.latitude === null || base.longitude === null || incomingPrecision > base._bestPrecision) {
    base.latitude = row.latitude;
    base.longitude = row.longitude;
    base.lat_raw = row.lat_raw;
    base.lon_raw = row.lon_raw;
    base._bestPrecision = incomingPrecision;
  }
}

function estimateCapacityMw(row) {
  let signal = 0;
  if (row.carrier_count !== null) signal += row.carrier_count * 0.45;
  if (row.ix_count !== null) signal += row.ix_count * 0.9;
  if (row.net_count !== null) signal += Math.log1p(Math.max(0, row.net_count)) * 1.8;
  if (signal === 0) signal = 3.5;
  const providerText = `${norm(row.provider_family)} ${norm(row.operator)} ${norm(row.name)}`.toLowerCase();
  const isHyperscale = HYPERSCALE_TOKENS.some((t) => providerText.includes(t));
  if (isHyperscale) signal *= 1.8;
  if (providerText.includes("equinix") || providerText.includes("digital realty") || providerText.includes("qts")) signal *= 1.35;
  return Number(Math.min(320, Math.max(1.5, signal)).toFixed(1));
}

export function dedupeRegistryRows(rawRows) {
  const cleanRows = rawRows.filter((row) => row.latitude !== null && row.longitude !== null);
  const deduped = [];
  const buckets = new Map();
  let mergedVariants = 0;
  let fuzzyMatchCount = 0;

  for (const row of cleanRows) {
    const keys = candidateBucketKeys(row);
    const candidateIndices = new Set();
    for (const key of keys) {
      const list = buckets.get(key);
      if (!list) continue;
      for (const idx of list) candidateIndices.add(idx);
    }

    let bestIdx = -1;
    let bestScore = 0;
    for (const idx of candidateIndices) {
      const score = dedupeScore(row, deduped[idx]);
      if (score > bestScore) {
        bestScore = score;
        bestIdx = idx;
      }
    }

    if (bestIdx >= 0 && bestScore >= DEDUPE_THRESHOLD) {
      mergeAggregate(deduped[bestIdx], row);
      mergedVariants += 1;
      if (bestScore < 0.97) fuzzyMatchCount += 1;
    } else {
      const agg = initAggregate(row);
      deduped.push(agg);
      const idx = deduped.length - 1;
      for (const key of keys) {
        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key).push(idx);
      }
    }
  }

  const rows = deduped.map((agg) => {
    const sourceSystems = Array.from(agg._sourceSystems).filter(Boolean);
    const sourceUrls = Array.from(agg._sourceUrls).filter(Boolean);
    const multiSourceScore = sourceSystems.length >= 3 ? 1 : sourceSystems.length === 2 ? 0.86 : 0.62;
    const srcScore = sourceQualityScore(agg);
    const coordScore = coordinatePrecisionScore(agg.lat_raw, agg.lon_raw);
    const confidenceScore = Math.round((srcScore * 0.5 + coordScore * 0.25 + multiSourceScore * 0.25) * 100);
    const confidenceBand = confidenceBandFromScore(confidenceScore);
    const estimatedMw = estimateCapacityMw(agg);
    const tier = sourceTier(agg);
    return {
      ...agg,
      provider_family: normalizeProviderFamily(agg),
      source_systems: sourceSystems,
      source_urls: sourceUrls,
      source_system: sourceSystems.join(" + "),
      source_url: sourceUrls[0] || norm(agg.source_url),
      source_tier: tier,
      source_tier_label: sourceTierLabel(tier),
      match_count: agg._rows.length,
      merged_name_variants: Array.from(agg._nameVariants).slice(0, 4),
      confidence_score: confidenceScore,
      confidence_band: confidenceBand,
      confidence_class: confidenceClass(confidenceBand),
      coordinate_precision_score: Number(coordScore.toFixed(2)),
      estimated_mw: estimatedMw,
      building_size_low_sqft: Math.round(estimatedMw * 5500),
      building_size_high_sqft: Math.round(estimatedMw * 12000),
    };
  });

  return {
    rows,
    stats: {
      rawCount: cleanRows.length,
      dedupedCount: rows.length,
      mergedVariants,
      fuzzyMatchCount,
    },
  };
}

export function registryFeatureCollection(rowsIn) {
  return {
    type: "FeatureCollection",
    features: rowsIn
      .map((r, idx) => {
        const lat = num(r.latitude);
        const lon = num(r.longitude);
        if (lat === null || lon === null) return null;
        return {
          type: "Feature",
          id: idx + 1,
          geometry: { type: "Point", coordinates: [lon, lat] },
          properties: {
            row_key: rowRegistryId(r) || `row-${idx + 1}`,
            registry_id: norm(r.registry_id),
            source_record_id: norm(r.source_record_id),
            name: norm(r.name) || "Unknown",
            operator: norm(r.operator) || "Unknown",
            address: norm(r.address),
            city: norm(r.city),
            state: norm(r.state),
            country: norm(r.country),
            provider_family: norm(r.provider_family) || "Other/Unknown",
            source_system: norm(r.source_system) || "Unknown",
            source_url: norm(r.source_url),
            confidence_band: norm(r.confidence_band),
            confidence_score: num(r.confidence_score),
            estimated_mw: num(r.estimated_mw),
            carrier_count: num(r.carrier_count),
            ix_count: num(r.ix_count),
            source_tier_label: norm(r.source_tier_label),
          },
        };
      })
      .filter(Boolean),
  };
}

export function verifiedFeatureCollection(rowsIn) {
  return {
    type: "FeatureCollection",
    features: rowsIn
      .map((r, idx) => ({
        type: "Feature",
        id: `verified-${idx + 1}`,
        geometry: { type: "Point", coordinates: [r.longitude, r.latitude] },
        properties: {
          region_id: norm(r.region_id),
          region_name: norm(r.region_name),
          provider_family: norm(r.provider_family),
          city: norm(r.city),
          state: norm(r.state),
          country: norm(r.country),
          source_system: norm(r.source_system),
          source_url: norm(r.source_url),
        },
      }))
      .filter(Boolean),
  };
}
