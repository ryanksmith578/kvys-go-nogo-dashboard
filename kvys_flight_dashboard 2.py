
import streamlit as st
import requests
from datetime import datetime, timedelta
from astral import LocationInfo
from astral.sun import sun
import folium
from streamlit_folium import st_folium
from math import radians, cos, sin, asin, sqrt

# ----------------- CONFIG -----------------
kvys_lat, kvys_lon = 41.3514, -89.1531
map_radius_nm = 50
collection_alt_ft = 8000 + 500  # 8500 MSL
min_cloud_clearance_ft = 500
sun_angle_required = 30
metar_endpoint = "https://aviationweather.gov/api/data/metar"
taf_endpoint = "https://aviationweather.gov/api/data/taf"
headers = {"User-Agent": "KVYS Flight Dashboard"}

# -------------- FUNCTIONS -----------------
def haversine(lat1, lon1, lat2, lon2):
    # Haversine formula to calculate distance between two lat/lon points (NM)
    R = 3440.065  # Radius of Earth in nautical miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * asin(sqrt(a))

def get_metars():
    params_metar = {
        "bbox": f"{kvys_lon - 1.5},{kvys_lat - 1.0},{kvys_lon + 1.5},{kvys_lat + 1.0}",
        "hoursBeforeNow": 2,
        "format": "json"
    }
    r = requests.get("https://aviationweather.gov/api/data/metar", params=params_metar, headers=headers)
    return r.json() if r.status_code == 200 else []

def extract_cloud_base(metar):
    # Extract lowest cloud base in ft AGL from METAR
    clouds = metar.get("sky_conditions", [])
    if not clouds:
        return None
    for layer in clouds:
        if layer.get("sky_cover") in ["BKN", "OVC"]:
            base = layer.get("cloud_base_ft_agl")
            return int(base) if base else None
    return None

def get_sun_window():
    loc = LocationInfo(latitude=kvys_lat, longitude=kvys_lon)
    s = sun(loc.observer, date=datetime.utcnow())
    return s['sunrise'], s['sunset']

def get_sun_angle_times():
    # Return approx times when sun is at 30° above horizon (morning and evening)
    loc = LocationInfo(latitude=kvys_lat, longitude=kvys_lon)
    today = datetime.now()
    s = sun(loc.observer, date=today.date())

    sunrise = s["sunrise"].astimezone()
    sunset = s["sunset"].astimezone()

    # Estimate based on rate of sun angle increase
    morning_time = sunrise + timedelta(hours=1.5)  # Approx 30°
    evening_time = sunset - timedelta(hours=1.5)    # Approx 30° from setting
    return morning_time.strftime("%I:%M %p"), evening_time.strftime("%I:%M %p")

def decision_logic(metars):
    go = True
    reasons = []
    for metar in metars:
        lat = metar.get("latitude")
        lon = metar.get("longitude")
        if not lat or not lon:
            continue
        distance = haversine(kvys_lat, kvys_lon, lat, lon)
        if distance <= map_radius_nm:
            base = extract_cloud_base(metar)
            if base is None:
                continue
            if base < (collection_alt_ft - kvys_lat + min_cloud_clearance_ft):
                go = False
                station = metar.get("station_id", "UNKNOWN")
                reasons.append(f"{station} reports cloud base {base} ft AGL.")
    return go, reasons

# -------------- STREAMLIT UI -----------------
st.set_page_config(page_title="KVYS Flight Weather", layout="wide")
st.title("✈️ KVYS Flight Conditions Dashboard")
st.caption("Visual Go/No-Go tool for 8500' MSL photo missions (cloud bases, flight categories, sun angle).")

sun_morning, sun_evening = get_sun_angle_times()
st.markdown(f"**Sun Angle ≥ 30°:** {sun_morning} to {sun_evening} (Local Time)")

st.markdown("---")
st.subheader("📡 Fetching Live METAR Data...")
metars = get_metars()

# Decision
go, reasons = decision_logic(metars)
if go:
    st.success("✅ GO: Weather conditions appear favorable.")
else:
    st.error("⛔ NO-GO: Conditions not favorable.")
    for r in reasons:
        st.write(f"- {r}")

# 📍 Map with METAR + Flight Category overlay
st.subheader("🗺️ Cloud Base & Flight Category Map Overlay")

m = folium.Map(location=[kvys_lat, kvys_lon], zoom_start=8, tiles=None)

# Satellite tile layer
folium.TileLayer(
    tiles='http://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
    attr='Google Satellite',
    name='Satellite',
    subdomains=['mt0', 'mt1', 'mt2', 'mt3'],
    max_zoom=20
).add_to(m)

# Cloud overlay (requires API key)
folium.TileLayer(
    tiles="https://tile.openweathermap.org/map/clouds_new/{z}/{x}/{y}.png?appid=YOUR_API_KEY",
    attr="Clouds © OpenWeatherMap",
    name="Clouds",
    overlay=True,
    control=True,
    opacity=0.5
).add_to(m)

# Color map for flight categories
flight_cat_colors = {
    "VFR": "green",
    "MVFR": "blue",
    "IFR": "red",
    "LIFR": "purple"
}

# Add METAR stations with cloud base + flight category
for metar in metars:
    station = metar.get("station_id", "")
    lat = metar.get("latitude")
    lon = metar.get("longitude")
    flight_cat = metar.get("flight_category", "Unknown")
    base = extract_cloud_base(metar)

    if lat and lon:
        color = flight_cat_colors.get(flight_cat, "gray")
        label = f"""<b>{station}</b><br>
                    Flight Category: {flight_cat}<br>
                    Cloud Base: {base or 'N/A'} ft AGL"""
        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            popup=folium.Popup(label, max_width=300),
            color=color,
            fill=True,
            fill_opacity=0.8
        ).add_to(m)

# Add radius circle
folium.Circle(
    location=[kvys_lat, kvys_lon],
    radius=map_radius_nm * 1852,  # convert NM to meters
    color="blue",
    fill=False
).add_to(m)

folium.LayerControl().add_to(m)
st_folium(m, width=725)
