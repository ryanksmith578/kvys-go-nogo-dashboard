import streamlit as st
import requests
from datetime import datetime, timedelta
from dateutil import parser
import pytz

# Configuration
API_KEY = "50efb8d57a7941b1b4738711e0419c61"
HEADERS = {"X-API-Key": API_KEY}

AIRPORT = "KVYS"
NEARBY_STATIONS = ["KC75", "KPIA", "KBMI", "KAAA", "KGBG"]
COLLECTION_ALTITUDE_MSL = 8000
REQUIRED_CLEARANCE = 500
MIN_CLOUD_BASE = COLLECTION_ALTITUDE_MSL + REQUIRED_CLEARANCE  # 8500 MSL
CST = pytz.timezone("America/Chicago")

def fetch_metar(station):
    url = f"https://api.checkwx.com/metar/{station}/decoded"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        if data["results"] > 0:
            return data["data"][0]["raw_text"]
        return "Unavailable"
    except Exception as e:
        return f"Error: {e}"

def fetch_taf(station):
    url = f"https://api.checkwx.com/taf/{station}/decoded"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        return data["data"][0] if data["results"] > 0 else None
    except Exception:
        return None

def extract_cloud_base_agl(taf_data, start_time, end_time):
    """Returns lowest BKN/OVC cloud base AGL during the forecast window."""
    if not taf_data:
        return None

    for forecast in taf_data.get("forecast", []):
        try:
            from_time = parser.isoparse(forecast["timestamp"]["from"]).astimezone(CST)
            to_time = parser.isoparse(forecast["timestamp"]["to"]).astimezone(CST)
        except Exception:
            continue

        if to_time < start_time or from_time > end_time:
            continue

        for cloud in forecast.get("clouds", []):
            if cloud.get("type") in ("BKN", "OVC") and cloud.get("base", {}).get("feet"):
                return cloud["base"]["feet"]
    return None

def main():
    st.title("🛫 KVYS Go / No-Go Forecast (via CheckWX)")
    
    now = datetime.now(CST)
    tomorrow = now + timedelta(days=1)
    flight_start = CST.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, 0))
    flight_end = CST.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 18, 0))

    st.markdown(f"**Current Time:** {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    st.markdown(f"**Forecast Window:** {tomorrow.strftime('%A, %B %d')} from 08:00 to 18:00 CST")

    # Show METAR for KVYS
    kvys_metar = fetch_metar(AIRPORT)
    st.markdown(f"### Current METAR for KVYS\n```{kvys_metar}```")

    st.subheader("Forecast Cloud Base (TAF) Analysis")

    stations = [AIRPORT] + NEARBY_STATIONS
    results = []

    for station in stations:
        taf_data = fetch_taf(station)
        taf_raw = taf_data["raw_text"] if taf_data else "N/A"
        base = extract_cloud_base_agl(taf_data, flight_start, flight_end)

        status = "✅ Go" if base and base >= MIN_CLOUD_BASE else "❌ No-Go"
        cloud_info = f"{base} ft AGL" if base else "Not Reported"

        results.append({
            "station": station,
            "taf": taf_raw,
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
