import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz

# Constants
CHECKWX_API_KEY = "YOUR_CHECKWX_API_KEY"  # Replace with your API key
CHECKWX_BASE_URL = "https://api.checkwx.com"
ICAO = "KVYS"
COLLECTION_ALT_MSL = 8000  # in feet
CST = pytz.timezone("US/Central")

# Define time window for forecast analysis
ANALYSIS_START_HOUR = 8
ANALYSIS_END_HOUR = 18

HEADERS = {
    "X-API-Key": CHECKWX_API_KEY
}


def fetch_metar(icao):
    url = f"{CHECKWX_BASE_URL}/metar/{icao}/decoded"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    return data['data'][0] if data.get('data') else None


def fetch_taf_nearest(icao):
    url = f"{CHECKWX_BASE_URL}/taf/{icao}/nearest/10/decoded"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    if data.get("data"):
        return data['data'][0]
    return None


def extract_cloud_base_agl(taf_data, flight_start, flight_end):
    cloud_bases = []
    if not taf_data:
        return cloud_bases

    for forecast in taf_data.get("forecast", []):
        from_time = datetime.strptime(forecast["timestamp"]["from"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=pytz.UTC).astimezone(CST)
        to_time = datetime.strptime(forecast["timestamp"]["to"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=pytz.UTC).astimezone(CST)

        if from_time > flight_end or to_time < flight_start:
            continue

        for cloud in forecast.get("clouds", []):
            if cloud["altitude"] is not None:
                base_ft_agl = cloud["altitude"] * 100
                base_ft_msl = base_ft_agl + taf_data["elevation_ft"]
                cloud_bases.append((from_time.strftime("%H:%M"), to_time.strftime("%H:%M"), base_ft_msl))
                break

    return cloud_bases


def analyze_and_display(icao, airport_name):
    # Header
    st.markdown(f"### {airport_name} ({icao})")

    # Fetch METAR and TAF
    metar = fetch_metar(icao)
    taf = fetch_taf_nearest(icao)

    # METAR Display
    metar_text = metar["raw_text"] if metar else "No METAR data available"
    st.markdown("**Latest METAR:**")
    st.markdown(f"""
    <div style="white-space: pre-wrap; word-wrap: break-word;">
        {metar_text}
    </div>
    """, unsafe_allow_html=True)

    # TAF Display
    taf_text = taf["raw_text"] if taf else "No TAF data available"
    st.markdown("**TAF Used (Nearest Available):**")
    st.markdown(f"""
    <div style="white-space: pre-wrap; word-wrap: break-word;">
        {taf_text}
    </div>
    """, unsafe_allow_html=True)

    # Forecast Time Window
    now = datetime.now(CST)
    if now.hour < 16:
        flight_day = now
    else:
        flight_day = now + timedelta(days=1)

    flight_start = flight_day.replace(hour=ANALYSIS_START_HOUR, minute=0, second=0, microsecond=0)
    flight_end = flight_day.replace(hour=ANALYSIS_END_HOUR, minute=0, second=0, microsecond=0)

    cloud_bases = extract_cloud_base_agl(taf, flight_start, flight_end)

    # Prepare Table
    if not cloud_bases:
        st.warning("No cloud base forecast data available during flight window.")
        return

    rows = []
    for entry in cloud_bases:
        from_t, to_t, base_ft_msl = entry
        rows.append({
            "From (CST)": from_t,
            "To (CST)": to_t,
            "Cloud Base (MSL ft)": int(base_ft_msl)
        })

    df = pd.DataFrame(rows)

    # Style based on collection altitude
    def highlight(row):
        base = row["Cloud Base (MSL ft)"]
        if base >= COLLECTION_ALT_MSL + 500:
            return ['background-color: #d4edda'] * len(row)  # green
        elif base >= 5000:
            return ['background-color: #fff3cd'] * len(row)  # amber/yellow
        else:
            return ['background-color: #f8d7da'] * len(row)  # red

    st.markdown("### Forecast Cloud Bases")
    st.dataframe(df.style.apply(highlight, axis=1), use_container_width=True)


def main():
    st.set_page_config(page_title="KVYS Go/No-Go Flight Dashboard", layout="wide")
    st.title("✈️ KVYS Go/No-Go Flight Weather Dashboard")

    analyze_and_display("KVYS", "Illinois Valley Regional Airport")


if __name__ == "__main__":
    main()
