import streamlit as st
import requests
from datetime import datetime, timedelta
import pytz

# Constants
AIRPORT = "KVYS"
NEARBY_STATIONS = ["KC75", "KPIA", "KBMI", "KAAA", "KGBG"]
COLLECTION_ALTITUDE_MSL = 8000
REQUIRED_CLEARANCE = 500
MIN_CLOUD_BASE = COLLECTION_ALTITUDE_MSL + REQUIRED_CLEARANCE  # 8500 MSL
CST = pytz.timezone("America/Chicago")

def fetch_metar(station):
    url = f"https://aviationweather.gov/api/data/metar?ids={station}&format=json"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data[0] if data else {}
    except Exception as e:
        return {"rawText": f"Error fetching METAR: {e}"}

def fetch_taf(station):
    url = f"https://aviationweather.gov/api/data/taf?ids={station}&format=json"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data[0] if data else {}
    except Exception as e:
        return {"rawText": f"Error fetching TAF: {e}"}

def extract_tomorrow_cloud_base(taf_data, start_cst, end_cst):
    """Extracts lowest forecasted broken/overcast cloud base (in ft AGL) during 0800–1800 CST tomorrow."""
    if not taf_data or "forecast" not in taf_data:
        return None
    for period in taf_data["forecast"]:
        from_time = parse_taf_time(period.get("fcstTimeFrom"))
        to_time = parse_taf_time(period.get("fcstTimeTo"))
        if not from_time or not to_time:
            continue
        if to_time < start_cst or from_time > end_cst:
            continue  # Outside desired window

        # Check for BKN/OVC cloud layer
        sky = period.get("skyCondition", [])
        for layer in sky:
            if layer.get("skyCover") in ("BKN", "OVC") and "cloudBase" in layer:
                return int(layer["cloudBase"]) * 100
    return None

def parse_taf_time(timestr):
    """Parses TAF time format '20250718T1300Z' to aware datetime in CST."""
    try:
        dt = datetime.strptime(timestr, "%Y%m%dT%H%MZ")
        return pytz.utc.localize(dt).astimezone(CST)
    except:
        return None

def main():
    st.title("🛫 KVYS Tomorrow Go / No-Go Forecast")

    now = datetime.now(CST)
    tomorrow = now + timedelta(days=1)
    st.markdown(f"**Current Time:** {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    st.markdown(f"**Forecasting for:** {tomorrow.strftime('%A, %B %d')} (08:00–18:00 CST)")

    # Define tomorrow's flight window in CST
    flight_start = CST.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, 0, 0))
    flight_end = CST.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 18, 0, 0))

    # Show current METAR for KVYS
    kvys_metar = fetch_metar(AIRPORT)
    st.markdown(f"### Current METAR for KVYS\n```{kvys_metar.get('rawText', 'Unavailable')}```")

    st.subheader("Forecast Cloud Base Analysis (TAF)")

    stations = [AIRPORT] + NEARBY_STATIONS
    results = []

    for station in stations:
        taf = fetch_taf(station)
        taf_text = taf.get("rawText", "N/A")
        cloud_base = extract_tomorrow_cloud_base(taf, flight_start, flight_end)

        status = "✅ Go" if cloud_base and (cloud_base >= MIN_CLOUD_BASE) else "❌ No-Go"
        cloud_info = f"{cloud_base} ft AGL" if cloud_base else "Not Reported"

        results.append({
            "station": station,
            "taf": taf_text,
            "cloud_base": cloud_info,
            "status": status
        })

    for r in results:
        st.markdown(f"""
        **{r['station']}**  
        `{r['taf']}`  
        - Forecast Cloud Base: **{r['cloud_base']}**
        - Status: **{r['status']}**
        ---
        """)

    if all(r["status"] == "✅ Go" for r in results):
        st.success("✅ All stations forecasted to meet cloud base minimum. Flight is a **Go**.")
    else:
        st.error("❌ One or more stations forecasted below minimum cloud base. **No-Go.**")

if __name__ == "__main__":
    main()
