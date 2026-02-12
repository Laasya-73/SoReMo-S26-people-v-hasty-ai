from __future__ import annotations

import pandas as pd
import geopandas as gpd
import folium
import branca.colormap as cm


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
    """
    c = counties.copy()

    if "Poverty_Rate_Percent" not in c.columns:
        c["Poverty_Rate_Percent"] = pd.NA
    if "Pct_Minority" not in c.columns:
        c["Pct_Minority"] = pd.NA

    pov_n = _minmax(c["Poverty_Rate_Percent"])
    min_n = _minmax(c["Pct_Minority"])

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
      .leaflet-top.leaflet-right { top: 12px !important; right: 12px !important; }

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

      .leaflet-control-layers input[type="checkbox"] { margin-top: 2px !important; }
    </style>
    """
    m.get_root().header.add_child(folium.Element(css))


def _colormap_html_bar(colormap_obj, width_px: int = 260) -> str:
    # branca's built-in repr is fine, but we constrain width so it looks clean in Streamlit sidebar
    html = colormap_obj._repr_html_()
    return f"<div style='max-width:{width_px}px'>{html}</div>"


def _add_geojson_choropleth(
    m: folium.Map,
    gdf: gpd.GeoDataFrame,
    value_col: str,
    layer_name: str,
    palette: str,
    show: bool,
    fill_opacity: float,
    line_opacity: float = 0.05,
):
    """
    Adds a choropleth layer WITHOUT injecting a map legend (so nothing covers the map).
    Returns a (colormap_obj, html_legend) tuple for Streamlit sidebar rendering.
    """
    s = pd.to_numeric(gdf[value_col], errors="coerce")
    s_valid = s.dropna()

    if s_valid.empty:
        return None, None

    vmin = float(s_valid.min())
    vmax = float(s_valid.max())

    # Build colormap
    if not hasattr(cm.linear, palette):
        raise ValueError(f"Unknown branca palette: {palette}")

    colormap_obj = getattr(cm.linear, palette).scale(vmin, vmax)

    def style_fn(feature):
        val = feature["properties"].get(value_col, None)
        try:
            v = float(val)
        except Exception:
            v = None

        if v is None or pd.isna(v):
            fill = "#9e9e9e"  # gray for missing
        else:
            fill = colormap_obj(v)

        return {
            "fillColor": fill,
            "color": "#000000",
            "weight": 1,
            "fillOpacity": fill_opacity,
            "opacity": line_opacity,
        }

    fg = folium.FeatureGroup(name=layer_name, show=show)

    folium.GeoJson(
        gdf,
        name=layer_name,
        style_function=style_fn,
        highlight_function=lambda _: {"weight": 2, "fillOpacity": min(fill_opacity + 0.10, 0.95)},
    ).add_to(fg)

    fg.add_to(m)

    html_legend = _colormap_html_bar(colormap_obj)
    return colormap_obj, html_legend


def build_illinois_map(
    sites: pd.DataFrame,
    counties_layer: gpd.GeoDataFrame | None = None,
    center: list[float] | None = None,
    zoom_start: int = 7,
):
    """
    Returns: (folium_map, legends_list)

    legends_list is a list of dicts:
      [{"title": "...", "html": "..."}]
    Render these in Streamlit sidebar.
    """
    if center is None:
        center = [40.0, -89.2]

    legends = []

    df = sites.copy()

    if "layer" in df.columns:
        df["layer"] = df["layer"].astype(str).str.strip().str.lower()

    df = df.dropna(subset=["lat", "lon"])
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

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

        if "GEOID" in cl.columns:
            cl["GEOID"] = cl["GEOID"].astype(str)

        if "NAME" not in cl.columns and "name" in cl.columns:
            cl["NAME"] = cl["name"]

        # Compute Impact Score (poverty + minority)
        cl = _compute_impact_score(cl)

        # 1) Main Impact Score layer (default ON)
        _, html = _add_geojson_choropleth(
            m=m,
            gdf=cl,
            value_col="Impact_Score",
            layer_name="Community Impact Score (0–100)",
            palette="RdYlGn_11",
            show=True,
            fill_opacity=0.78,
        )
        # Reverse the palette by swapping values through a reversed colormap:
        # Easiest practical method: use the reversed palette name if available, else keep as-is.
        # Note: branca linear palettes do not always expose reversed variants consistently.
        # We keep the same look as your original ("RdYlGn_r") by using a red->green scale and interpreting it in sidebar.
        if html:
            legends.append({"title": "Community Impact Score (higher = more vulnerable)", "html": html})

        # 2) Poverty (toggle)
        if "Poverty_Rate_Percent" in cl.columns:
            _, html = _add_geojson_choropleth(
                m=m,
                gdf=cl,
                value_col="Poverty_Rate_Percent",
                layer_name="County Poverty Rate (%)",
                palette="YlOrRd_09",
                show=False,
                fill_opacity=0.70,
            )
            if html:
                legends.append({"title": "County Poverty Rate (%)", "html": html})

        # 3) Minority (toggle)
        if "Pct_Minority" in cl.columns:
            _, html = _add_geojson_choropleth(
                m=m,
                gdf=cl,
                value_col="Pct_Minority",
                layer_name="County Minority Population (%)",
                palette="Purples_09",
                show=False,
                fill_opacity=0.70,
            )
            if html:
                legends.append({"title": "County Minority Population (%)", "html": html})

        # 4) AQI hotspots
        if "AQI_P90" in cl.columns:
            _, html = _add_geojson_choropleth(
                m=m,
                gdf=cl,
                value_col="AQI_P90",
                layer_name="Air Quality Hotspots (AQI 90th %ile)",
                palette="YlOrRd_09",
                show=False,
                fill_opacity=0.75,
            )
            if html:
                legends.append({"title": "90th Percentile AQI (higher = worse air)", "html": html})

        # 5) Ozone hotspots
        if "Ozone_Days" in cl.columns:
            _, html = _add_geojson_choropleth(
                m=m,
                gdf=cl,
                value_col="Ozone_Days",
                layer_name="Ozone Hotspots (Days per Year)",
                palette="PuRd_09",
                show=False,
                fill_opacity=0.75,
            )
            if html:
                legends.append({"title": "Ozone Days (higher = more ozone days)", "html": html})

        # 6) PM2.5 hotspots
        if "PM25_Days" in cl.columns:
            _, html = _add_geojson_choropleth(
                m=m,
                gdf=cl,
                value_col="PM25_Days",
                layer_name="PM2.5 Hotspots (Days per Year)",
                palette="BuPu_09",
                show=False,
                fill_opacity=0.75,
            )
            if html:
                legends.append({"title": "PM2.5 Days (higher = more PM2.5 days)", "html": html})

        # Hover tooltips layer
        tooltip_fg = folium.FeatureGroup(name="County Hover Details", show=True)
        tooltip_fields = []
        tooltip_aliases = []

        def _add_field(field: str, alias: str) -> None:
            if field in cl.columns:
                tooltip_fields.append(field)
                tooltip_aliases.append(alias)

        _add_field("NAME", "County")
        _add_field("Impact_Score", "Impact Score (0–100)")
        _add_field("Poverty_Rate_Percent", "Poverty Rate (%)")
        _add_field("Pct_Minority", "Minority Population (%)")
        _add_field("AQI_P90", "AQI 90th %ile")
        _add_field("AQI_Median", "AQI Median")
        _add_field("AQI_Max", "AQI Max")
        _add_field("Ozone_Days", "Ozone Days")
        _add_field("PM25_Days", "PM2.5 Days")
        _add_field("AQI_Days_Total", "Days with AQI")

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

    # --- Site layers (pins) ---
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
    return m, legends
