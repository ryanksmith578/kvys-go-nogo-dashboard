import streamlit as st
import folium
from folium import plugins
from streamlit_folium import st_folium
import requests
from geopy.distance import geodesic
from datetime import datetime, timedelta
import pytz
import pandas as pd

# Constants
API_KEY = "50efb8d57a7941b1b4738711e0419c61"
HOME_ICAO = "KVYS"
HOME_COORDS = (41.3519, -89.1536)
CST = pytz.timezone("America/Chicago")
FLIGHT_START = CST.localize(datetime.now().replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1))
FLIGHT_END = CST.localize(datetime.now().replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1))

# Remove haze look
st.markdown("""
    <style>
        body, .stApp {
            background-color: white !important;
            opacity: 1 !important;
            filter: none !important;
        }
    </style>
""", unsafe_allow_html=True)

# Function: Get METAR and TAF data from CheckWX
def get_checkwx_data(icao_list):
    joined = ",".join(icao_list)
    headers = {"X-API-Key": API_KEY}
    
    metar_resp = requests.get(f"https://api.checkwx.com/metar/{joined}/decoded", headers=headers).json()
    taf_resp = requests.get(f"https://api.checkwx.com/taf/{joined}/decoded", headers=headers).json()
    
    metars = {d["icao"]: d for d in metar_resp.get("data", [])}
    tafs = {d["icao"]: d for d in taf_resp.get("data", [])}
    
    return metars, tafs

# Function: Find airports within radius
def get_nearby_airports(radius_nm=50):
    url = "https://ourairports.com/data/airports.csv"
    df = pd.read_csv(url)
    df = df[df["iso_country"] == "US"]
    df = df[df["type"].isin(["medium_airport", "large_airport", "small_airport"])]
    df = df[df["gps_code"].notna()]
    
    df["distance_nm"] = df.apply(
        lambda row: geodesic(HOME_COORDS, (row["latitude_deg"], row["longitude_deg"])).nm,
        axis=1
    )
    df = df[df["distance_nm"] <= radius_nm]
    
    return df.sort_values("distance_nm")

# Function: Interpret flight category to color
def category_to_color(category):
    return {
        "VFR": "green",
        "MVFR": "blue",
        "IFR": "red",
        "LIFR": "pink"
    }.get(category, "gray")

# Function: Find nearest valid TAF for a given airport
def find_nearest_valid_taf(icao, tafs, airport_df):
    if icao in tafs and tafs[icao].get("forecast"):
        return icao, tafs[icao], 0  # own valid TAF

    this_airport = airport_df[airport_df["gps_code"] == icao]
    if this_airport.empty:
        return None, None, None

    lat, lon = this_airport.iloc[0]["latitude_deg"], this_airport.iloc[0]["longitude_deg"]
    distances = []

    for taf_icao, taf in tafs.items():
        if not taf.get("forecast"):
            continue
        taf_airport = airport_df[airport_df["gps_code"] == taf_icao]
        if taf_airport.empty:
            continue
        taf_coords = (taf_airport.iloc[0]["latitude_deg"], taf_airport.iloc[0]["longitude_deg"])
        d = geodesic((lat, lon), taf_coords).nm
        distances.append((taf_icao, taf, d))

    if not distances:
        return None, None, None
    return min(distances, key=lambda x: x[2])  # nearest with valid TAF

# Function: Extract cloud base from TAF during the flight window
def extract_cloud_base_agl(taf, start_time, end_time):
    cloud_bases = []

    for forecast in taf.get("forecast", []):
        from_time = datetime.strptime(forecast["timestamp"]["from"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC).astimezone(CST)
        if not (start_time <= from_time <= end_time):
            continue
        clouds = forecast.get("clouds", [])
        for cloud in clouds:
            if "base_feet_agl" in cloud:
                cloud_bases.append(cloud["base_feet_agl"])

    return min(cloud_bases) if cloud_bases else None

# Main App
def main():
    st.title("KVYS Go/No-Go Flight Dashboard")
    st.markdown("Flight Level: **8000’ MSL** | Cloud Base Minimum: **8500’ MSL (500’ AGL buffer)**")

    airport_df = get_nearby_airports()
    icao_list = airport_df["gps_code"].tolist()
    metars, tafs = get_checkwx_data(icao_list + [HOME_ICAO])

    # Show current METAR from KVYS
    kvys_metar = metars.get(HOME_ICAO, {})
    if kvys_metar:
        metar_text = kvys_metar.get("raw_text", "No METAR available")
        st.markdown(f"""
            <div style="white-space: pre-wrap; word-wrap: break-word;">
                <strong>KVYS METAR:</strong> {metar_text}
            </div>
        """, unsafe_allow_html=True)

    # Build Map
    fmap = folium.Map(location=HOME_COORDS, zoom_start=8, tiles="Esri.WorldImagery")

    # Add radius circle
    folium.Circle(
        location=HOME_COORDS,
        radius=92600,  # 50 NM in meters
        color="yellow",
        fill=False
    ).add_to(fmap)

    results = []

    for _, row in airport_df.iterrows():
        icao = row["gps_code"]
        name = row["name"]
        dist_nm = round(row["distance_nm"], 1)

        metar = metars.get(icao)
        taf_icao, taf_used, taf_dist = find_nearest_valid_taf(icao, tafs, airport_df)

        if taf_used:
            base = extract_cloud_base_agl(taf_used, FLIGHT_START, FLIGHT_END)
            go_nogo = "✅ GO" if base and base >= 500 else "❌ NO-GO"
            taf_source = f"{taf_icao} ({round(taf_dist)} NM away)" if taf_icao != icao else f"{icao} (own TAF)"
        else:
            base = None
            go_nogo = "❌ NO-GO"
            taf_source = "No TAF available"

        # Save results
        results.append({
            "ICAO": icao,
            "Name": name,
            "Distance": dist_nm,
            "TAF Source": taf_source,
            "Cloud Base AGL": f"{base} ft" if base else "N/A",
            "Go/No-Go": go_nogo
        })

        # Add marker
        if metar:
            color = category_to_color(metar.get("flight_category", ""))
            tooltip = f"{icao} - {name}\n{metar.get('flight_category', 'Unknown')}"
            folium.CircleMarker(
                location=[row["latitude_deg"], row["longitude_deg"]],
                radius=6,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=1.0,
                tooltip=tooltip
            ).add_to(fmap)

    st_data = st_folium(fmap, width=700, height=500)

    # Show results table
    st.markdown("### Forecast Summary")
    for entry in results:
        st.markdown(f"**{entry['ICAO']} - {entry['Name']} ({entry['Distance']} NM)**")
        st.markdown(f"- **TAF Used:** {entry['TAF Source']}")
        st.markdown(f"- **Forecast Cloud Base:** {entry['Cloud Base AGL']}")
        st.markdown(f"- **Decision:** {entry['Go/No-Go']}")
        st.markdown("---")

if __name__ == "__main__":
    main()
