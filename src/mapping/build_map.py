from __future__ import annotations

import folium
import pandas as pd


def _icon_color(layer: str) -> str:
    """Pick marker icon color by layer label."""
    l = (layer or "").strip().lower()
    if l == "existing":
        return "green"
    if l == "proposed":
        return "blue"
    if l == "denied":
        return "red"
    return "gray"


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


def _safe_text(val) -> str:
    """Convert values to safe display strings for popups."""
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    return str(val)


def build_illinois_map(
    sites: pd.DataFrame,
    center: list[float] | None = None,
    zoom_start: int = 7,
) -> folium.Map:
    """
    Build a Folium map for Illinois data centers with toggles.

    Args:
        sites: DataFrame of sites (see module docstring for expected columns)
        center: [lat, lon] map center. Defaults to Illinois center-ish.
        zoom_start: Initial zoom level.

    Returns:
        folium.Map
    """
    if center is None:
        center = [40.0, -89.2]

    df = sites.copy()

    # Normalize expected columns if they exist
    if "layer" in df.columns:
        df["layer"] = df["layer"].astype(str).str.strip().str.lower()

    # Drop rows without coordinates
    if "lat" not in df.columns or "lon" not in df.columns:
        raise ValueError("Input dataframe must include 'lat' and 'lon' columns.")

    df = df.dropna(subset=["lat", "lon"])

    # Ensure numeric
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    m = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Layer toggles
    layer_existing = folium.FeatureGroup(name="Existing", show=True)
    layer_proposed = folium.FeatureGroup(name="Proposed / Under Dev", show=True)
    layer_denied = folium.FeatureGroup(name="Denied", show=True)

    # Cluster overlays toggle
    clusters = folium.FeatureGroup(name="Clusters", show=True)

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

    # Add markers
    for _, r in df.iterrows():
        name = _safe_text(r.get("name"))
        layer = _safe_text(r.get("layer"))
        operator = _safe_text(r.get("operator"))
        city = _safe_text(r.get("city"))
        state = _safe_text(r.get("state"))

        popup_html = f"""
        <div style="font-size: 12px;">
          <b>{name}</b><br>
          <b>Layer:</b> {layer}<br>
          <b>Operator:</b> {operator}<br>
          <b>Location:</b> {city}, {state}<br>
          <b>Address/Hint:</b> {_safe_text(r.get('address_or_hint'))}<br>
          <b>Precision:</b> {_safe_text(r.get('location_precision'))}<br><br>

          <b>Surroundings:</b> {_safe_text(r.get('surroundings_snapshot'))}<br><br>
          <b>Community signals:</b> {_safe_text(r.get('community_signals'))}<br><br>
          <b>Stressors:</b> {_safe_text(r.get('stressors'))}<br><br>

          <b>Sources:</b> {_safe_text(r.get('sources'))}
        </div>
        """

        marker = folium.Marker(
            location=[float(r["lat"]), float(r["lon"])],
            tooltip=name,
            popup=folium.Popup(popup_html, max_width=450),
            icon=folium.Icon(color=_icon_color(layer)),
        )

        if layer == "existing":
            marker.add_to(layer_existing)
        elif layer == "denied":
            marker.add_to(layer_denied)
        else:
            marker.add_to(layer_proposed)

    layer_existing.add_to(m)
    layer_proposed.add_to(m)
    layer_denied.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m
