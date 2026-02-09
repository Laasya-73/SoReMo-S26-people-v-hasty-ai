from __future__ import annotations

import pandas as pd
import geopandas as gpd
import folium


def _safe_text(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    return str(val)


def _minmax(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().empty:
        return s
    mn = float(s.min())
    mx = float(s.max())
    if mx == mn:
        return s * 0
    return (s - mn) / (mx - mn)


def _compute_impact_score(counties: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Composite vulnerability score (0..100).
    Higher poverty + higher minority percentage => higher score.
    Weights are adjustable.
    """
    c = counties.copy()

    if "Poverty_Rate_Percent" not in c.columns:
        c["Poverty_Rate_Percent"] = pd.NA
    if "Pct_Minority" not in c.columns:
        c["Pct_Minority"] = pd.NA

    pov_n = _minmax(c["Poverty_Rate_Percent"])
    min_n = _minmax(c["Pct_Minority"])

    # Weighting: poverty slightly higher weight
    score_0_1 = 0.55 * pov_n + 0.45 * min_n
    c["Impact_Score"] = (score_0_1 * 100).round(1)

    return c


def add_dashed_cluster_circle(
    fg: folium.FeatureGroup,
    center: list[float],
    radius_m: int,
    label: str,
    color: str = "purple",
) -> None:
    folium.Circle(
        location=center,
        radius=radius_m,
        popup=label,
        color=color,
        weight=2,
        dash_array="6,10",
        fill=True,
        fill_opacity=0.10,
    ).add_to(fg)


def _inject_layercontrol_css(m: folium.Map) -> None:
    css = """
    <style>
      .leaflet-top.leaflet-right {
        top: 12px !important;
        right: 12px !important;
      }

      .leaflet-control-layers {
        min-width: 320px !important;
        max-width: 360px !important;
        max-height: 320px !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        font-size: 14px !important;
        line-height: 1.25 !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.12) !important;
      }

      .leaflet-control-layers label {
        display: flex !important;
        align-items: flex-start !important;
        gap: 8px !important;
        white-space: normal !important;
        word-break: break-word !important;
      }

      .leaflet-control-layers input[type="checkbox"] {
        margin-top: 2px !important;
      }
    </style>
    """
    m.get_root().header.add_child(folium.Element(css))


def build_illinois_map(
    sites: pd.DataFrame,
    counties_layer: gpd.GeoDataFrame | None = None,
    center: list[float] | None = None,
    zoom_start: int = 7,
) -> folium.Map:
    """
    Build Folium map for the People v. Hasty AI Development project.

    Includes:
    - Base map
    - Optional county layers:
        * Community Impact Score (0–100) (default ON when counties_layer provided)
        * Poverty choropleth (toggle)
        * Minority choropleth (toggle)
        * County hover tooltips (toggle)
    - Impact clusters (dashed circles)
    - Data center pins (no clustering, no numbers)
    """
    if center is None:
        center = [40.0, -89.2]

    df = sites.copy()

    # Normalize layer values
    if "layer" in df.columns:
        df["layer"] = df["layer"].astype(str).str.strip().str.lower()

    # Clean coords
    df = df.dropna(subset=["lat", "lon"])
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    # Base map
    m = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles=None,
        control_scale=True,
        width="100%",
        height="560px",
    )

    folium.TileLayer(
        tiles="CartoDB Voyager",
        name="Base Map",
        control=False,
    ).add_to(m)

    _inject_layercontrol_css(m)

    # --- County context layers ---
    if counties_layer is not None and not counties_layer.empty:
        cl = counties_layer.copy()

        # Ensure GEOID is a string for choropleth joins
        if "GEOID" in cl.columns:
            cl["GEOID"] = cl["GEOID"].astype(str)

        # County name used in tooltip (if present)
        if "NAME" not in cl.columns and "name" in cl.columns:
            cl["NAME"] = cl["name"]

        # Compute Impact Score
        cl = _compute_impact_score(cl)

        # Impact Score choropleth (most important for "high vs low")
        folium.Choropleth(
            geo_data=cl,
            name="Community Impact Score (0–100)",
            data=cl,
            columns=["GEOID", "Impact_Score"],
            key_on="feature.properties.GEOID",
            fill_color="RdYlGn_r",  # red = high impact
            fill_opacity=0.78,
            line_opacity=0.05,
            legend_name="Community Impact Score (higher = more vulnerable)",
            show=True,
            highlight=False,
        ).add_to(m)

        # Poverty layer (toggle)
        if "Poverty_Rate_Percent" in cl.columns:
            folium.Choropleth(
                geo_data=cl,
                name="County Poverty Rate (%)",
                data=cl,
                columns=["GEOID", "Poverty_Rate_Percent"],
                key_on="feature.properties.GEOID",
                fill_color="YlOrRd",
                fill_opacity=0.70,
                line_opacity=0.05,
                legend_name="County Poverty Rate (%)",
                show=False,
                highlight=False,
            ).add_to(m)

        # Minority layer (toggle)
        if "Pct_Minority" in cl.columns:
            folium.Choropleth(
                geo_data=cl,
                name="County Minority Population (%)",
                data=cl,
                columns=["GEOID", "Pct_Minority"],
                key_on="feature.properties.GEOID",
                fill_color="Purples",
                fill_opacity=0.70,
                line_opacity=0.05,
                legend_name="County Minority Population (%)",
                show=False,
                highlight=False,
            ).add_to(m)

        # Hover tooltips layer (transparent GeoJson)
        tooltip_fg = folium.FeatureGroup(name="County Hover Details", show=True)
        tooltip_fields = []
        tooltip_aliases = []

        # Only include fields that exist
        if "NAME" in cl.columns:
            tooltip_fields.append("NAME")
            tooltip_aliases.append("County")
        if "Impact_Score" in cl.columns:
            tooltip_fields.append("Impact_Score")
            tooltip_aliases.append("Impact Score (0–100)")
        if "Poverty_Rate_Percent" in cl.columns:
            tooltip_fields.append("Poverty_Rate_Percent")
            tooltip_aliases.append("Poverty Rate (%)")
        if "Pct_Minority" in cl.columns:
            tooltip_fields.append("Pct_Minority")
            tooltip_aliases.append("Minority Population (%)")

        folium.GeoJson(
            cl,
            name="County Details",
            style_function=lambda _: {"fillOpacity": 0, "color": "transparent"},
            tooltip=folium.GeoJsonTooltip(
                fields=tooltip_fields,
                aliases=tooltip_aliases,
                localize=True,
                sticky=True,
                labels=True,
            ),
        ).add_to(tooltip_fg)

        tooltip_fg.add_to(m)

    # --- Impact clusters layer ---
    impact_clusters = folium.FeatureGroup(name="Impact Clusters", show=True)
    add_dashed_cluster_circle(
        impact_clusters,
        center=[42.000, -87.970],
        radius_m=6000,
        label="Elk Grove Village cluster: multiple existing + proposed sites",
    )
    add_dashed_cluster_circle(
        impact_clusters,
        center=[41.864, -87.631],
        radius_m=4500,
        label="Chicago core cluster: interconnection hubs + dense urban facilities",
    )
    add_dashed_cluster_circle(
        impact_clusters,
        center=[41.865, -88.751],
        radius_m=9000,
        label="DeKalb area cluster: campus expansion + approved proposal corridor",
    )
    impact_clusters.add_to(m)

    # --- Site layers (pins, no clustering) ---
    layer_existing = folium.FeatureGroup(name="Existing Data Centers", show=True)
    layer_proposed = folium.FeatureGroup(name="Proposed / Under Development", show=True)
    layer_denied = folium.FeatureGroup(name="Rejected or Withdrawn Proposals", show=True)
    layer_inventory = folium.FeatureGroup(name="Additional Infrastructure Context", show=False)

    def add_site_marker(row, target_group: folium.FeatureGroup, color: str) -> None:
        name = _safe_text(row.get("name"))

        poverty = _safe_text(row.get("Poverty_Rate_Percent"))
        minority = _safe_text(row.get("Pct_Minority"))
        income = _safe_text(row.get("Median_Household_Income"))

        popup_html = f"""
        <div style="font-size: 12px; min-width: 220px;">
          <b>{name}</b><br>
          <b>Status:</b> {_safe_text(row.get("layer"))}<br><hr>
          <b>County Context:</b><br>
          • Poverty Rate: {poverty}%<br>
          • Median Income: ${income}<br>
          • Minority Population: {minority}%<br><br>
          <b>Surroundings Snapshot:</b> {_safe_text(row.get('surroundings_snapshot'))}<br><br>
          <b>Community Signals:</b> {_safe_text(row.get('community_signals'))}<br><br>
          <b>Stressors:</b> {_safe_text(row.get('stressors'))}<br><br>
          <b>Sources:</b> {_safe_text(row.get('sources'))}
        </div>
        """

        folium.Marker(
            location=[float(row["lat"]), float(row["lon"])],
            tooltip=name,
            popup=folium.Popup(popup_html, max_width=450),
            icon=folium.Icon(color=color, icon="info-sign", prefix="glyphicon"),
        ).add_to(target_group)

    for _, r in df.iterrows():
        layer_val = _safe_text(r.get("layer")).strip().lower()
        site_id = _safe_text(r.get("site_id"))
        layer_text_raw = _safe_text(r.get("layer"))

        is_inv = ("INV" in site_id) or ("inventory" in layer_text_raw.lower()) or ("reserve" in layer_text_raw.lower())

        if is_inv:
            name = _safe_text(r.get("name"))
            popup_inv = f"""
            <div style="font-size: 12px; min-width: 200px;">
              <b>{name}</b><br><br>
              <b>Source:</b> {_safe_text(r.get('sources'))}
            </div>
            """
            folium.Marker(
                location=[float(r["lat"]), float(r["lon"])],
                tooltip=name,
                popup=folium.Popup(popup_inv, max_width=450),
                icon=folium.Icon(color="gray", icon="info-sign", prefix="glyphicon"),
            ).add_to(layer_inventory)
            continue

        if layer_val == "existing":
            add_site_marker(r, layer_existing, "green")
        elif layer_val == "denied":
            add_site_marker(r, layer_denied, "red")
        else:
            add_site_marker(r, layer_proposed, "blue")

    layer_existing.add_to(m)
    layer_proposed.add_to(m)
    layer_denied.add_to(m)
    layer_inventory.add_to(m)

    folium.LayerControl(collapsed=False, position="topright").add_to(m)
    return m
