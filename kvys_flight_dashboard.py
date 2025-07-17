import streamlit as st
import requests
from datetime import datetime, timedelta
import pytz
import xml.etree.ElementTree as ET

# Config
AIRPORT = "KVYS"
NEARBY_STATIONS = ["KC75", "KPIA", "KBMI", "KAAA", "KGBG"]
COLLECTION_ALTITUDE_MSL = 8000
REQUIRED_CLEARANCE = 500
MIN_CLOUD_BASE = COLLECTION_ALTITUDE_MSL + REQUIRED_CLEARANCE  # 8500 MSL
CST = pytz.timezone("America/Chicago")

def fetch_metar_from_adds(station):
    url = (
        "https://aviationweather.gov/adds/dataserver_current/httpparam"
        "?dataSource=metars&requestType=retrieve&format=xml"
        f"&stationString={station}&hoursBeforeNow=1&mostRecent=true"
    )
    try:
        r = requests.get(url, timeout=10)
        root = ET.fromstring(r.text)
        raw_text = root.findtext(".//raw_text", default="Unavailable")
        return raw_text
    except Exception as e:
        return f"Error fetching METAR for {station}: {e}"

def fetch_taf_from_adds(station):
    url = (
        "https://aviationweather.gov/adds/dataserver_current/httpparam"
        "?dataSource=tafs&requestType=retrieve&format=xml"
        f"&stationString={station}&hoursBeforeNow=6&mostRecent=true"
    )
    try:
        r = requests.get(url, timeout=10)
        return ET.fromstring(r.text)
    except Exception as e:
        return None

def extract_forecast_bases(taf_xml, start_cst, end_cst):
    """Extract forecast cloud base (lowest BKN/OVC) between given times from TAF XML."""
    if taf_xml is None:
        return None
    forecasts = taf_xml.findall(".//forecast")
    for fcst in forecasts:
        from_time = fcst.findtext("fcst_time_from")
        to_time = fcst.findtext("fcst_time_to")
        try:
            from_dt = datetime.strptime(from_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC).astimezone(CST)
            to_dt = datetime.strptime(to_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC).astimezone(CST)
        except:
            continue

        if to_dt < start_cst or from_dt > end_cst:
            continue  # Skip periods outside tomorrow’s flight window

        for sky in fcst.findall("sky_condition"):
            cover = sky.attrib.get("sky_cover", "")
            base_ft_agl = sky.attrib.get("cloud_base_ft_agl")
            if cover in ("BKN", "OVC") and base_ft_agl:
                return int(base_ft_agl)
    return None

def main():
    st.title("🛫 KVYS Tomorrow Go / No-Go Forecast (via NOAA ADDS)")

    now = datetime.now(CST)
    tomorrow = now + timedelta(days=1)
    flight_start = CST.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, 0))
    flight_end = CST.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 18, 0))

    st.markdown(f"**Current Time:** {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    st.markdown(f"**Forecast Window:** {tomorrow.strftime('%A, %B %d')} from 08:00 to 18:00 CST")

    # Show current METAR for KVYS
    kvys_metar = fetch_metar_from_adds(AIRPORT)
    st.markdown(f"### Current METAR for KVYS\n```{kvys_metar}```")

    st.subheader("Forecast Cloud Base (TAF) Analysis")

    stations = [AIRPORT] + NEARBY_STATIONS
    results = []

    for station in stations:
        taf_xml = fetch_taf_from_adds(station)
        taf_raw = taf_xml.findtext(".//raw_text", default="Unavailable") if taf_xml else "N/A"
        base = extract_forecast_bases(taf_xml, flight_start, flight_end)

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
