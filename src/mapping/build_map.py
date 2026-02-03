from __future__ import annotations
import pandas as pd
import geopandas as gpd
import folium


def _icon_color(layer: str) -> str:
    """Pick marker icon color by layer label."""
    l = (layer or "").strip().lower()
    if l == "existing":
        return "green"
    if "proposed" in l:
        return "blue"
    if l == "denied":
        return "red"
    return "gray" # covers gray case for "inventory" layer


def _safe_text(val) -> str:
    """Convert values to safe display strings for popups."""
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    return str(val)


def add_dashed_cluster_circle(
        fg: folium.FeatureGroup,
        center: list[float],
        radius_m: int,
        label: str,
        color: str = "purple",
) -> None:
    """Add a dashed, semi-transparent circle overlay to a FeatureGroup."""
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


def build_illinois_map(
        sites: pd.DataFrame,
        counties_layer: gpd.GeoDataFrame | None = None,
        center: list[float] | None = None,
        zoom_start: int = 7,
) -> folium.Map:
    """
    Build a Folium map for Illinois data centers with toggles and heat maps.
    """
    if center is None:
        center = [40.0, -89.2]

    df = sites.copy()

    # Data cleaning
    if "layer" in df.columns:
        df["layer"] = df["layer"].astype(str).str.strip().str.lower()

    df = df.dropna(subset=["lat", "lon"])
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    # Base Map
    m = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles="cartodbpositron",
        control_scale=True,
    )

    # --- CHOROPLETH LAYERS (HEAT MAPS) ---
    if counties_layer is not None:
        # Poverty Heat Map
        folium.Choropleth(
            geo_data=counties_layer,
            name="Poverty Rate (%)",
            data=counties_layer,
            columns=["GEOID", "Poverty_Rate_Percent"],
            key_on="feature.properties.GEOID",
            fill_color="YlOrRd",
            fill_opacity=0.6,
            line_opacity=0.2,
            legend_name="Percentage Below Poverty Level",
            show=False,
            highlight=True
        ).add_to(m)

        # Minority Population Heat Map
        folium.Choropleth(
            geo_data=counties_layer,
            name="Minority Population (%)",
            data=counties_layer,
            columns=["GEOID", "Pct_Minority"],
            key_on="feature.properties.GEOID",
            fill_color="Purples",
            fill_opacity=0.6,
            line_opacity=0.2,
            legend_name="Minority Population (%)",
            show=False,
            highlight=True
        ).add_to(m)

    # --- CLUSTERS LAYER ---
    clusters = folium.FeatureGroup(name="Impact Clusters", show=True)

    add_dashed_cluster_circle(
        clusters,
        center=[42.000, -87.970],
        radius_m=6000,
        label="Elk Grove Village cluster (multiple existing + proposed sites)",
    )
    add_dashed_cluster_circle(
        clusters,
        center=[41.864, -87.631],
        radius_m=4500,
        label="Chicago core cluster (interconnection hubs and dense urban facilities)",
    )
    add_dashed_cluster_circle(
        clusters,
        center=[41.865, -88.751],
        radius_m=9000,
        label="DeKalb area cluster (campus expansion + approved proposal corridor)",
    )
    clusters.add_to(m)

    # --- MARKER LAYERS ---
    layer_existing = folium.FeatureGroup(name="Existing", show=True)
    layer_proposed = folium.FeatureGroup(name="Proposed", show=True)
    layer_denied = folium.FeatureGroup(name="Denied", show=True)
    layer_inventory = folium.FeatureGroup(name="Inventory (Reserve)", show=False)

    for _, r in df.iterrows():
        name = _safe_text(r.get("name"))
        layer_val = _safe_text(r.get("layer"))

        # Identify if it's a reserve/inv data point
        is_inv= str(r.get("site_id", "")).__contains__("INV") or "inventory" in str(r.get("layer"))

        if is_inv:
            # Build simplified marker for inventory sites
            marker = folium.CircleMarker(
                location = [r["lat"], r["lon"]],
                radius = 6,
                color = "gray",
                fill = True,
                popup = f"<b>{r['name']}</b><br><br><b>Source:</b> {_safe_text(r.get('sources'))}",
            )
            marker.add_to(layer_inventory)
        else:
            # Build Popup HTML using _safe_text function
            poverty = _safe_text(r.get('Poverty_Rate_Percent'))
            minority = _safe_text(r.get('Pct_Minority'))
            income = _safe_text(r.get('Median_Household_Income'))

            popup_html = f"""
                    <div style="font-size: 12px; min-width: 200px;">
                      <b>{name}</b><br>
                      <b>Status:</b> {layer_val}<br><hr>
                      <b>Context:</b><br>
                      • Poverty Rate: {poverty}%<br>
                      • Median Income: ${income}<br>
                      • Minority Population: {minority}%<br><br>
                      <b>Surroundings Snapshot:</b> {_safe_text(r.get('surroundings_snapshot'))} <br><br>
                      <b>Community Signals:</b> {_safe_text(r.get('community_signals'))} <br><br>
                      <b>Stressors:</b> {_safe_text(r.get('stressors'))} <br><br>
                      <b>Sources:</b> {_safe_text(r.get('sources'))}
                    </div>
                    """
            marker = folium.Marker(
                location=[float(r["lat"]), float(r["lon"])],
                tooltip=name,
                popup=folium.Popup(popup_html, max_width=450),
                icon=folium.Icon(color=_icon_color(layer_val)),
            )

            if layer_val == "existing":
                marker.add_to(layer_existing)
            elif layer_val == "denied":
                marker.add_to(layer_denied)
            else:
                marker.add_to(layer_proposed)


    layer_existing.add_to(m)
    layer_proposed.add_to(m)
    layer_denied.add_to(m)
    layer_inventory.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m