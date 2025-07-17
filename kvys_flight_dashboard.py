import streamlit as st
import requests
from datetime import datetime
import pytz

# Constants
AIRPORT = "KVYS"
NEARBY_STATIONS = ["KC75", "KPIA", "KBMI", "KAAA", "KGBG"]
COLLECTION_ALTITUDE_MSL = 8000  # in feet
REQUIRED_CLEARANCE = 500  # feet above collection altitude
MIN_CLOUD_BASE = COLLECTION_ALTITUDE_MSL + REQUIRED_CLEARANCE  # 8500 MSL
CST = pytz.timezone("America/Chicago")

def fetch_metar(station):
    url = f"https://aviationweather.gov/api/data/metar?ids={station}&format=json"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data:
            return data[0]
    except Exception as e:
        return {"rawText": f"Error fetching METAR for {station}: {e}"}
    return None

def extract_cloud_base(metar_data):
    """
    Returns the first broken or overcast cloud base in feet AGL.
    """
    if not metar_data or "skyCondition" not in metar_data:
        return None
    for layer in metar_data["skyCondition"]:
        if layer.get("skyCover") in ("BKN", "OVC"):
            base_hundreds = layer.get("cloudBase")
            if base_hundreds:
                return int(base_hundreds) * 100
    return None

def main():
    st.title("🛫 KVYS Go / No-Go Flight Check")

    # Show current time (CST)
    now = datetime.now(CST)
    st.markdown(f"**Current Time:** {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # Time check: only run analysis between 0800–1800 CST
    if not (8 <= now.hour < 18):
        st.warning("⏱️ Outside of 0800–1800 CST. No analysis performed.")
        return

    # Fetch and show KVYS METAR at top
    kvys_metar = fetch_metar(AIRPORT)
    kvys_raw = kvys_metar.get("rawText", "Unavailable")
    st.markdown(f"### Current METAR for KVYS\n```{kvys_raw}```")

    st.subheader("Nearby METAR Analysis")

    results = []
    for station in [AIRPORT] + NEARBY_STATIONS:
        metar = fetch_metar(station)
        raw_text = metar.get("rawText", "N/A")
        cloud_base = extract_cloud_base(metar)

        status = "✅ Go" if cloud_base and (cloud_base >= MIN_CLOUD_BASE) else "❌ No-Go"
        cloud_info = f"{cloud_base} ft AGL" if cloud_base else "Not Reported"

        results.append({
            "station": station,
            "metar": raw_text,
            "cloud_base": cloud_info,
            "status": status
        })

    for r in results:
        st.markdown(f"""
        **{r['station']}**  
        `{r['metar']}`  
        - Cloud Base: **{r['cloud_base']}**
        - Status: **{r['status']}**
        ---
        """)

    if all(r["status"] == "✅ Go" for r in results):
        st.success("✅ All stations meet cloud base minimum. Flight is a **Go**.")
    else:
        st.error("❌ One or more stations below minimum cloud base. **No-Go.**")

if __name__ == "__main__":
    main()
