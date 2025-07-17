import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from geopy.distance import geodesic
import pytz
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import os

# Constants
KVYS_COORDS = (41.3514, -89.1531)
CHECKWX_API_KEY = "50efb8d57a7941b1b4738711e0419c61"
CST = pytz.timezone("America/Chicago")
FLIGHT_ALT_MSL = 8000
MIN_CLOUD_BASE_ABOVE = 500  # in feet
REQUIRED_CLOUD_BASE = FLIGHT_ALT_MSL + MIN_CLOUD_BASE_ABOVE
RADIUS_NM = 50

# Load local airports.csv file
def get_nearby_airports():
    file_path = os.path.join("data", "airports.csv")
    df = pd.read_csv(file_path)
    return df

# Haversine distance in NM
def distance_nm(coord1, coord2):
    return geodesic(coord1, coord2).nautical

# Filter nearby airports
def filter_airports(df, center_coords, radius_nm):
    nearby = []
    for _, row in df.iterrows():
        try:
            lat, lon = float(row['latitude_deg']), float(row['longitude_deg'])
            dist = distance_nm(center_coords, (lat, lon))
            if dist <= radius_nm:
                nearby.append({
                    "icao": row["ident"],
                    "name": row["name"],
                    "lat": lat,
                    "lon": lon,
                    "dist_nm": round(dist, 1)
                })
        except:
            continue
    return pd.DataFrame(nearby)

# CheckWX GET
def checkwx_get(endpoint):
    url = f"https://api.checkwx.com/{endpoint}"
    headers = {"X-API-Key": CHECKWX_API_KEY}
    response = requests.get(url, headers=headers)
    return response.json()

# Get METAR for station
def get_metar(icao):
    data = checkwx_get(f"metar/{icao}/decoded")
    if "data" in data and len(data["data"]) > 0:
        return data["data"][0]
    return None

# Get TAF for station
def get_taf(icao):
    data = checkwx_get(f"taf/{icao}/decoded")
    if "data" in data and len(data["data"]) > 0:
        return data["data"][0]
    return None

# Find nearest airport with valid TAF
def get_nearest_taf(icao, nearby_airports):
    for airport in nearby_airports:
        taf = get_taf(airport["icao"])
        if taf:
            return taf, airport
    return None, None

# Analyze cloud base during flight period (0800–1800 CST)
def extract_cloud_base_agl(taf_data, flight_start, flight_end):
    cloud_bases = []
    for forecast in taf_data.get("forecast", []):
        try:
            from_time = datetime.strptime(forecast["timestamp"]["from"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC).astimezone(CST)
            to_time = datetime.strptime(forecast["timestamp"]["to"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC).astimezone(CST)
            if to_time < flight_start or from_time > flight_end:
                continue
            for cloud_layer in forecast.get("clouds", []):
                if cloud_layer.get("base"):
                    base_agl = int(cloud_layer["base"]["feet"])
                    cloud_bases.append(base_agl)
        except:
            continue
    return min(cloud_bases) if cloud_bases else None

# Plot map
def create_map(airport_df, flight_category_dict):
    m = folium.Map(location=KVYS_COORDS, zoom_start=8, tiles="CartoDB positron")

    # Add 50 NM radius
    folium.Circle(
        location=KVYS_COORDS,
        radius=50 * 1852,
        color='gray',
        fill=False,
        weight=2
    ).add_to(m)

    marker_cluster = MarkerCluster().add_to(m)

    for _, row in airport_df.iterrows():
        category = flight_category_dict.get(row["icao"], "UNK")
        color = {
            "VFR": "green",
            "MVFR": "blue",
            "IFR": "red",
            "LIFR": "pink"
        }.get(category, "gray")
        folium.CircleMarker(
            location=(row["lat"], row["lon"]),
            radius=6,
            color=color,
            fill=True,
            fill_opacity=0.8,
            tooltip=f"{row['icao']} - {row['name']} ({row['dist_nm']} NM)",
        ).add_to(marker_cluster)

    return m

# Main app
def main():
    st.set_page_config(page_title="KVYS Go/No-Go Dashboard", layout="wide")
    st.title("✈️ KVYS Go/No-Go Flight Dashboard")

    # Dates
    today = datetime.now(CST).date()
    tomorrow = today + timedelta(days=1)
    flight_start = CST.localize(datetime.combine(today, datetime.strptime("08:00", "%H:%M").time()))
    flight_end = CST.localize(datetime.combine(today, datetime.strptime("18:00", "%H:%M").time()))

    # Load and filter airports
    full_df = get_nearby_airports()
    nearby_df = filter_airports(full_df, KVYS_COORDS, RADIUS_NM)

    # METAR for KVYS
    kvys_metar = get_metar("KVYS")
    if kvys_metar:
        metar_text = kvys_metar.get("raw_text", "Unavailable")
        st.markdown("### Current METAR for KVYS")
        st.markdown(f"""
        <div style="white-space: pre-wrap; word-wrap: break-word; background-color:#f9f9f9; padding: 10px; border-radius: 6px;">
            {metar_text}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error("METAR data unavailable for KVYS")

    st.markdown("### Nearby Airport Forecasts and Flight Decision")

    results = []
    flight_category = {}

    for _, row in nearby_df.iterrows():
        icao = row["icao"]
        name = row["name"]
        taf = get_taf(icao)
        taf_source = "Own TAF used"
        taf_dist = 0
        taf_used = taf

        if not taf:
            taf_used, source_airport = get_nearest_taf(icao, nearby_df.to_dict(orient="records"))
            if taf_used and source_airport:
                taf_source = f"TAF from {source_airport['icao']} ({source_airport['dist_nm']} NM)"
            else:
                taf_source = "No TAF available"

        cloud_base = extract_cloud_base_agl(taf_used, flight_start, flight_end) if taf_used else None

        decision = "Go" if cloud_base and (FLIGHT_ALT_MSL + 500) <= cloud_base else "No-Go"
        flight_category[icao] = kvys_metar.get("flight_category", "UNK") if icao == "KVYS" else "UNK"

        st.subheader(f"{icao} - {name}")
        st.markdown(f"**Forecast Source:** {taf_source}")
        if taf_used:
            raw_taf = taf_used.get("raw_text", "No TAF Text")
            st.markdown(f"""
            <div style="white-space: pre-wrap; word-wrap: break-word; background-color:#eef; padding: 10px; border-radius: 6px;">
                {raw_taf}
            </div>
            """, unsafe_allow_html=True)
        st.markdown(f"**Forecast Cloud Base AGL:** {cloud_base if cloud_base else 'N/A'} ft")
        st.markdown(f"**Decision:** {'✅ Go' if decision == 'Go' else '⛔️ No-Go'}")
        st.markdown("---")

    # Map
    st.markdown("### Airport Flight Category Map")
    map_obj = create_map(nearby_df, flight_category)
    st_data = st_folium(map_obj, width=1000, height=600)

if __name__ == "__main__":
    main()
