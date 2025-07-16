
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from astral import LocationInfo
from astral.sun import sun

station = "KVYS"
radius_nm = 50
collection_alt_ft = 7500
min_cloud_base_ft = collection_alt_ft + 500
aviation_api = "https://aviationweather.gov/adds/dataserver_current/httpparam"

now = datetime.utcnow()
params_metar = {
    "dataSource": "metars",
    "requestType": "retrieve",
    "format": "xml",
    "stationString": station,
    "hoursBeforeNow": 2,
    "radialDistance": f"{radius_nm};{station}"
}
params_taf = {
    "dataSource": "tafs",
    "requestType": "retrieve",
    "format": "xml",
    "stationString": station,
    "hoursBeforeNow": 0,
    "radialDistance": f"{radius_nm};{station}"
}

metar_res = requests.get(aviation_api, params=params_metar)
taf_res = requests.get(aviation_api, params=params_taf)
metar_root = ET.fromstring(metar_res.content)
taf_root = ET.fromstring(taf_res.content)

def parse_metar(root):
    clouds = []
    for metar in root.findall(".//METAR"):
        for sky in metar.findall("sky_condition"):
            base = sky.attrib.get("cloud_base_ft_agl")
            if base:
                clouds.append(int(base))
    return clouds

cloud_bases = parse_metar(metar_root)
min_observed_base = min(cloud_bases) if cloud_bases else 99999

def parse_taf(root):
    forecasts = []
    for taf in root.findall(".//TAF"):
        raw = taf.findtext("raw_text")
        forecasts.append(raw)
    return forecasts

taf_forecasts = parse_taf(taf_root)

def is_sun_angle_valid(lat, lon, check_date):
    city = LocationInfo(name="FlightArea", region="IL", timezone="US/Central", latitude=lat, longitude=lon)
    s = sun(city.observer, date=check_date)
    sunrise = s["sunrise"]
    sunset = s["sunset"]
    return {
        "window_start": sunrise + timedelta(hours=1.5),
        "window_end": sunset - timedelta(hours=1.5)
    }

sun_window = is_sun_angle_valid(41.35, -89.15, datetime.utcnow().date())

decision = "GO" if min_observed_base > min_cloud_base_ft else "NO-GO"

print(f"=== FLIGHT WEATHER ANALYSIS FOR KVYS ===")
print(f"Lowest observed cloud base: {min_observed_base} ft AGL")
print(f"Required minimum cloud base: {min_cloud_base_ft} ft AGL")
print(f"Sun window (local time): {sun_window['window_start'].time()} to {sun_window['window_end'].time()}")
print(f"TAF Forecasts:\n" + "\n".join(taf_forecasts[:1]))
print(f"\n🚦 Flight Decision: {decision}")
