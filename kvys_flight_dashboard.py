import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz
import math
import os

# Constants
CHECKWX_API_KEY = "50efb8d57a7941b1b4738711e0419c61"
BASE_URL = "https://api.checkwx.com"
CENTER_ICAO = "KVYS"
CST = pytz.timezone("America/Chicago")
RADIUS_NM = 50

def get_metar(icao):
    headers = {"X-API-Key": CHECKWX_API_KEY}
    url = f"{BASE_URL}/metar/{icao}/decoded"
    response = requests.get(url, headers=headers)
    if response.status_code == 200 and response.json()["data"]:
        return response.json()["data"][0]
    return None

def get_taf(icao):
    headers = {"X-API-Key": CHECKWX_API_KEY}
    url = f"{BASE_URL}/taf/{icao}/decoded"
    response = requests.get(url, headers=headers)
    if response.status_code == 200 and response.json()["data"]:
        return response.json()["data"][0]
    return None

def haversine(lat1, lon1, lat2, lon2):
    R = 3440.065  # Radius of Earth in NM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_nearby_airports():
    kvys_lat, kvys_lon = 41.3519, -89.1531
    airports_path = os.path.join("data", "airports.csv")
    df = pd.read_csv(airports_path)
    df["distance"] = df.apply(lambda row: haversine(kvys_lat, kvys_lon, row["latitude_deg"], row["longitude_deg"]), axis=1)
    df = df[df["distance"] <= RADIUS_NM]
    return df.sort_values(by="distance")

def extract_cloud_base_agl(taf_data, flight_start, flight_end):
    if not taf_data:
        return "TAF unavailable"

    cloud_bases = []
    for forecast in taf_data.get("forecast", []):
        try:
            from_time = datetime.strptime(forecast["timestamp"]["from"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC).astimezone(CST)
            to_time = datetime.strptime(forecast["timestamp"]["to"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC).astimezone(CST)
        except Exception:
            continue

        if to_time < flight_start or from_time > flight_end:
            continue

        if "clouds" in forecast:
            for layer in forecast["clouds"]:
                if "base" in layer and layer["base"]["feet_agl"] is not None:
                    cloud_bases.append(layer["base"]["feet_agl"])

    if not cloud_bases:
        return "No cloud base info in TAF"
    
    return f"{min(cloud_bases)} ft AGL"

def main():
    st.set_page_config(layout="wide")
    st.title("🛩️ KVYS Flight Go/No-Go Dashboard")

    st.markdown("### Current METAR for KVYS")
    kvys_metar = get_metar(CENTER_ICAO)
    kvys_flight_cat = "UNK"

    if kvys_metar:
        metar_text = kvys_metar.get("raw_text", "Unavailable")
        kvys_flight_cat = kvys_metar.get("flight_category", "UNK")

        st.markdown(f"""
        <div style="white-space: pre-wrap; word-wrap: break-word; background-color:#f9f9f9; padding: 10px; border-radius: 6px;">
            {metar_text}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error("METAR data unavailable for KVYS")

    # Define flight window
    now = datetime.now(CST)
    is_morning_run = now.hour < 12
    target_day = now if is_morning_run else now + timedelta(days=1)
    flight_start = target_day.replace(hour=8, minute=0, second=0, microsecond=0)
    flight_end = target_day.replace(hour=18, minute=0, second=0, microsecond=0)

    # Load airports
    airport_df = get_nearby_airports()

    taf_rows = []

    for _, row in airport_df.iterrows():
        icao = row["ident"]
        name = row["name"]

        taf = get_taf(icao)

        if taf:
            taf_source = f"{icao} (own TAF)"
            taf_used = taf
        else:
            # Use nearest TAF from another station
            taf_used = None
            for _, alt_row in airport_df.iterrows():
                alt_icao = alt_row["ident"]
                if alt_icao == icao:
                    continue
                alt_taf = get_taf(alt_icao)
                if alt_taf:
                    taf_used = alt_taf
                    taf_source = f"{alt_icao} (TAF {alt_row['name']} - {alt_row['distance']:.1f} NM)"
                    break
            if not taf_used:
                taf_source = "No TAF found"

        cloud_base = extract_cloud_base_agl(taf_used, flight_start, flight_end)

        taf_rows.append({
            "ICAO": icao,
            "Airport": name,
            "Cloud Base Forecast": cloud_base,
            "TAF Source": taf_source
        })

    summary_df = pd.DataFrame(taf_rows)
    st.markdown(f"### Cloud Base Forecasts for {flight_start.strftime('%Y-%m-%d')}")
    st.dataframe(summary_df, use_container_width=True)

if __name__ == "__main__":
    main()
