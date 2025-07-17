import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
from datetime import datetime, timedelta
from dateutil import parser
import pytz

# Config
API_KEY = "50efb8d57a7941b1b4738711e0419c61"
HEADERS = {"X-API-Key": API_KEY}
CST = pytz.timezone("America/Chicago")

# Central point (KVYS)
HOME_ICAO = "KVYS"
HOME_COORDS = (41.3507, -89.1531)  # KVYS
RADIUS_NM = 50
MIN_CLOUD_BASE = 8500  # MSL

# Static airport info (ICAO -> (lat, lon, name))
AIRPORTS = {
    "KVYS": (41.3507, -89.1531, "Illinois Valley Regional"),
    "KPIA": (40.6642, -89.6933, "Peoria Intl"),
    "KBMI": (40.4771, -88.9159, "Bloomington-Normal"),
    "KGBG": (40.9375, -90.4311, "Galesburg Muni"),
    "KC75": (41.0327, -89.3857, "Marshall County"),
    "KAAA": (40.8333, -89.5833, "Logan County"),
    "KSQI": (41.7504, -89.6776, "Whiteside County"),
    "KMLI": (41.4486, -90.5075, "Quad City Intl"),
    "KJOT": (41.5206, -88.1753, "Joliet Regional"),
    "KDKB": (41.9317, -88.7053, "DeKalb Taylor"),
    "KRFD": (42.1954, -89.0972, "Rockford Intl"),
}

def fetch_metar(icao):
    try:
        r = requests.get(f"https://api.checkwx.com/metar/{icao}/decoded", headers=HEADERS, timeout=10)
        data = r.json()
        return data["data"][0] if data.get("results", 0) > 0 else None
    except:
        return None

def fetch_taf(icao):
    try:
        r = requests.get(f"https://api.checkwx.com/taf/{icao}/decoded", headers=HEADERS, timeout=10)
        data = r.json()
        return data["data"][0] if data.get("results", 0) > 0 else None
    except:
        return None

def extract_cloud_base_agl(taf_data, start_time, end_time):
    """Return lowest BKN/OVC cloud base AGL during the forecast window."""
    if not taf_data: return None
    for forecast in taf_data.get("forecast", []):
        try:
            from_time = parser.isoparse(forecast["timestamp"]["from"]).astimezone(CST)
            to_time = parser.isoparse(forecast["timestamp"]["to"]).astimezone(CST)
        except:
            continue
        if to_time < start_time or from_time > end_time:
            continue
        for cloud in forecast.get("clouds", []):
            if cloud.get("type") in ("BKN", "OVC"):
                return cloud.get("base", {}).get("feet")
    return None

def get_nearest_taf(source_icao, start, end):
    """Find nearest airport with usable TAF."""
    src_coords = AIRPORTS[source_icao][:2]
    best = None
    best_dist = float('inf')
    for icao, (lat, lon, _) in AIRPORTS.items():
        if icao == source_icao:
            continue
        taf = fetch_taf(icao)
        if not taf:
            continue
        cb = extract_cloud_base_agl(taf, start, end)
        if cb is not None:
            dist = geodesic(src_coords, (lat, lon)).nm
            if dist < best_dist:
                best = (icao, taf, cb, dist)
                best_dist = dist
    return best

def get_flight_category(metar):
    return metar.get("flight_category", "UNK")

def get_marker_color(cat):
    return {
        "VFR": "green",
        "MVFR": "blue",
        "IFR": "red",
        "LIFR": "pink"
    }.get(cat, "gray")

def main():
    st.set_page_config("KVYS Go/No-Go Dashboard", layout="wide")
    st.title("🛫 KVYS Go/No-Go Flight Forecast Dashboard")
    
    now = datetime.now(CST)
    tomorrow = now + timedelta(days=1)
    flight_start = CST.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, 0))
    flight_end = CST.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 18, 0))

    st.markdown(f"**Forecast Window:** {tomorrow.strftime('%A %B %d')} from 08:00 to 18:00 CST")

    # Show current METAR
    kvys_metar = fetch_metar(HOME_ICAO)
    if kvys_metar:
        st.markdown(f"### Current METAR for KVYS")
        st.code(kvys_metar.get("raw_text", "N/A"))
    else:
        st.warning("METAR for KVYS unavailable.")

    # Cloud Base Forecast Table
    st.subheader("☁️ Forecast Cloud Base Analysis")
    st.markdown("*Cloud base must be ≥ 8500' MSL to be a Go.*")

    results = []
    for icao, (lat, lon, name) in AIRPORTS.items():
        taf = fetch_taf(icao)
        cloud_base = extract_cloud_base_agl(taf, flight_start, flight_end) if taf else None
        taf_used = icao
        taf_dist = 0

        if cloud_base is None:
            fallback = get_nearest_taf(icao, flight_start, flight_end)
            if fallback:
                taf_used, taf, cloud_base, taf_dist = fallback

        status = "✅ Go" if cloud_base and cloud_base >= MIN_CLOUD_BASE else "❌ No-Go"
        taf_note = f"TAF data used from {taf_used} ({AIRPORTS[taf_used][2]}, {round(taf_dist)} NM away)" if taf_used != icao else "Own TAF used"

        results.append({
            "icao": icao,
            "name": name,
            "cloud_base": cloud_base,
            "status": status,
            "taf_note": taf_note,
            "taf_raw": taf["raw_text"] if taf else "N/A"
        })

    for r in results:
        st.markdown(f"""
**{r['icao']} – {r['name']}**  
`{r['taf_note']}`  
- Forecast Cloud Base: **{r['cloud_base'] or "N/A"} ft AGL**
- Status: **{r['status']}**
- TAF: `{r['taf_raw']}`
---
""")

    # Map with METAR categories
    st.subheader("🗺️ Flight Category Map (Current METARs)")
    fmap = folium.Map(location=HOME_COORDS, zoom_start=8, tiles="Esri.WorldImagery")

    for icao, (lat, lon, name) in AIRPORTS.items():
        dist_nm = geodesic(HOME_COORDS, (lat, lon)).nm
        if dist_nm > RADIUS_NM:
            continue
        metar = fetch_metar(icao)
        if not metar:
            continue
        cat = get_flight_category(metar)
        color = get_marker_color(cat)
        folium.CircleMarker(
            location=(lat, lon),
            radius=6,
            color=color,
            fill=True,
            fill_opacity=0.8,
            popup=f"{icao} – {name} ({cat})\n{metar.get('raw_text', '')}"
        ).add_to(fmap)

    st_data = st_folium(fmap, width=1000, height=600)

if __name__ == "__main__":
    main()
