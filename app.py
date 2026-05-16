"""
Vatavaram Drusti — ବାତାବରଣ ଦୃଷ୍ଟି
Atmospheric Vision | Full-spectrum weather & climate hazard monitor
Run: streamlit run app.py
"""

import os
import requests
import streamlit as st
import folium
import plotly.graph_objects as go
from streamlit_folium import st_folium
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
OWM_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# ── Countries ──────────────────────────────────────────────────────
COUNTRIES = {
    "AF":"Afghanistan","AL":"Albania","DZ":"Algeria","AR":"Argentina",
    "AU":"Australia","AT":"Austria","BD":"Bangladesh","BE":"Belgium",
    "BR":"Brazil","BG":"Bulgaria","CA":"Canada","CL":"Chile",
    "CN":"China","CO":"Colombia","HR":"Croatia","CZ":"Czech Republic",
    "DK":"Denmark","EG":"Egypt","ET":"Ethiopia","FI":"Finland",
    "FR":"France","DE":"Germany","GH":"Ghana","GR":"Greece",
    "HU":"Hungary","IN":"India","ID":"Indonesia","IR":"Iran",
    "IQ":"Iraq","IE":"Ireland","IL":"Israel","IT":"Italy",
    "JP":"Japan","JO":"Jordan","KE":"Kenya","KR":"South Korea",
    "KW":"Kuwait","LB":"Lebanon","LY":"Libya","MY":"Malaysia",
    "MX":"Mexico","MA":"Morocco","MM":"Myanmar","NP":"Nepal",
    "NL":"Netherlands","NZ":"New Zealand","NG":"Nigeria",
    "NO":"Norway","OM":"Oman","PK":"Pakistan","PH":"Philippines",
    "PL":"Poland","PT":"Portugal","QA":"Qatar","RO":"Romania",
    "RU":"Russia","SA":"Saudi Arabia","SN":"Senegal","RS":"Serbia",
    "ZA":"South Africa","ES":"Spain","LK":"Sri Lanka","SE":"Sweden",
    "CH":"Switzerland","SY":"Syria","TW":"Taiwan","TZ":"Tanzania",
    "TH":"Thailand","TN":"Tunisia","TR":"Turkey","UG":"Uganda",
    "UA":"Ukraine","AE":"United Arab Emirates","GB":"United Kingdom",
    "US":"United States","UZ":"Uzbekistan","VN":"Vietnam",
    "YE":"Yemen","ZM":"Zambia","ZW":"Zimbabwe",
}

# ══════════════════════════════════════════════════════════════════
# DYNAMIC THRESHOLD ENGINE
# ══════════════════════════════════════════════════════════════════

def climate_zone(lat: float) -> str:
    a = abs(lat)
    if a <= 15: return "equatorial"
    if a <= 25: return "tropical"
    if a <= 40: return "subtropical"
    if a <= 60: return "temperate"
    return "polar"

CAPE_CFG = {
    "equatorial":  ( 800,  400,  600,  300, 1500),
    "tropical":    (1000,  500,  800,  400, 2000),
    "subtropical": (1500,  800, 1200,  600, 2500),
    "temperate":   (2000, 1000, 1500,  800, 3000),
    "polar":       (3000, 2000, 2500, 1500, 4500),
}

def elev_factor(elev: float) -> float:
    if elev > 2000: return 0.60
    if elev > 1500: return 0.70
    if elev > 800:  return 0.85
    return 1.0

def hour_weight(hour: int, lat: float) -> float:
    a = abs(lat)
    peak = 15 if a <= 25 else (14 if a <= 40 else 13)
    return max(0.5, 1.0 - abs(hour - peak) * 0.055)

# ══════════════════════════════════════════════════════════════════
# WIND SCALES
# ══════════════════════════════════════════════════════════════════

def imd_wind(kmh: float) -> tuple[str, str]:
    if kmh < 15:  return "Light",           "LOW"
    if kmh < 35:  return "Moderate",        "LOW"
    if kmh < 50:  return "Fresh",           "MODERATE"
    if kmh < 62:  return "Strong",          "MODERATE"
    if kmh < 88:  return "Very Strong ⚠️",  "HIGH"
    if kmh < 117: return "Storm 🚨",         "HIGH"
    return             "Violent Storm 🆘",    "HIGH"

def beaufort_wind(kmh: float) -> tuple[int, str, str]:
    if kmh < 2:   return  0, "Calm",            "LOW"
    if kmh < 6:   return  1, "Light Air",       "LOW"
    if kmh < 12:  return  2, "Light Breeze",    "LOW"
    if kmh < 20:  return  3, "Gentle Breeze",   "LOW"
    if kmh < 29:  return  4, "Moderate Breeze", "LOW"
    if kmh < 39:  return  5, "Fresh Breeze",    "MODERATE"
    if kmh < 50:  return  6, "Strong Breeze",   "MODERATE"
    if kmh < 62:  return  7, "Near Gale",       "MODERATE"
    if kmh < 75:  return  8, "Gale",            "HIGH"
    if kmh < 89:  return  9, "Strong Gale",     "HIGH"
    if kmh < 103: return 10, "Storm",           "HIGH"
    if kmh < 118: return 11, "Violent Storm",   "HIGH"
    return              12, "Hurricane Force",   "HIGH"

# ══════════════════════════════════════════════════════════════════
# AQI
# ══════════════════════════════════════════════════════════════════

def calc_aqi(pm25: float) -> int:
    bp = [(0,12.0,0,50),(12.1,35.4,51,100),(35.5,55.4,101,150),
          (55.5,150.4,151,200),(150.5,250.4,201,300),(250.5,500.4,301,500)]
    for cl, ch, il, ih in bp:
        if cl <= pm25 <= ch:
            return round((ih-il)/(ch-cl)*(pm25-cl)+il)
    return 500 if pm25 > 500 else 0

def aqi_label(aqi: int) -> tuple[str, str]:
    if aqi <= 50:  return "Good",                  "#22c55e"
    if aqi <= 100: return "Moderate",              "#f59e0b"
    if aqi <= 150: return "Unhealthy (Sensitive)", "#f97316"
    if aqi <= 200: return "Unhealthy",             "#ef4444"
    if aqi <= 300: return "Very Unhealthy",        "#7c3aed"
    return                "Hazardous",             "#831843"

# ══════════════════════════════════════════════════════════════════
# WILDFIRE ZONE DETECTOR
# ══════════════════════════════════════════════════════════════════

def is_wildfire_zone(lat: float, humidity: float, precip: float, zone: str) -> bool:
    is_arid         = humidity < 35 and precip < 1
    is_mediterr     = zone == "subtropical" and 30 <= abs(lat) <= 45
    is_tropical_dry = zone in ("tropical","equatorial") and humidity < 45
    is_boreal       = abs(lat) > 50
    return is_arid or is_mediterr or is_tropical_dry or is_boreal

# ══════════════════════════════════════════════════════════════════
# WET BULB (Stull 2011)
# ══════════════════════════════════════════════════════════════════

def wet_bulb(temp: float, rh: float) -> float:
    return (temp*(0.5*(rh/100+0.0001)**0.333)
            + (-4.8+0.045*temp)*(1-rh/100))

# ══════════════════════════════════════════════════════════════════
# API CALLS
# ══════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400)
def geocode(city: str, state: str, cc: str) -> list:
    if not OWM_KEY: return []
    q = f"{city},{state},{cc}" if state.strip() else f"{city},{cc}"
    try:
        r = requests.get("http://api.openweathermap.org/geo/1.0/direct",
                         params={"q":q,"limit":5,"appid":OWM_KEY}, timeout=8)
        r.raise_for_status(); return r.json()
    except: return []


@st.cache_data(ttl=900)
def fetch_owm(lat: float, lon: float) -> dict | None:
    if not OWM_KEY: return None
    try:
        r = requests.get("https://api.openweathermap.org/data/2.5/weather",
                         params={"lat":lat,"lon":lon,"appid":OWM_KEY,"units":"metric"}, timeout=8)
        r.raise_for_status(); d = r.json()
        return {
            "temp_c":       round(d["main"]["temp"],1),
            "humidity_pct": d["main"]["humidity"],
            "pressure_hpa": d["main"]["pressure"],
            "cloud_pct":    d["clouds"]["all"],
            "wind_ms":      round(d["wind"]["speed"],1),
            "rain_1h":      d.get("rain",{}).get("1h",0),
            "weather_main": d["weather"][0]["main"],
            "weather_desc": d["weather"][0]["description"].title(),
        }
    except: return None


@st.cache_data(ttl=900)
def fetch_openmeteo(lat: float, lon: float) -> dict | None:
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "hourly": ",".join([
                "temperature_2m","apparent_temperature","dewpoint_2m",
                "relativehumidity_2m","precipitation_probability","precipitation",
                "cloudcover","surface_pressure","windspeed_10m","windspeed_80m",
                "windgusts_10m","cape","lifted_index","convective_inhibition",
                "freezinglevel_height","snowfall","weathercode",
                "soil_moisture_0_to_7cm","soil_moisture_7_to_28cm",
                "soil_moisture_28_to_100cm","vapour_pressure_deficit",
            ]),
            "forecast_days": 2, "timezone": "auto",
        }, timeout=12)
        r.raise_for_status()
        data  = r.json(); h = data["hourly"]; times = h["time"]
        now_s = datetime.now().strftime("%Y-%m-%dT%H:00")
        try:    idx = times.index(now_s)
        except: idx = 0

        def row(i):
            i = min(i, len(times)-1)
            return ({k:(h[k][i] if h[k][i] is not None else 0)
                     for k in h if k!="time"}
                    | {"hour": int(times[i][11:13])})

        def interp(i1, i2):
            r1,r2 = row(i1),row(i2)
            return {k:(r1[k]+r2[k])/2 for k in r1}

        def safe(key, n):
            arr = h.get(key,[])
            return [arr[idx+i] if idx+i<len(arr) and arr[idx+i] is not None else 0
                    for i in range(n)]

        t12 = [times[idx+i][11:16] if idx+i<len(times) else "" for i in range(12)]
        t24 = [times[idx+i][11:16] if idx+i<len(times) else "" for i in range(24)]

        return {
            "now":      row(idx),
            "h30min":   interp(idx, idx+1),
            "h2":       row(idx+2),
            "h6":       row(idx+6),
            "h12":      row(idx+12),
            "elevation": data.get("elevation",0),
            "raw": {
                "t12": t12, "t24": t24,
                "gusts_12":  safe("windgusts_10m",12),
                "temp_24":   safe("temperature_2m",24),
                "feels_24":  safe("apparent_temperature",24),
            },
        }
    except: return None


@st.cache_data(ttl=900)
def fetch_air_quality(lat: float, lon: float) -> dict | None:
    try:
        r = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality", params={
            "latitude": lat, "longitude": lon,
            "hourly": ",".join([
                "pm2_5","pm10","carbon_monoxide","nitrogen_dioxide",
                "ozone","dust","uv_index",
                "birch_pollen","grass_pollen","mugwort_pollen","alder_pollen",
            ]),
            "timezone": "auto",
        }, timeout=12)
        r.raise_for_status()
        data  = r.json(); h = data["hourly"]; times = h["time"]
        now_s = datetime.now().strftime("%Y-%m-%dT%H:00")
        try:    idx = times.index(now_s)
        except: idx = 0

        def val(key):
            arr = h.get(key,[])
            return round(arr[idx],2) if idx<len(arr) and arr[idx] is not None else 0.0

        pm25 = val("pm2_5")
        return {
            "pm25":    pm25,   "pm10":    val("pm10"),
            "co":      val("carbon_monoxide"),
            "no2":     val("nitrogen_dioxide"),
            "o3":      val("ozone"),   "dust":    val("dust"),
            "uv":      val("uv_index"),
            "birch":   val("birch_pollen"), "grass":   val("grass_pollen"),
            "mugwort": val("mugwort_pollen"), "alder":   val("alder_pollen"),
            "aqi":     calc_aqi(pm25),
        }
    except: return None

# ══════════════════════════════════════════════════════════════════
# RISK HELPERS
# ══════════════════════════════════════════════════════════════════

RISK_COLOR = {"HIGH":"#ef4444","MODERATE":"#f59e0b","LOW":"#22c55e"}
RISK_BG    = {"HIGH":"#fee2e2","MODERATE":"#fef3c7","LOW":"#dcfce7"}
RISK_TEXT  = {"HIGH":"#991b1b","MODERATE":"#92400e","LOW":"#166534"}
RISK_EMOJI = {"HIGH":"🔴","MODERATE":"🟡","LOW":"🟢"}

def _level(score: float, h: float, m: float) -> str:
    return "HIGH" if score>=h else "MODERATE" if score>=m else "LOW"

# ══════════════════════════════════════════════════════════════════
# SCORERS
# ══════════════════════════════════════════════════════════════════

def score_storm_rainfall(om, owm, lat, elev, is_now):
    zone=climate_zone(lat); _,_,sh,sm,_=CAPE_CFG[zone]; ef=elev_factor(elev)
    cape=om.get("cape",0) or 0; pprob=om.get("precipitation_probability",0) or 0
    prec=om.get("precipitation",0) or 0; cloud=om.get("cloudcover",0) or 0
    wcode=om.get("weathercode",0) or 0
    score,flags=0,[]
    if pprob>75:   score+=35; flags.append(f"Precipitation probability {pprob}%")
    elif pprob>50: score+=20; flags.append(f"Precipitation probability {pprob}%")
    elif pprob>30: score+=10; flags.append(f"Precipitation probability {pprob}%")
    if prec>10:   score+=30; flags.append(f"Forecast rain {prec:.1f}mm")
    elif prec>5:  score+=20; flags.append(f"Forecast rain {prec:.1f}mm")
    elif prec>2:  score+=10; flags.append(f"Forecast rain {prec:.1f}mm")
    if cape>sh*ef: score+=15; flags.append(f"CAPE {cape:.0f} J/kg")
    if cloud>70:   score+=10; flags.append(f"Cloud cover {cloud}%")
    if wcode>=200: score+=15; flags.append("Thunderstorm code active")
    if is_now and owm and owm["rain_1h"]>0:
        score+=15; flags.append(f"Active rain {owm['rain_1h']} mm/hr")
    return _level(score,60,30), flags


def score_flash_rain(om, owm, lat, elev, is_now):
    zone=climate_zone(lat); fh,fm,*_=CAPE_CFG[zone]; ef=elev_factor(elev)
    hw=hour_weight(om["hour"],lat)
    cape=om.get("cape",0) or 0; li=om.get("lifted_index",0) or 0
    cin=abs(om.get("convective_inhibition",100) or 100)
    pprob=om.get("precipitation_probability",0) or 0
    cloud=om.get("cloudcover",0) or 0; hum=om.get("relativehumidity_2m",0) or 0
    shear=abs((om.get("windspeed_80m",0) or 0)-(om.get("windspeed_10m",0) or 0))
    score,flags=0,[]
    if cape>fh*ef*hw:   score+=35; flags.append(f"CAPE {cape:.0f} J/kg — high instability")
    elif cape>fm*ef*hw: score+=20; flags.append(f"CAPE {cape:.0f} J/kg — moderate instability")
    if li<-4:  score+=25; flags.append(f"Lifted Index {li:.1f} — very unstable")
    elif li<-2:score+=15; flags.append(f"Lifted Index {li:.1f} — unstable")
    if cin<20: score+=15; flags.append(f"CIN {cin:.0f} J/kg — cap breaking")
    if pprob>70:score+=12; flags.append(f"Precip probability {pprob}%")
    if cloud>85:score+=8;  flags.append(f"Cloud cover {cloud}%")
    if hum>85:  score+=8;  flags.append(f"Humidity {hum}%")
    if shear>8: score+=7;  flags.append(f"Wind shear {shear:.1f} m/s")
    if is_now and owm:
        if owm["rain_1h"]>=7.5:score+=20;flags.append(f"Active rain {owm['rain_1h']} mm/hr (IMD heavy)")
        elif owm["rain_1h"]>0: score+=10;flags.append(f"Light rain {owm['rain_1h']} mm/hr")
        if owm["weather_main"]=="Thunderstorm":score+=15;flags.append("Thunderstorm active")
    return _level(score,65,35), flags


def score_cloudburst(om, owm, lat, elev, is_now):
    zone=climate_zone(lat); *_,cbh=CAPE_CFG[zone]; ef=elev_factor(elev)
    cape=om.get("cape",0) or 0; cin=abs(om.get("convective_inhibition",100) or 100)
    hum=om.get("relativehumidity_2m",0) or 0; li=om.get("lifted_index",0) or 0
    shear=abs((om.get("windspeed_80m",0) or 0)-(om.get("windspeed_10m",0) or 0))
    score,flags=0,[]
    cbth=cbh*ef
    if cape>cbth:        score+=40; flags.append(f"CAPE {cape:.0f} J/kg — extreme instability")
    elif cape>cbth*0.7:  score+=20; flags.append(f"CAPE {cape:.0f} J/kg — elevated")
    if cin<10:  score+=25; flags.append("CIN near zero — cap fully broken")
    elif cin<20:score+=15; flags.append(f"CIN {cin:.0f} J/kg — weakening cap")
    if li<-6:   score+=20; flags.append(f"LI {li:.1f} — extreme instability")
    if hum>90:  score+=15; flags.append(f"Humidity {hum}% — near saturated")
    if shear>12:score+=10; flags.append(f"Wind shear {shear:.1f} m/s")
    if elev>800:score+=10; flags.append(f"Elevation {elev:.0f}m — orographic risk")
    if is_now and owm and owm["rain_1h"]>50:
        score+=30; flags.append(f"⚠️ Extreme rain {owm['rain_1h']} mm/hr")
    return _level(score,60,35), flags


def score_snow_hail(om, owm, lat, elev, is_now):
    temp=om.get("temperature_2m",20) or 20
    hum=om.get("relativehumidity_2m",60) or 60
    pprob=om.get("precipitation_probability",0) or 0
    cape=om.get("cape",0) or 0
    cin=abs(om.get("convective_inhibition",100) or 100)
    shear=abs((om.get("windspeed_80m",0) or 0)-(om.get("windspeed_10m",0) or 0))
    snow_cm=om.get("snowfall",0) or 0
    frz=om.get("freezinglevel_height",6000) or 6000
    zone=climate_zone(lat); fh,*_=CAPE_CFG[zone]; ef=elev_factor(elev)
    wb=wet_bulb(temp,hum)
    ss,sf=0,[]
    if wb<=0:    ss+=40; sf.append(f"Wet bulb {wb:.1f}°C ≤ 0°C — snow-favourable")
    elif wb<=1.5:ss+=20; sf.append(f"Wet bulb {wb:.1f}°C — rain/snow mix possible")
    if temp<-2:  ss+=25; sf.append(f"Surface temp {temp:.1f}°C — well below freezing")
    elif temp<2: ss+=12; sf.append(f"Surface temp {temp:.1f}°C — near freezing")
    if pprob>50: ss+=20; sf.append(f"Precipitation probability {pprob}%")
    elif pprob>30:ss+=10
    if snow_cm>0:ss+=20; sf.append(f"Forecast snowfall {snow_cm:.1f}cm")
    if elev>1500:ss+=10; sf.append(f"High elevation {elev:.0f}m — enhances snow")
    hs,hf=0,[]
    eff_frz=frz-elev
    if cape>fh*ef:      hs+=35; hf.append(f"CAPE {cape:.0f} J/kg — strong updraft")
    elif cape>fh*ef*0.6:hs+=18; hf.append(f"CAPE {cape:.0f} J/kg — moderate updraft")
    if eff_frz<3500:    hs+=30; hf.append(f"Freezing level {frz:.0f}m — large hail favourable")
    elif eff_frz<4500:  hs+=20; hf.append(f"Freezing level {frz:.0f}m — hail-favourable")
    elif eff_frz<5500:  hs+=10; hf.append(f"Freezing level {frz:.0f}m — marginal for hail")
    if shear>12:hs+=20; hf.append(f"Wind shear {shear:.1f} m/s — strong (large hail)")
    elif shear>8:hs+=12;hf.append(f"Wind shear {shear:.1f} m/s — moderate")
    if cin<15:  hs+=15; hf.append(f"CIN {cin:.0f} — cap fully broken")
    elif cin<30:hs+=8;  hf.append(f"CIN {cin:.0f} — weakening")
    if is_now and owm and owm["weather_main"]=="Thunderstorm":
        hs+=15; hf.append("Active thunderstorm — hail possible NOW")
    return _level(ss,60,30), _level(hs,60,30), sf, hf, wb, frz


def score_extreme_wind(om, owm, is_now, country_code):
    gusts=om.get("windgusts_10m",0) or 0
    wind=om.get("windspeed_10m",0) or 0
    cape=om.get("cape",0) or 0
    shear=abs((om.get("windspeed_80m",0) or 0)-wind)
    score,flags=0,[]
    is_india=(str(country_code)=="IN")
    if is_india:
        label,lvl_raw=imd_wind(gusts)
        flags.append(f"IMD: {label} ({gusts:.0f} km/h)")
    else:
        bnum,label,lvl_raw=beaufort_wind(gusts)
        flags.append(f"Beaufort {bnum}: {label} ({gusts:.0f} km/h)")
    if lvl_raw=="HIGH":      score+=50
    elif lvl_raw=="MODERATE":score+=25
    if gusts>=88:   score+=15; flags.append("⚠️ Extreme gust — structural damage risk")
    elif gusts>=62: score+=10; flags.append("Strong gust — tree/roof damage possible")
    if cape>1000 and shear>25:
        score+=25; flags.append(f"CAPE {cape:.0f} J/kg + shear {shear:.0f} km/h — derecho/squall")
    elif cape>500 and shear>15:
        score+=12; flags.append(f"Squall line possible — CAPE {cape:.0f} J/kg")
    if is_now and owm:
        obs=owm["wind_ms"]*3.6
        if obs>60: score+=10; flags.append(f"Observed surface wind {obs:.0f} km/h")
    return _level(score,60,30), flags, gusts


def score_extreme_heat(om, owm, lat, elev, is_now):
    temp=om.get("temperature_2m",20) or 20
    feels=om.get("apparent_temperature",20) or 20
    rh=om.get("relativehumidity_2m",60) or 60
    heat_thresh=30 if elev>800 else 40
    cold_thresh=5  if elev>800 else 10
    score,flags=0,[]
    if temp>=heat_thresh+5:   score+=50;flags.append(f"Severe heat wave — {temp:.1f}°C (threshold: {heat_thresh}°C)")
    elif temp>=heat_thresh:   score+=30;flags.append(f"Heat wave — {temp:.1f}°C ≥ IMD threshold {heat_thresh}°C")
    elif temp>=heat_thresh-3: score+=15;flags.append(f"Near heat wave — {temp:.1f}°C")
    if feels>=46:  score+=25;flags.append(f"Extreme heat index {feels:.1f}°C — dangerous")
    elif feels>=40:score+=12;flags.append(f"High heat index {feels:.1f}°C")
    if temp<=cold_thresh-5:  score+=45;flags.append(f"Severe cold wave — {temp:.1f}°C")
    elif temp<=cold_thresh:  score+=25;flags.append(f"Cold wave — {temp:.1f}°C ≤ {cold_thresh}°C")
    if temp>=35 and rh>=70:  score+=10;flags.append(f"Humidity {rh}% amplifies heat stress")
    return _level(score,55,25), flags, round(temp,1), round(feels,1)


def score_wildfire(om, lat, humidity, precip, zone, elev):
    if not is_wildfire_zone(lat, humidity, precip, zone):
        return None, [], {}
    temp=om.get("temperature_2m",25) or 25
    wind=om.get("windgusts_10m",0) or 0
    sm=om.get("soil_moisture_0_to_7cm",0.2) or 0.2
    t_s=min(40,max(0,(temp-20)*1.5))
    h_s=min(30,max(0,(100-humidity)*0.4))
    w_s=min(20,max(0,wind*0.22))
    d_s=min(10,max(0,(0.3-sm)*50))
    p_p=min(30,precip*3)
    total=max(0,min(100,t_s+h_s+w_s+d_s-p_p))
    flags=[]
    if total>=60: flags.append(f"Fire Weather Index {total:.0f}/100 — extreme fire danger")
    elif total>=35:flags.append(f"Fire Weather Index {total:.0f}/100 — high fire danger")
    if humidity<20:flags.append(f"Critically low humidity {humidity:.0f}%")
    if wind>40:    flags.append(f"Strong wind {wind:.0f} km/h — rapid fire spread risk")
    if sm<0.1:     flags.append("Very dry surface soil — elevated ignition risk")
    return _level(total,60,35), flags, {
        "Temperature":round(t_s),"Low Humidity":round(h_s),
        "Wind Speed":round(w_s),"Drought Code":round(d_s),
    }


def score_agro_risk(om, lat, elev):
    precip=om.get("precipitation",0) or 0
    sm_s=om.get("soil_moisture_0_to_7cm",0.2) or 0.2
    gusts=om.get("windgusts_10m",0) or 0
    temp=om.get("temperature_2m",25) or 25
    vpd=om.get("vapour_pressure_deficit",0) or 0
    water=min(100,(precip/30*60)+max(0,(sm_s-0.35)/0.15*40))
    wind_l=min(100,gusts/80*100)
    heat_s=min(100,max(0,(temp-30)/15*100))
    frost_r=min(100,max(0,(5-temp)/10*100))
    scores={"Waterlogging":round(water),"Wind Lodging":round(wind_l),
            "Heat Stress":round(heat_s),"Frost Risk":round(frost_r)}
    flags=[]
    if water>60:  flags.append(f"Waterlogging — {precip:.1f}mm + saturated soil")
    if wind_l>60: flags.append(f"Wind lodging — gusts {gusts:.0f} km/h")
    if heat_s>60: flags.append(f"Heat stress — {temp:.1f}°C above optimal")
    if frost_r>60:flags.append(f"Frost damage — {temp:.1f}°C near/below 0°C")
    if vpd>2.5:   flags.append(f"VPD {vpd:.1f} kPa — severe plant stress")
    return _level(max(scores.values()),60,30), flags, scores


def get_soil_context(om: dict) -> dict:
    s0  = om.get("soil_moisture_0_to_7cm",    0.2) or 0.2
    s7  = om.get("soil_moisture_7_to_28cm",   0.2) or 0.2
    s28 = om.get("soil_moisture_28_to_100cm", 0.2) or 0.2
    def fc(v): return ("HIGH flood/runoff — surface saturated" if v>0.42
                       else "MODERATE — elevated runoff possible" if v>0.32
                       else "LOW — surface absorbing normally")
    def ac(v,d): return (f"Waterlogged — root rot risk ({d})" if v>0.42
                         else f"Optimal moisture ({d})" if v>0.30
                         else f"Below optimal — mild drought stress ({d})" if v>0.15
                         else f"Drought stress — irrigation needed ({d})")
    return {
        "surface": {"v":s0,  "flood":fc(s0),  "agro":ac(s0,"0–7cm")},
        "shallow": {"v":s7,  "flood":"—",      "agro":ac(s7,"7–28cm")},
        "deep":    {"v":s28, "flood":"—",      "agro":ac(s28,"28–100cm")},
    }

# ══════════════════════════════════════════════════════════════════
# CHART FUNCTIONS
# ══════════════════════════════════════════════════════════════════

TRANSPARENT = "rgba(0,0,0,0)"

def chart_wind(raw, is_india):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=raw["t12"], y=raw["gusts_12"], mode="lines+markers",
        line=dict(color="#7c3aed",width=2.5),
        fill="tozeroy", fillcolor="rgba(124,58,237,0.1)", name="Gusts km/h"))
    lbl1 = "Very Strong (IMD 62)" if is_india else "Gale (Beaufort 8, 62)"
    lbl2 = "Storm (IMD 88)"        if is_india else "Storm (Beaufort 10, 89)"
    fig.add_hline(y=62,line_dash="dash",line_color="#f97316",
                  annotation_text=lbl1,annotation_position="top right")
    fig.add_hline(y=88,line_dash="dash",line_color="#ef4444",
                  annotation_text=lbl2,annotation_position="top right")
    fig.update_layout(height=250,margin=dict(t=10,b=10,l=10,r=120),
                      yaxis_title="km/h",xaxis_title="Next 12 hours",
                      plot_bgcolor=TRANSPARENT,paper_bgcolor=TRANSPARENT,
                      legend=dict(orientation="h"))
    return fig


def chart_heat(raw, heat_thresh, cold_thresh):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=raw["t24"],y=raw["temp_24"],name="Temperature °C",
                             line=dict(color="#ef4444",width=2.5)))
    fig.add_trace(go.Scatter(x=raw["t24"],y=raw["feels_24"],name="Feels Like °C",
                             line=dict(color="#f97316",width=2,dash="dash")))
    fig.add_hline(y=heat_thresh,line_dash="dot",line_color="#ef4444",
                  annotation_text=f"Heat Wave ({heat_thresh}°C)",annotation_position="top right")
    fig.add_hline(y=cold_thresh,line_dash="dot",line_color="#3b82f6",
                  annotation_text=f"Cold Wave ({cold_thresh}°C)",annotation_position="bottom right")
    fig.update_layout(height=250,margin=dict(t=10,b=10,l=10,r=120),
                      yaxis_title="°C",xaxis_title="Next 24 hours",
                      plot_bgcolor=TRANSPARENT,paper_bgcolor=TRANSPARENT,
                      legend=dict(orientation="h"))
    return fig


def chart_air_quality(aq):
    who  = {"PM2.5":15,"PM10":45,"NO₂":200,"O₃":100,"Dust":50}
    vals = [aq["pm25"],aq["pm10"],aq["no2"],aq["o3"],aq["dust"]]
    pcts = [min(250,v/w*100) for v,w in zip(vals,who.values())]
    cols = ["#ef4444" if p>100 else "#f59e0b" if p>60 else "#22c55e" for p in pcts]
    fig  = go.Figure(go.Bar(
        x=list(who.keys()),y=pcts,marker_color=cols,
        text=[f"{v:.1f} µg/m³" for v in vals],textposition="outside"))
    fig.add_hline(y=100,line_dash="dash",line_color="#ef4444",annotation_text="WHO Limit")
    fig.update_layout(height=270,margin=dict(t=30,b=10,l=10,r=10),
                      yaxis_title="% of WHO Guideline",yaxis_range=[0,270],
                      plot_bgcolor=TRANSPARENT,paper_bgcolor=TRANSPARENT)
    return fig


def chart_wildfire(comp):
    maxes={"Temperature":40,"Low Humidity":30,"Wind Speed":20,"Drought Code":10}
    fig=go.Figure(go.Bar(
        x=list(comp.keys()),y=list(comp.values()),
        marker_color=["#ef4444","#f97316","#7c3aed","#92400e"],
        text=[f"{v}/{maxes[k]}" for k,v in comp.items()],textposition="outside"))
    fig.update_layout(height=250,margin=dict(t=20,b=10,l=10,r=10),
                      yaxis_title="Score",yaxis_range=[0,45],
                      plot_bgcolor=TRANSPARENT,paper_bgcolor=TRANSPARENT)
    return fig


def chart_agro_radar(scores):
    cats=list(scores.keys())+[list(scores.keys())[0]]
    vals=list(scores.values())+[list(scores.values())[0]]
    fig=go.Figure(go.Scatterpolar(
        r=vals,theta=cats,fill="toself",
        line_color="#16a34a",fillcolor="rgba(22,163,74,0.2)"))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True,range=[0,100],tickvals=[25,50,75,100])),
        height=300,margin=dict(t=20,b=20,l=40,r=40),paper_bgcolor=TRANSPARENT)
    return fig


def chart_soil_gauge(value, title):
    color=("#ef4444" if value>0.42 else "#3b82f6" if value>0.30
           else "#22c55e" if value>0.15 else "#f59e0b")
    fig=go.Figure(go.Indicator(
        mode="gauge+number",value=round(value,3),
        title={"text":title,"font":{"size":13}},
        number={"suffix":" m³/m³","font":{"size":14}},
        gauge={"axis":{"range":[0,0.5],"tickwidth":1},
               "bar":{"color":color},
               "steps":[{"range":[0.00,0.10],"color":"#fef3c7"},
                         {"range":[0.10,0.25],"color":"#dcfce7"},
                         {"range":[0.25,0.38],"color":"#bfdbfe"},
                         {"range":[0.38,0.50],"color":"#fee2e2"}],
               "threshold":{"line":{"color":"red","width":3},"value":0.42}}))
    fig.update_layout(height=190,margin=dict(t=50,b=5,l=10,r=10),
                      paper_bgcolor=TRANSPARENT)
    return fig

# ══════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════

def risk_badge(level):
    return (f'<span style="background:{RISK_BG[level]};color:{RISK_TEXT[level]};'
            f'border-radius:20px;padding:3px 14px;font-weight:700;font-size:13px;">'
            f'{RISK_EMOJI[level]} {level}</span>')

def time_card(title, level, flags, extra=""):
    c=RISK_COLOR[level]
    fh="".join(f'<div style="font-size:12px;margin-top:3px;">⚡ {f}</div>' for f in flags) \
       or '<div style="font-size:12px;color:#6b7280;margin-top:3px;">✅ No triggers</div>'
    ex=f'<div style="font-size:11px;color:#6b7280;margin-top:6px;">{extra}</div>' if extra else ""
    return (f'<div style="background:#fff;border:1.5px solid {c};border-radius:12px;'
            f'padding:14px 16px;height:100%;box-shadow:0 2px 8px {c}22;">'
            f'<div style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;'
            f'letter-spacing:.06em;margin-bottom:6px;">{title}</div>'
            f'<div style="margin-bottom:8px;">{risk_badge(level)}</div>{fh}{ex}</div>')

def section_header(icon, title, subtitle, color):
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{color}22,transparent);'
        f'border-left:4px solid {color};border-radius:8px;padding:12px 18px;margin:1rem 0 0.8rem;">'
        f'<div style="font-size:17px;font-weight:700;color:{color}">{icon} {title}</div>'
        f'<div style="font-size:12px;color:#6b7280;margin-top:2px;">{subtitle}</div></div>',
        unsafe_allow_html=True)

def group_header(label, color):
    st.markdown(
        f'<div style="font-size:15px;font-weight:800;color:{color};padding:8px 0 4px;'
        f'border-bottom:2px solid {color};margin:1.4rem 0 8px;">{label}</div>',
        unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# PAGE SETUP
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Vatavaram Drusti", page_icon="🌦️", layout="wide")
st.markdown("""<style>
  .block-container{padding-top:1rem;}
  div[data-testid="stHorizontalBlock"]{gap:12px;}
  .stTabs [data-baseweb="tab"]{font-size:13px;font-weight:600;padding:8px 14px;}
</style>""", unsafe_allow_html=True)

# ── CHANGE 1: Odia subtitle ── ବାତାବରଣ ଦୃଷ୍ଟି
st.markdown("""
<div style="background:linear-gradient(135deg,#0f172a,#1e3a5f,#0c4a6e);
            border-radius:16px;padding:24px 32px;margin-bottom:1.2rem;color:white;">
  <div style="font-size:26px;font-weight:800;letter-spacing:-0.5px;">
    🌦️ Vatavaram Drusti
    <span style="font-size:14px;opacity:0.65;font-weight:400;margin-left:8px;">ବାତାବରଣ ଦୃଷ୍ଟି</span>
  </div>
  <div style="font-size:13px;opacity:0.8;margin-top:4px;">
    Full-spectrum atmospheric hazard monitor — any city worldwide
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:18px;margin-top:12px;font-size:12px;opacity:0.7;">
    <span>📡 OpenWeatherMap</span>
    <span>🌐 Open-Meteo Forecast + Air Quality</span>
    <span>🧠 Dynamic climate-zone + elevation thresholds</span>
    <span>🌦 Weather Info &nbsp;|&nbsp; 🌍 Climate Intelligence</span>
  </div>
</div>""", unsafe_allow_html=True)

if not OWM_KEY:
    st.error("Add `OPENWEATHER_API_KEY=your_key` to `.env` and restart.")
    st.stop()

# ── Search ─────────────────────────────────────────────────────────
st.markdown("#### 📍 Search Location")
c1,c2,c3,c4=st.columns([2.5,2,2.5,1])
clist=sorted(COUNTRIES.values())
with c1: cname=st.selectbox("Country",clist,index=clist.index("India"))
ccode=next(k for k,v in COUNTRIES.items() if v==cname)
with c2: state_in=st.text_input("State / Province",placeholder="e.g. Karnataka (optional)")
with c3: city_in=st.text_input("City",placeholder="e.g. Bengaluru",
                                value="Bengaluru" if cname=="India" else "")
with c4:
    st.markdown("<br>",unsafe_allow_html=True)
    search=st.button("🔍 Search",use_container_width=True)

# ── CHANGE 2: single city — stores only one location at a time ─────
if "location" not in st.session_state:
    st.session_state.location = None

if search:
    if not city_in.strip():
        st.warning("Enter a city name.")
    else:
        with st.spinner(f"Locating {city_in}..."):
            geo=geocode(city_in.strip(),state_in.strip(),ccode)
        if not geo:
            st.error(f"Could not find **{city_in}** in {cname}.")
        else:
            loc=geo[0]; state=loc.get("state","") or ""
            label=f"{loc['name']}{', '+state if state else ''}, {cname}"
            with st.spinner("Fetching weather & air quality..."):
                owm=fetch_owm(loc["lat"],loc["lon"])
                om =fetch_openmeteo(loc["lat"],loc["lon"])
                aq =fetch_air_quality(loc["lat"],loc["lon"])
            if owm and om:
                # Always replace — new city overwrites the previous one
                st.session_state.location = {
                    "label": label,
                    "lat":   loc["lat"],
                    "lon":   loc["lon"],
                    "cc":    loc.get("country", ccode),
                    "owm":   owm,
                    "om":    om,
                    "aq":    aq or {},
                }
                st.success(f"Showing data for **{label}**")
            else:
                st.error("Data fetch failed. Check API key or try again.")

if st.session_state.location:
    if st.button("🗑️ Clear"):
        st.session_state.location = None; st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════
# MAIN DISPLAY — single city only
# ══════════════════════════════════════════════════════════════════
loc = st.session_state.location

if not loc:
    st.markdown("""
    <div style="text-align:center;padding:3rem 1rem;color:#6b7280;">
      <div style="font-size:52px;">🌤️</div>
      <div style="font-size:16px;margin-top:10px;font-weight:500;">Search any city above to begin monitoring</div>
      <div style="font-size:13px;margin-top:6px;">Storm · Flash Rain · Cloudburst · Snow · Hail · Wind · Heat · Air Quality · Wildfire · Agro · Soil</div>
    </div>""", unsafe_allow_html=True)
else:
    ow=loc["owm"]; om=loc["om"]; aq=loc["aq"]
    elev=om["elevation"]; lat=loc["lat"]; zone=climate_zone(lat)
    is_india=(str(loc.get("cc",""))=="IN")

    # ── Map + current conditions ───────────────────────────────────
    mc,ic=st.columns([3,2])
    with mc:
        st.markdown("#### 🗺️ Live Risk Map")
        m=folium.Map(location=[lat,loc["lon"]],zoom_start=9,tiles="CartoDB positron")
        lvl,_=score_flash_rain(om["now"],ow,lat,elev,True)
        cm={"HIGH":"red","MODERATE":"orange","LOW":"green"}
        ov=om["now"]
        folium.CircleMarker(
            location=[lat,loc["lon"]],radius=22,
            color=cm[lvl],fill=True,fill_opacity=0.65,
            popup=folium.Popup(
                f"<b>{loc['label']}</b><br>Flash Rain: <b>{lvl}</b><br>"
                f"🌡 {ow['temp_c']}°C  💧 {ow['humidity_pct']}%<br>"
                f"CAPE: {ov.get('cape',0):.0f} J/kg  Gusts: {ov.get('windgusts_10m',0):.0f} km/h",
                max_width=210),
            tooltip=f"{loc['label']} — {lvl}",
        ).add_to(m)
        st_folium(m,width=None,height=410)

    with ic:
        st.markdown(f"#### 📊 {loc['label']}")
        st.markdown(f"**{ow['weather_desc']}**")
        a,b,c=st.columns(3)
        a.metric("Temp",     f"{ow['temp_c']}°C")
        b.metric("Humidity", f"{ow['humidity_pct']}%")
        c.metric("Rain",     f"{ow['rain_1h']} mm/hr")
        d,e,f=st.columns(3)
        d.metric("CAPE",     f"{om['now'].get('cape',0):.0f} J/kg")
        e.metric("LI",       f"{om['now'].get('lifted_index',0):.1f}")
        f.metric("Gusts",    f"{om['now'].get('windgusts_10m',0):.0f} km/h")
        g,h,i=st.columns(3)
        g.metric("Pressure", f"{ow['pressure_hpa']} hPa")
        h.metric("Cloud",    f"{ow['cloud_pct']}%")
        i.metric("Wind",     f"{ow['wind_ms']} m/s")
        st.caption(f"🌍 {zone.title()} · {elev:.0f}m elevation · "
                   f"{lat:.2f}°, {loc['lon']:.2f}° · "
                   f"Updated: {datetime.now().strftime('%H:%M')}")

    st.divider()

    # ══════════════════════════════════════════════════════════════
    # WEATHER INFO
    # ══════════════════════════════════════════════════════════════
    group_header("🌦 Weather Info", "#1e40af")
    w1,w2,w3,w4,w5,w6=st.tabs([
        "🌧 Storm Rainfall","⛈️ Flash Rain","💥 Cloudburst",
        "❄️🧊 Snow & Hail","💨 Extreme Wind","🌡 Extreme Heat",
    ])

    with w1:
        section_header("🌧","Storm Rainfall",
                       "Sustained heavy rain · IMD >64.5mm/24hr · 6–12hr forecast","#3b82f6")
        ln,fn=score_storm_rainfall(om["now"],ow,lat,elev,True)
        l6,f6=score_storm_rainfall(om["h6"],None,lat,elev,False)
        l12,f12=score_storm_rainfall(om["h12"],None,lat,elev,False)
        a,b,c=st.columns(3)
        with a: st.markdown(time_card("🕐 Current",ln,fn,
            f"Precip prob: {om['now'].get('precipitation_probability',0)}%"),unsafe_allow_html=True)
        with b: st.markdown(time_card("🕕 +6 Hours",l6,f6,
            f"Precip prob: {om['h6'].get('precipitation_probability',0)}%"),unsafe_allow_html=True)
        with c: st.markdown(time_card("🕛 +12 Hours",l12,f12,
            f"Precip prob: {om['h12'].get('precipitation_probability',0)}%"),unsafe_allow_html=True)

    with w2:
        section_header("⛈️","Flash Rain",
                       "Intense burst · IMD >50mm/1–2hr · CAPE + Lifted Index nowcast","#f97316")
        ln,fn=score_flash_rain(om["now"],ow,lat,elev,True)
        l2,f2=score_flash_rain(om["h2"],None,lat,elev,False)
        l6,f6=score_flash_rain(om["h6"],None,lat,elev,False)
        a,b,c=st.columns(3)
        with a: st.markdown(time_card("🕐 Current",ln,fn,
            f"CAPE: {om['now'].get('cape',0):.0f} J/kg · LI: {om['now'].get('lifted_index',0):.1f}"),unsafe_allow_html=True)
        with b: st.markdown(time_card("🕑 +2 Hours",l2,f2,
            f"CAPE: {om['h2'].get('cape',0):.0f} J/kg"),unsafe_allow_html=True)
        with c: st.markdown(time_card("🕕 +6 Hours",l6,f6,
            f"CAPE: {om['h6'].get('cape',0):.0f} J/kg"),unsafe_allow_html=True)
        fh,fm,*_=CAPE_CFG[zone]; ef=elev_factor(elev)
        st.info(f"🧠 Climate zone: **{zone.title()}** · Elevation: **{elev:.0f}m** · "
                f"CAPE HIGH threshold: **{fh*ef:.0f} J/kg** · MODERATE: **{fm*ef:.0f} J/kg**")

    with w3:
        section_header("💥","Cloudburst",
                       "Extreme · IMD 100mm+/hr · Conditions flagged — needs Doppler radar for precision","#dc2626")
        ln,fn=score_cloudburst(om["now"],ow,lat,elev,True)
        l3,f3=score_cloudburst(om["h30min"],None,lat,elev,False)
        a,b=st.columns(2)
        with a: st.markdown(time_card("🕐 Current",ln,fn,
            f"CAPE: {om['now'].get('cape',0):.0f} J/kg · CIN: {abs(om['now'].get('convective_inhibition',0) or 0):.0f} J/kg"),unsafe_allow_html=True)
        with b: st.markdown(time_card("⏱️ ~30 Min",l3,f3,"Interpolated from hourly data"),unsafe_allow_html=True)
        st.warning("⚠️ Cloudburst prediction requires Doppler radar. This panel flags dangerous atmospheric setups only.")

    with w4:
        section_header("❄️🧊","Snow & Hail",
                       "Snow: Stull wet bulb ≤0°C + precip · Hail: CAPE + effective freezing level + shear","#6366f1")
        sn0,hn0,sf0,hf0,wb0,fz0=score_snow_hail(om["now"],ow,lat,elev,True)
        sn2,hn2,sf2,hf2,wb2,fz2=score_snow_hail(om["h2"],None,lat,elev,False)
        sn6,hn6,sf6,hf6,wb6,fz6=score_snow_hail(om["h6"],None,lat,elev,False)
        st.markdown('<div style="font-size:13px;font-weight:700;color:#6366f1;margin:4px 0 6px;">❄️ Snow Risk</div>',unsafe_allow_html=True)
        a,b,c=st.columns(3)
        with a: st.markdown(time_card("🕐 Current",sn0,sf0,f"Wet bulb: {wb0:.1f}°C"),unsafe_allow_html=True)
        with b: st.markdown(time_card("🕑 +3 Hours",sn2,sf2,f"Wet bulb: {wb2:.1f}°C"),unsafe_allow_html=True)
        with c: st.markdown(time_card("🕕 +6 Hours",sn6,sf6,f"Wet bulb: {wb6:.1f}°C"),unsafe_allow_html=True)
        st.markdown('<div style="font-size:13px;font-weight:700;color:#0891b2;margin:10px 0 6px;">🧊 Hail Risk</div>',unsafe_allow_html=True)
        d,e,f=st.columns(3)
        with d: st.markdown(time_card("🕐 Current",hn0,hf0,f"Freezing level: {fz0:.0f}m"),unsafe_allow_html=True)
        with e: st.markdown(time_card("🕑 +3 Hours",hn2,hf2,f"Freezing level: {fz2:.0f}m"),unsafe_allow_html=True)
        with f: st.markdown(time_card("🕕 +6 Hours",hn6,hf6,f"Freezing level: {fz6:.0f}m"),unsafe_allow_html=True)
        st.info(f"🧠 Elevation: {elev:.0f}m · Effective freezing level above ground: {fz0-elev:.0f}m · "
                f"Wet bulb now: {wb0:.1f}°C · Snow needs wet bulb ≤ 0°C")
        if abs(lat)<20:
            st.warning("🌴 Tropical location — snow is climatologically rare except above 3000m elevation.")

    with w5:
        scale=("IMD scale — India" if is_india else "Beaufort scale — International")
        section_header("💨","Extreme Wind",
                       f"Gust nowcast · Derecho/squall detection · {scale}","#7c3aed")
        ln,fn,g0=score_extreme_wind(om["now"],ow,True,loc.get("cc",""))
        l3,f3,g3=score_extreme_wind(om["h2"],None,False,loc.get("cc",""))
        l6,f6,g6=score_extreme_wind(om["h6"],None,False,loc.get("cc",""))
        a,b,c=st.columns(3)
        with a: st.markdown(time_card("🕐 Current",ln,fn,f"Gust: {g0:.0f} km/h"),unsafe_allow_html=True)
        with b: st.markdown(time_card("🕑 +3 Hours",l3,f3,f"Gust: {g3:.0f} km/h"),unsafe_allow_html=True)
        with c: st.markdown(time_card("🕕 +6 Hours",l6,f6,f"Gust: {g6:.0f} km/h"),unsafe_allow_html=True)
        st.markdown("**12-Hour Wind Gust Forecast**")
        st.plotly_chart(chart_wind(om["raw"],is_india),use_container_width=True)
        st.caption("⚡ Bareilly-type squall events flagged when CAPE >1000 J/kg + wind shear >25 km/h simultaneously")

    with w6:
        ht=30 if elev>800 else 40; ct=5 if elev>800 else 10
        section_header("🌡","Extreme Heat / Cold Wave",
                       "IMD heat wave >40°C plains / >30°C hills · Cold wave <10°C plains / <5°C hills","#f59e0b")
        ln,fn,t0,fl0=score_extreme_heat(om["now"],ow,lat,elev,True)
        l6,f6,t6,fl6=score_extreme_heat(om["h6"],None,lat,elev,False)
        l12,f12,t12,fl12=score_extreme_heat(om["h12"],None,lat,elev,False)
        a,b,c=st.columns(3)
        with a: st.markdown(time_card("🕐 Current",ln,fn,f"Temp: {t0}°C · Feels: {fl0}°C"),unsafe_allow_html=True)
        with b: st.markdown(time_card("🕕 +6 Hours",l6,f6,f"Temp: {t6}°C · Feels: {fl6}°C"),unsafe_allow_html=True)
        with c: st.markdown(time_card("🕛 +12 Hours",l12,f12,f"Temp: {t12}°C · Feels: {fl12}°C"),unsafe_allow_html=True)
        st.markdown("**24-Hour Temperature Forecast**")
        st.plotly_chart(chart_heat(om["raw"],ht,ct),use_container_width=True)

    # ══════════════════════════════════════════════════════════════
    # CLIMATE INTELLIGENCE
    # ══════════════════════════════════════════════════════════════
    group_header("🌍 Climate Intelligence", "#065f46")
    c1t,c2t,c3t,c4t=st.tabs([
        "💨 Air Quality","🔥 Wildfire","🌾 Agro Risk","💧 Soil & Drought",
    ])

    with c1t:
        section_header("💨","Air Quality",
                       "PM2.5 · PM10 · NO₂ · O₃ · CO · Dust · UV · Pollen (4 types) — Open-Meteo AQ API","#0891b2")
        if not aq:
            st.info("Air quality data unavailable for this location.")
        else:
            aqi_v=aq["aqi"]; albl,acol=aqi_label(aqi_v)
            abg=("#fee2e2" if aqi_v>150 else "#fef3c7" if aqi_v>50 else "#dcfce7")
            a,b,c,d=st.columns(4)
            a.markdown(f'<div style="background:{abg};border-radius:10px;padding:12px;text-align:center;">'
                       f'<div style="font-size:11px;color:#6b7280;">AQI (PM2.5 based)</div>'
                       f'<div style="font-size:30px;font-weight:700;color:{acol}">{aqi_v}</div>'
                       f'<div style="font-size:12px;color:{acol}">{albl}</div></div>',unsafe_allow_html=True)
            b.metric("UV Index", f"{aq['uv']:.1f}",
                     help="<3 Low · 3-5 Moderate · 6-7 High · 8-10 Very High · 11+ Extreme")
            c.metric("Dust",     f"{aq['dust']:.1f} µg/m³")
            d.metric("CO",       f"{aq['co']:.0f} µg/m³",help="WHO 1hr: 30,000 µg/m³")
            st.markdown("**Pollutants vs WHO Guidelines**")
            st.plotly_chart(chart_air_quality(aq),use_container_width=True)
            st.markdown("**Detailed Readings**")
            r1,r2,r3,r4=st.columns(4)
            r1.metric("PM2.5", f"{aq['pm25']:.1f} µg/m³",help="WHO: 15 µg/m³")
            r2.metric("PM10",  f"{aq['pm10']:.1f} µg/m³",help="WHO: 45 µg/m³")
            r3.metric("NO₂",   f"{aq['no2']:.1f} µg/m³", help="WHO hourly: 200 µg/m³")
            r4.metric("Ozone", f"{aq['o3']:.1f} µg/m³",  help="WHO 8hr: 100 µg/m³")
            st.markdown("**Pollen Levels (grains/m³)**")
            p1,p2,p3,p4=st.columns(4)
            p1.metric("Birch",   f"{aq['birch']:.0f}")
            p2.metric("Grass",   f"{aq['grass']:.0f}")
            p3.metric("Mugwort", f"{aq['mugwort']:.0f}")
            p4.metric("Alder",   f"{aq['alder']:.0f}")
            st.caption("Pollen: 0–10 Low · 10–30 Moderate · 30–100 High · >100 Very High (grains/m³)")

    with c2t:
        section_header("🔥","Wildfire Weather Index",
                       "FWI-based scoring · Auto-flagged for arid / Mediterranean / boreal zones only","#dc2626")
        hum_n=ow["humidity_pct"]; prec_n=om["now"].get("precipitation",0) or 0
        wlvl,wflags,wcomp=score_wildfire(om["now"],lat,hum_n,prec_n,zone,elev)
        if wlvl is None:
            st.success(
                f"✅ **Not a wildfire-prone zone.**  \n"
                f"Climate zone: **{zone.title()}** · Humidity: **{hum_n}%**  \n"
                f"Location does not meet arid / Mediterranean / boreal forest criteria.")
        else:
            a,b=st.columns([1,2])
            with a: st.markdown(time_card("🔥 Fire Weather Now",wlvl,wflags,
                                          f"Humidity: {hum_n}% · Precip: {prec_n:.1f}mm"),
                                unsafe_allow_html=True)
            with b:
                if wcomp:
                    st.markdown("**FWI Component Scores**")
                    st.plotly_chart(chart_wildfire(wcomp),use_container_width=True)
            st.warning("⚠️ FWI flags dangerous weather — not confirmed fire occurrence.")

    with c3t:
        section_header("🌾","Agrometeorological Risk Score",
                       "Waterlogging · Wind lodging · Heat stress · Frost risk · VPD — no crop-specific warnings","#16a34a")
        alvl,aflags,ascores=score_agro_risk(om["now"],lat,elev)
        vpd=om["now"].get("vapour_pressure_deficit",0) or 0
        a,b=st.columns([1,1])
        with a:
            st.markdown(time_card("🌾 Overall Agro Risk",alvl,aflags,"Current conditions"),
                        unsafe_allow_html=True)
            st.markdown("<br>",unsafe_allow_html=True)
            r1,r2=st.columns(2)
            r1.metric("Waterlogging",f"{ascores['Waterlogging']}/100")
            r2.metric("Wind Lodging", f"{ascores['Wind Lodging']}/100")
            r3,r4=st.columns(2)
            r3.metric("Heat Stress",  f"{ascores['Heat Stress']}/100")
            r4.metric("Frost Risk",   f"{ascores['Frost Risk']}/100")
            vpdlbl=("Severe plant stress" if vpd>2.5 else
                    "Moderate stress" if vpd>1.5 else "Within acceptable range")
            st.info(f"💧 VPD: **{vpd:.2f} kPa** — {vpdlbl}")
        with b:
            st.markdown("**Stress Radar Chart**")
            st.plotly_chart(chart_agro_radar(ascores),use_container_width=True)

    with c4t:
        section_header("💧","Soil Moisture & Drought",
                       "Current snapshot only — Surface: flood context · Deep: agriculture context","#1d4ed8")
        soil=get_soil_context(om["now"])
        st.markdown("**🌊 Surface (0–7cm) — Flood & Runoff Context**")
        g1,g2,g3=st.columns([1,2,2])
        with g1: st.plotly_chart(chart_soil_gauge(soil["surface"]["v"],"0–7cm"),use_container_width=True)
        with g2: st.markdown(
            f'<div style="background:#f0f9ff;border-radius:10px;padding:14px;margin-top:8px;">'
            f'<div style="font-size:11px;color:#6b7280;margin-bottom:4px;">🌊 FLOOD</div>'
            f'<div style="font-size:13px;font-weight:600;">{soil["surface"]["flood"]}</div>'
            f'<div style="font-size:12px;color:#6b7280;margin-top:6px;">Value: {soil["surface"]["v"]:.3f} m³/m³</div>'
            f'</div>',unsafe_allow_html=True)
        with g3: st.markdown(
            f'<div style="background:#f0fdf4;border-radius:10px;padding:14px;margin-top:8px;">'
            f'<div style="font-size:11px;color:#6b7280;margin-bottom:4px;">🌱 AGRO</div>'
            f'<div style="font-size:13px;font-weight:600;">{soil["surface"]["agro"]}</div>'
            f'</div>',unsafe_allow_html=True)
        st.markdown("**🌱 Shallow Root Zone (7–28cm) — Crop Root Agriculture**")
        g4,g5,_=st.columns([1,3,1])
        with g4: st.plotly_chart(chart_soil_gauge(soil["shallow"]["v"],"7–28cm"),use_container_width=True)
        with g5: st.markdown(
            f'<div style="background:#f0fdf4;border-radius:10px;padding:14px;margin-top:8px;">'
            f'<div style="font-size:11px;color:#6b7280;margin-bottom:4px;">🌱 AGRO</div>'
            f'<div style="font-size:13px;font-weight:600;">{soil["shallow"]["agro"]}</div>'
            f'<div style="font-size:12px;color:#6b7280;margin-top:6px;">Value: {soil["shallow"]["v"]:.3f} m³/m³</div>'
            f'</div>',unsafe_allow_html=True)
        st.markdown("**🏜 Deep Root Zone (28–100cm) — Drought & Deep Agriculture**")
        g6,g7,_=st.columns([1,3,1])
        with g6: st.plotly_chart(chart_soil_gauge(soil["deep"]["v"],"28–100cm"),use_container_width=True)
        with g7: st.markdown(
            f'<div style="background:#fefce8;border-radius:10px;padding:14px;margin-top:8px;">'
            f'<div style="font-size:11px;color:#6b7280;margin-bottom:4px;">🏜 DROUGHT</div>'
            f'<div style="font-size:13px;font-weight:600;">{soil["deep"]["agro"]}</div>'
            f'<div style="font-size:12px;color:#6b7280;margin-top:6px;">Value: {soil["deep"]["v"]:.3f} m³/m³</div>'
            f'</div>',unsafe_allow_html=True)
        st.markdown("""
        <div style="font-size:11px;color:#9ca3af;margin-top:14px;">
        Soil scale: <span style="color:#f59e0b">■ 0–0.10 Very dry</span> &nbsp;
        <span style="color:#22c55e">■ 0.10–0.25 Optimal</span> &nbsp;
        <span style="color:#3b82f6">■ 0.25–0.38 Wet</span> &nbsp;
        <span style="color:#ef4444">■ 0.38+ Saturated / flood risk</span>
        </div>""",unsafe_allow_html=True)

    st.divider()
    st.caption(
        f"Updated: {datetime.now().strftime('%d %b %Y, %H:%M')} · "
        "OpenWeatherMap (current) · Open-Meteo Forecast + Air Quality (free) · "
        "IMD thresholds · Beaufort/IMD wind scales · ERA6 integration planned 2027"
    )