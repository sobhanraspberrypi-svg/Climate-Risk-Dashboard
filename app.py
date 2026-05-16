"""
Flash Rainfall Predictor — Worldwide Monitor
Storm Rainfall | Flash Rain | Cloudburst
Run: streamlit run app.py
"""

import os
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
OWM_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# ── Countries ─────────────────────────────────────────────────────
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
# DYNAMIC THRESHOLD ENGINE  (no city hardcoding)
# ══════════════════════════════════════════════════════════════════

def climate_zone(lat: float) -> str:
    """Derive climate zone purely from latitude."""
    a = abs(lat)
    if a <= 15:  return "equatorial"   # Amazon, Congo, SE Asia
    if a <= 25:  return "tropical"     # India, Mexico, sub-Saharan
    if a <= 40:  return "subtropical"  # Mediterranean, S China, SE USA
    if a <= 60:  return "temperate"    # Europe, N USA, Japan
    return "polar"

# CAPE thresholds (J/kg) — lower in tropics because moisture is already high
CAPE_CFG = {
    #               flash_h  flash_m  storm_h  storm_m  cb_h
    "equatorial":  ( 800,     400,     600,     300,    1500),
    "tropical":    (1000,     500,     800,     400,    2000),
    "subtropical": (1500,     800,    1200,     600,    2500),
    "temperate":   (2000,    1000,    1500,     800,    3000),
    "polar":       (3000,    2000,    2500,    1500,    4500),
}

def elev_factor(elev_m: float) -> float:
    """Higher elevation → lower CAPE threshold for same risk."""
    if elev_m > 2000: return 0.60
    if elev_m > 1500: return 0.70
    if elev_m > 800:  return 0.85
    return 1.0

def hour_weight(hour: int, lat: float) -> float:
    """
    Afternoon convection peak — tropics 15:00, subtropics 14:00, temperate 13:00.
    Returns multiplier 0.5–1.0. Penalises night-time CAPE scores.
    """
    a = abs(lat)
    peak = 15 if a <= 25 else (14 if a <= 40 else 13)
    return max(0.5, 1.0 - abs(hour - peak) * 0.055)

# ══════════════════════════════════════════════════════════════════
# API CALLS
# ══════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400)
def geocode(city: str, state: str, cc: str) -> list:
    if not OWM_KEY: return []
    q = f"{city},{state},{cc}" if state.strip() else f"{city},{cc}"
    try:
        r = requests.get("http://api.openweathermap.org/geo/1.0/direct",
                         params={"q": q, "limit": 5, "appid": OWM_KEY}, timeout=8)
        r.raise_for_status()
        return r.json()
    except: return []


@st.cache_data(ttl=900)
def fetch_owm(lat: float, lon: float) -> dict | None:
    if not OWM_KEY: return None
    try:
        r = requests.get("https://api.openweathermap.org/data/2.5/weather",
                         params={"lat": lat, "lon": lon, "appid": OWM_KEY, "units": "metric"},
                         timeout=8)
        r.raise_for_status()
        d = r.json()
        return {
            "temp_c":        round(d["main"]["temp"], 1),
            "humidity_pct":  d["main"]["humidity"],
            "pressure_hpa":  d["main"]["pressure"],
            "cloud_pct":     d["clouds"]["all"],
            "wind_ms":       round(d["wind"]["speed"], 1),
            "rain_1h":       d.get("rain", {}).get("1h", 0),
            "weather_main":  d["weather"][0]["main"],
            "weather_desc":  d["weather"][0]["description"].title(),
        }
    except: return None


@st.cache_data(ttl=900)
def fetch_openmeteo(lat: float, lon: float) -> dict | None:
    """
    Fetches hourly atmospheric data from Open-Meteo (free, no key).
    Returns slices for: now, +30min(interpolated), +2h, +6h, +12h
    """
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude":  lat,
            "longitude": lon,
            "hourly": ",".join([
                "cape", "lifted_index", "convective_inhibition",
                "precipitation_probability", "precipitation",
                "cloudcover", "windspeed_10m", "windspeed_80m",
                "surface_pressure", "dewpoint_2m",
                "relativehumidity_2m", "weathercode", "temperature_2m",
                "freezinglevel_height",   # 0°C isotherm — key for hail survival
                "snowfall",               # forecast snowfall in cm
            ]),
            "forecast_days": 2,
            "timezone": "auto",
        }, timeout=10)
        r.raise_for_status()
        data   = r.json()
        hourly = data["hourly"]
        times  = hourly["time"]

        # Find current hour index
        now_str = datetime.now().strftime("%Y-%m-%dT%H:00")
        try:    idx = times.index(now_str)
        except: idx = 0

        def row(i):
            i = min(i, len(times) - 1)
            return {
                k: (hourly[k][i] if hourly[k][i] is not None else 0)
                for k in hourly if k != "time"
            } | {"hour": int(times[i][11:13])}

        def interp(i1, i2):
            r1, r2 = row(i1), row(i2)
            return {k: (r1[k] + r2[k]) / 2 for k in r1}

        return {
            "now":    row(idx),
            "h30min": interp(idx, idx + 1),   # midpoint between hr0 and hr1
            "h2":     row(idx + 2),
            "h6":     row(idx + 6),
            "h12":    row(idx + 12),
            "elevation": data.get("elevation", 0),
        }
    except: return None

# ══════════════════════════════════════════════════════════════════
# RISK SCORERS
# ══════════════════════════════════════════════════════════════════

RISK_LABEL = {2: "HIGH", 1: "MODERATE", 0: "LOW"}
RISK_EMOJI = {"HIGH": "🔴", "MODERATE": "🟡", "LOW": "🟢"}
RISK_COLOR = {"HIGH": "#ef4444", "MODERATE": "#f59e0b", "LOW": "#22c55e"}
RISK_BG    = {"HIGH": "#fee2e2", "MODERATE": "#fef3c7", "LOW": "#dcfce7"}
RISK_TEXT  = {"HIGH": "#991b1b", "MODERATE": "#92400e", "LOW": "#166534"}


def _level(score, h, m):
    if score >= h: return "HIGH"
    if score >= m: return "MODERATE"
    return "LOW"


def score_flash_rain(om: dict, owm: dict | None, lat: float, elev: float,
                     is_now: bool) -> tuple[str, list[str]]:
    zone = climate_zone(lat)
    fh, fm, *_ = CAPE_CFG[zone]
    ef  = elev_factor(elev)
    hw  = hour_weight(om["hour"], lat)

    cape  = om.get("cape", 0) or 0
    li    = om.get("lifted_index", 0) or 0
    cin   = abs(om.get("convective_inhibition", 100) or 100)
    pprob = om.get("precipitation_probability", 0) or 0
    cloud = om.get("cloudcover", 0) or 0
    hum   = om.get("relativehumidity_2m", 0) or 0
    shear = abs((om.get("windspeed_80m", 0) or 0) - (om.get("windspeed_10m", 0) or 0))

    score, flags = 0, []

    # CAPE — dynamically adjusted threshold
    if cape > fh * ef * hw:
        score += 35; flags.append(f"CAPE {cape:.0f} J/kg — high instability")
    elif cape > fm * ef * hw:
        score += 20; flags.append(f"CAPE {cape:.0f} J/kg — moderate instability")

    if li < -4:  score += 25; flags.append(f"Lifted Index {li:.1f} — very unstable")
    elif li < -2: score += 15; flags.append(f"Lifted Index {li:.1f} — unstable")

    if cin < 20: score += 15; flags.append(f"CIN {cin:.0f} J/kg — cap breaking")
    if pprob > 70: score += 12; flags.append(f"Precip probability {pprob}%")
    if cloud > 85: score += 8;  flags.append(f"Cloud cover {cloud}%")
    if hum > 85:   score += 8;  flags.append(f"Humidity {hum}%")
    if shear > 8:  score += 7;  flags.append(f"Wind shear {shear:.1f} m/s")

    if is_now and owm:
        if owm["rain_1h"] >= 7.5:
            score += 20; flags.append(f"Active rain {owm['rain_1h']} mm/hr (IMD heavy)")
        elif owm["rain_1h"] > 0:
            score += 10; flags.append(f"Light rain {owm['rain_1h']} mm/hr")
        if owm["weather_main"] == "Thunderstorm":
            score += 15; flags.append("Thunderstorm active now")

    return _level(score, 65, 35), flags


def score_storm_rainfall(om: dict, owm: dict | None, lat: float, elev: float,
                          is_now: bool) -> tuple[str, list[str]]:
    zone = climate_zone(lat)
    _, _, sh, sm, _ = CAPE_CFG[zone]
    ef = elev_factor(elev)

    cape  = om.get("cape", 0) or 0
    pprob = om.get("precipitation_probability", 0) or 0
    prec  = om.get("precipitation", 0) or 0
    cloud = om.get("cloudcover", 0) or 0
    wcode = om.get("weathercode", 0) or 0

    score, flags = 0, []

    if pprob > 75:   score += 35; flags.append(f"Precipitation probability {pprob}%")
    elif pprob > 50: score += 20; flags.append(f"Precipitation probability {pprob}%")
    elif pprob > 30: score += 10; flags.append(f"Precipitation probability {pprob}%")

    if prec > 10:   score += 30; flags.append(f"Forecast rainfall {prec:.1f} mm")
    elif prec > 5:  score += 20; flags.append(f"Forecast rainfall {prec:.1f} mm")
    elif prec > 2:  score += 10; flags.append(f"Forecast rainfall {prec:.1f} mm")

    if cape > sh * ef: score += 15; flags.append(f"CAPE {cape:.0f} J/kg")
    if cloud > 70:     score += 10; flags.append(f"Cloud cover {cloud}%")
    if wcode >= 200:   score += 15; flags.append("Thunderstorm weather code")

    if is_now and owm and owm["rain_1h"] > 0:
        score += 15; flags.append(f"Active rainfall {owm['rain_1h']} mm/hr")

    return _level(score, 60, 30), flags


def score_cloudburst(om: dict, owm: dict | None, lat: float, elev: float,
                     is_now: bool) -> tuple[str, list[str]]:
    """
    Cloudburst: 100mm+ in 1 hr. Flags POTENTIAL CONDITIONS only.
    Note shown to user: actual cloudburst detection needs Doppler radar.
    """
    zone = climate_zone(lat)
    *_, cbh = CAPE_CFG[zone]
    ef = elev_factor(elev)

    cape  = om.get("cape", 0) or 0
    cin   = abs(om.get("convective_inhibition", 100) or 100)
    hum   = om.get("relativehumidity_2m", 0) or 0
    li    = om.get("lifted_index", 0) or 0
    shear = abs((om.get("windspeed_80m", 0) or 0) - (om.get("windspeed_10m", 0) or 0))

    score, flags = 0, []

    cbth = cbh * ef
    if cape > cbth:        score += 40; flags.append(f"CAPE {cape:.0f} J/kg — extreme")
    elif cape > cbth * 0.7: score += 20; flags.append(f"CAPE {cape:.0f} J/kg — elevated")

    if cin < 10:  score += 25; flags.append("CIN near zero — cap fully broken")
    elif cin < 20: score += 15; flags.append(f"CIN {cin:.0f} J/kg — weakening cap")

    if li < -6:  score += 20; flags.append(f"LI {li:.1f} — extreme instability")
    if hum > 90: score += 15; flags.append(f"Humidity {hum}% — near saturated")
    if shear > 12: score += 10; flags.append(f"Wind shear {shear:.1f} m/s")
    if elev > 800: score += 10; flags.append(f"Elevation {elev:.0f}m — orographic risk")

    if is_now and owm and owm["rain_1h"] > 50:
        score += 30; flags.append(f"⚠️ Extreme rain {owm['rain_1h']} mm/hr")

    return _level(score, 60, 35), flags

def wet_bulb_approx(temp_c: float, humidity_pct: float) -> float:
    """
    Stull (2011) wet bulb approximation — accurate to ±0.3°C.
    Snow falls when wet bulb ≤ 0°C even if air temp is up to ~3°C.
    """
    rh = humidity_pct
    return (temp_c * (0.5 * (rh / 100 + 0.0001) ** 0.333)
            + (-4.8 + 0.045 * temp_c) * (1 - rh / 100))


def score_snow_hail(om: dict, owm: dict | None, lat: float, elev: float,
                    is_now: bool) -> tuple[str, str, list[str]]:
    """
    Returns (snow_level, hail_level, flags)
    Two separate risk assessments in one function since they share variables.

    SNOW logic:
      - Wet bulb ≤ 0°C + precipitation likely → snow possible
      - Surface temp < -2°C → snow very likely
      - Elevation boost: high cities (Shimla, Denver) get lower temp threshold

    HAIL logic:
      - CAPE > threshold (zone-adjusted) → energy for updraft
      - Freezing level < 5000m → ice survives descent to ground
      - Wind shear > 8 m/s → organised storm that suspends hailstones
      - CIN < 30 → cap weakening so storm can fire
    """
    temp    = om.get("temperature_2m", 20) or 20
    hum     = om.get("relativehumidity_2m", 60) or 60
    pprob   = om.get("precipitation_probability", 0) or 0
    cape    = om.get("cape", 0) or 0
    cin     = abs(om.get("convective_inhibition", 100) or 100)
    shear   = abs((om.get("windspeed_80m", 0) or 0) - (om.get("windspeed_10m", 0) or 0))
    snow_cm = om.get("snowfall", 0) or 0
    frz_lvl = om.get("freezinglevel_height", 6000) or 6000

    zone = climate_zone(lat)
    fh, *_ = CAPE_CFG[zone]
    ef     = elev_factor(elev)

    wb = wet_bulb_approx(temp, hum)

    flags = []

    # ── SNOW scoring ──────────────────────────────────────────────
    snow_score = 0

    if wb <= 0:
        snow_score += 40
        flags.append(f"Wet bulb {wb:.1f}°C ≤ 0°C — snow-favourable")
    elif wb <= 1.5:
        snow_score += 20
        flags.append(f"Wet bulb {wb:.1f}°C — marginal (rain/snow mix)")

    if temp < -2:
        snow_score += 25
        flags.append(f"Surface temp {temp}°C — well below freezing")
    elif temp < 2:
        snow_score += 12
        flags.append(f"Surface temp {temp}°C — near freezing")

    if pprob > 50:
        snow_score += 20
        flags.append(f"Precipitation probability {pprob}%")
    elif pprob > 30:
        snow_score += 10

    if snow_cm > 0:
        snow_score += 20
        flags.append(f"Forecast snowfall {snow_cm:.1f} cm")

    if elev > 1500:
        snow_score += 10
        flags.append(f"High elevation {elev:.0f}m — enhances snow chance")

    snow_level = _level(snow_score, 60, 30)

    # ── HAIL scoring ──────────────────────────────────────────────
    hail_score  = 0
    hail_flags  = []

    # CAPE — same dynamic zone+elevation threshold as flash rain
    cape_thresh = fh * ef
    if cape > cape_thresh:
        hail_score += 35
        hail_flags.append(f"CAPE {cape:.0f} J/kg — strong updraft energy")
    elif cape > cape_thresh * 0.6:
        hail_score += 18
        hail_flags.append(f"CAPE {cape:.0f} J/kg — moderate updraft")

    # Freezing level — the single most important hail variable
    # Hail survives descent when freezing level is below ~5000m
    # At high elevation cities (Bengaluru 920m), effective height is frz_lvl - elev
    effective_frz = frz_lvl - elev
    if effective_frz < 3500:
        hail_score += 30
        hail_flags.append(f"Freezing level {frz_lvl:.0f}m — very favourable for large hail")
    elif effective_frz < 4500:
        hail_score += 20
        hail_flags.append(f"Freezing level {frz_lvl:.0f}m — hail-favourable")
    elif effective_frz < 5500:
        hail_score += 10
        hail_flags.append(f"Freezing level {frz_lvl:.0f}m — marginal for hail")

    # Wind shear — organises storm, sustains hailstone growth
    if shear > 12:
        hail_score += 20
        hail_flags.append(f"Wind shear {shear:.1f} m/s — strong (large hail risk)")
    elif shear > 8:
        hail_score += 12
        hail_flags.append(f"Wind shear {shear:.1f} m/s — moderate")

    if cin < 15:
        hail_score += 15
        hail_flags.append(f"CIN {cin:.0f} J/kg — cap fully broken")
    elif cin < 30:
        hail_score += 8
        hail_flags.append(f"CIN {cin:.0f} J/kg — weakening cap")

    if is_now and owm and owm["weather_main"] in ("Thunderstorm",):
        hail_score += 15
        hail_flags.append("Active thunderstorm — hail possible NOW")

    hail_level = _level(hail_score, 60, 30)

    # Combine flags: snow first, then hail separated
    all_flags = []
    if flags:      all_flags += ["❄️ SNOW —"] + flags
    if hail_flags: all_flags += ["🧊 HAIL —"] + hail_flags

    return snow_level, hail_level, all_flags, wb, frz_lvl


# ══════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════

def risk_badge(level: str) -> str:
    return (
        f'<span style="background:{RISK_BG[level]};color:{RISK_TEXT[level]};'
        f'border-radius:20px;padding:3px 14px;font-weight:700;font-size:13px;">'
        f'{RISK_EMOJI[level]} {level}</span>'
    )

def time_card(title: str, level: str, flags: list[str], extra: str = ""):
    color = RISK_COLOR[level]
    bg    = RISK_BG[level]
    tc    = RISK_TEXT[level]
    flags_html = "".join(f'<div style="font-size:12px;margin-top:3px;">⚡ {f}</div>' for f in flags) or \
                 '<div style="font-size:12px;color:#6b7280;margin-top:3px;">✅ No triggers</div>'
    return f"""
    <div style="background:#ffffff;border:1.5px solid {color};border-radius:12px;
                padding:14px 16px;height:100%;box-shadow:0 2px 8px {color}22;">
      <div style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;
                  letter-spacing:.06em;margin-bottom:6px;">{title}</div>
      <div style="margin-bottom:8px;">{risk_badge(level)}</div>
      {flags_html}
      {f'<div style="font-size:11px;color:#6b7280;margin-top:6px;">{extra}</div>' if extra else ''}
    </div>"""

def section_header(icon: str, title: str, subtitle: str, color: str):
    st.markdown(f"""
    <div style="background:linear-gradient(90deg,{color}22,transparent);
                border-left:4px solid {color};border-radius:8px;
                padding:12px 18px;margin:1.2rem 0 0.8rem 0;">
      <div style="font-size:17px;font-weight:700;color:{color}">{icon} {title}</div>
      <div style="font-size:12px;color:#6b7280;margin-top:2px;">{subtitle}</div>
    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# PAGE SETUP
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Flash Rainfall Predictor", page_icon="🌧️", layout="wide")

st.markdown("""
<style>
  .block-container{padding-top:1rem;}
  div[data-testid="stHorizontalBlock"]{gap:12px;}
  .stTabs [data-baseweb="tab"]{font-size:14px;font-weight:600;padding:8px 20px;}
</style>""", unsafe_allow_html=True)

# ── Gradient header ───────────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(135deg,#1e3a5f,#1565c0,#0288d1);
            border-radius:16px;padding:24px 32px;margin-bottom:1.2rem;color:white;">
  <div style="font-size:28px;font-weight:800;letter-spacing:-0.5px;">🌧️ Flash Rainfall Predictor</div>
  <div style="font-size:14px;opacity:0.85;margin-top:4px;">
    Real-time storm rainfall · Flash rain nowcast · Cloudburst potential — Worldwide
  </div>
  <div style="display:flex;gap:20px;margin-top:12px;font-size:12px;opacity:0.75;">
    <span>📡 OpenWeatherMap — current conditions</span>
    <span>🌐 Open-Meteo — CAPE · LI · CIN · 16-day forecast</span>
    <span>🧠 Dynamic thresholds by climate zone + elevation</span>
  </div>
</div>""", unsafe_allow_html=True)

# ── API guard ─────────────────────────────────────────────────────
if not OWM_KEY:
    st.error("**Add your OpenWeatherMap API key.** Create `.env` → `OPENWEATHER_API_KEY=your_key` → restart app.")
    st.stop()

# ══════════════════════════════════════════════════════════════════
# SEARCH BAR
# ══════════════════════════════════════════════════════════════════
with st.container():
    st.markdown("#### 📍 Search Location")
    c1, c2, c3, c4 = st.columns([2.5, 2, 2.5, 1])

    country_list = sorted(COUNTRIES.values())
    with c1:
        country_name = st.selectbox("Country", country_list,
                                    index=country_list.index("India"))
    country_code = next(k for k, v in COUNTRIES.items() if v == country_name)

    with c2:
        state_in = st.text_input("State / Province", placeholder="e.g. Karnataka (optional)")

    with c3:
        city_in = st.text_input("City", placeholder="e.g. Bengaluru",
                                value="Bengaluru" if country_name == "India" else "")

    with c4:
        st.markdown("<br>", unsafe_allow_html=True)
        search = st.button("🔍 Search", use_container_width=True)

if "locations" not in st.session_state:
    st.session_state.locations = []

# ── Search handler ────────────────────────────────────────────────
if search:
    if not city_in.strip():
        st.warning("Please enter a city name.")
    else:
        with st.spinner(f"Locating {city_in}..."):
            geo = geocode(city_in.strip(), state_in.strip(), country_code)
        if not geo:
            st.error(f"Could not find **{city_in}** in {country_name}. Check spelling.")
        else:
            loc   = geo[0]
            state = loc.get("state", "") or ""
            label = f"{loc['name']}{', ' + state if state else ''}, {country_name}"

            if any(abs(l["lat"] - loc["lat"]) < 0.05 for l in st.session_state.locations):
                st.info(f"{label} is already on the map.")
            else:
                with st.spinner("Fetching weather data..."):
                    owm = fetch_owm(loc["lat"], loc["lon"])
                    om  = fetch_openmeteo(loc["lat"], loc["lon"])

                if owm and om:
                    st.session_state.locations.append({
                        "label": label,
                        "lat":   loc["lat"],
                        "lon":   loc["lon"],
                        "owm":   owm,
                        "om":    om,
                    })
                    st.success(f"Added **{label}**")
                else:
                    st.error("Data fetch failed. Check API key or try again.")

col_cl, _ = st.columns([1, 5])
with col_cl:
    if st.session_state.locations:
        if st.button("🗑️ Clear all"):
            st.session_state.locations = []
            st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════
# MAIN DISPLAY
# ══════════════════════════════════════════════════════════════════
locs = st.session_state.locations

if not locs:
    st.markdown("""
    <div style="text-align:center;padding:3rem;color:#6b7280;">
      <div style="font-size:48px;">🌤️</div>
      <div style="font-size:16px;margin-top:8px;">Search for a city above to begin monitoring</div>
      <div style="font-size:13px;margin-top:4px;">Supports any city worldwide</div>
    </div>""", unsafe_allow_html=True)
else:
    # ── Map ───────────────────────────────────────────────────────
    map_col, info_col = st.columns([3, 2])

    with map_col:
        st.markdown("#### 🗺️ Live Risk Map")
        avg_lat = sum(l["lat"] for l in locs) / len(locs)
        avg_lon = sum(l["lon"] for l in locs) / len(locs)
        m = folium.Map(location=[avg_lat, avg_lon],
                       zoom_start=5 if len(locs) == 1 else 3,
                       tiles="CartoDB positron")

        cm = {"HIGH": "red", "MODERATE": "orange", "LOW": "green"}
        for loc in locs:
            # Use flash rain current as the map marker level
            lvl, _ = score_flash_rain(loc["om"]["now"], loc["owm"],
                                       loc["lat"], loc["om"]["elevation"], True)
            owm = loc["owm"]
            om  = loc["om"]["now"]
            folium.CircleMarker(
                location=[loc["lat"], loc["lon"]],
                radius=22,
                color=cm[lvl], fill=True, fill_opacity=0.65,
                popup=folium.Popup(
                    f"<b>{loc['label']}</b><br>"
                    f"Flash Rain Risk: <b>{lvl}</b><br>"
                    f"🌡 {owm['temp_c']}°C 💧 {owm['humidity_pct']}%<br>"
                    f"☁️ {owm['cloud_pct']}% 💨 {owm['wind_ms']} m/s<br>"
                    f"🌧 {owm['rain_1h']} mm/hr · {owm['weather_desc']}<br>"
                    f"CAPE: {om.get('cape',0):.0f} J/kg | LI: {om.get('lifted_index',0):.1f}",
                    max_width=220),
                tooltip=f"{loc['label']} — {lvl}",
            ).add_to(m)

        st_folium(m, width=None, height=420)

    with info_col:
        st.markdown("#### 📊 Current Conditions")
        for loc in locs:
            owm = loc["owm"]
            om  = loc["om"]
            with st.container(border=True):
                st.markdown(f"**{loc['label']}**")
                st.caption(f"{owm['weather_desc']}")
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Temp", f"{owm['temp_c']}°C")
                mc2.metric("Humidity", f"{owm['humidity_pct']}%")
                mc3.metric("Rain", f"{owm['rain_1h']} mm/hr")
                nc1, nc2, nc3 = st.columns(3)
                nc1.metric("CAPE", f"{om['now'].get('cape',0):.0f} J/kg")
                nc2.metric("Lifted Idx", f"{om['now'].get('lifted_index',0):.1f}")
                nc3.metric("Cloud", f"{owm['cloud_pct']}%")
                zone = climate_zone(loc["lat"])
                st.caption(
                    f"🌍 Climate zone: **{zone.title()}** · "
                    f"Elevation: **{om['elevation']:.0f}m** · "
                    f"📍 {loc['lat']:.2f}°, {loc['lon']:.2f}°"
                )

    st.divider()

    # ── Event type tabs ───────────────────────────────────────────
    for loc in locs:
        st.markdown(f"### 📍 {loc['label']}")
        owm = loc["owm"]
        om  = loc["om"]
        elev = om["elevation"]
        lat  = loc["lat"]

        tab1, tab2, tab3, tab4 = st.tabs([
            "🌧 Storm Rainfall",
            "⛈️ Flash Rain",
            "💥 Cloudburst",
            "❄️ Snow & 🧊 Hail",
        ])

        # ── STORM RAINFALL ────────────────────────────────────────
        with tab1:
            section_header("🌧", "Storm Rainfall",
                           "Sustained heavy rain · IMD: >64.5mm in 24hrs · Predictable 6–12 hrs ahead",
                           "#3b82f6")

            lvl_now, fl_now   = score_storm_rainfall(om["now"],  owm, lat, elev, True)
            lvl_6h,  fl_6h    = score_storm_rainfall(om["h6"],   None, lat, elev, False)
            lvl_12h, fl_12h   = score_storm_rainfall(om["h12"],  None, lat, elev, False)

            pprob_now = om["now"].get("precipitation_probability", 0) or 0
            pprob_6h  = om["h6"].get("precipitation_probability",  0) or 0
            pprob_12h = om["h12"].get("precipitation_probability", 0) or 0

            s1, s2, s3 = st.columns(3)
            with s1: st.markdown(
                time_card("🕐 Current", lvl_now, fl_now,
                          f"Precip prob: {pprob_now}% · {owm['weather_desc']}"),
                unsafe_allow_html=True)
            with s2: st.markdown(
                time_card("🕕 +6 Hours", lvl_6h,  fl_6h,
                          f"Precip prob: {pprob_6h}%"),
                unsafe_allow_html=True)
            with s3: st.markdown(
                time_card("🕛 +12 Hours", lvl_12h, fl_12h,
                          f"Precip prob: {pprob_12h}%"),
                unsafe_allow_html=True)

            st.caption("Source: Open-Meteo precipitation probability + CAPE · OWM current conditions")

        # ── FLASH RAIN ────────────────────────────────────────────
        with tab2:
            section_header("⛈️", "Flash Rain",
                           "Intense localised rain · IMD: >50mm in 1–2 hrs · Nowcast 2–6 hrs using CAPE + LI",
                           "#f97316")

            lvl_now, fl_now = score_flash_rain(om["now"], owm, lat, elev, True)
            lvl_2h,  fl_2h  = score_flash_rain(om["h2"],  None, lat, elev, False)
            lvl_6h,  fl_6h  = score_flash_rain(om["h6"],  None, lat, elev, False)

            cape_now = om["now"].get("cape", 0) or 0
            cape_2h  = om["h2"].get("cape",  0) or 0
            cape_6h  = om["h6"].get("cape",  0) or 0
            li_now   = om["now"].get("lifted_index", 0) or 0

            f1, f2, f3 = st.columns(3)
            with f1: st.markdown(
                time_card("🕐 Current", lvl_now, fl_now,
                          f"CAPE: {cape_now:.0f} J/kg · LI: {li_now:.1f}"),
                unsafe_allow_html=True)
            with f2: st.markdown(
                time_card("🕑 +2 Hours", lvl_2h, fl_2h,
                          f"CAPE: {cape_2h:.0f} J/kg"),
                unsafe_allow_html=True)
            with f3: st.markdown(
                time_card("🕕 +6 Hours", lvl_6h, fl_6h,
                          f"CAPE: {cape_6h:.0f} J/kg"),
                unsafe_allow_html=True)

            zone = climate_zone(lat)
            fh, fm, *_ = CAPE_CFG[zone]
            ef = elev_factor(elev)
            st.info(
                f"🧠 **Dynamic thresholds for this location** — "
                f"Climate zone: {zone.title()} · Elevation: {elev:.0f}m · "
                f"CAPE HIGH threshold: {fh * ef:.0f} J/kg · "
                f"CAPE MODERATE: {fm * ef:.0f} J/kg",
                icon="ℹ️"
            )

        # ── CLOUDBURST ────────────────────────────────────────────
        with tab3:
            section_header("💥", "Cloudburst",
                           "Extreme event · IMD: 100mm+ in 1 hr · Conditions flagged — NOT a precise prediction",
                           "#dc2626")

            lvl_now, fl_now   = score_cloudburst(om["now"],    owm, lat, elev, True)
            lvl_30m, fl_30m   = score_cloudburst(om["h30min"], None, lat, elev, False)

            cape_now  = om["now"].get("cape", 0) or 0
            cin_now   = abs(om["now"].get("convective_inhibition", 100) or 100)

            b1, b2 = st.columns(2)
            with b1: st.markdown(
                time_card("🕐 Current Conditions", lvl_now, fl_now,
                          f"CAPE: {cape_now:.0f} J/kg · CIN: {cin_now:.0f} J/kg"),
                unsafe_allow_html=True)
            with b2: st.markdown(
                time_card("⏱️ ~30 Min Outlook", lvl_30m, fl_30m,
                          "Interpolated from hourly data — use as guidance only"),
                unsafe_allow_html=True)

            st.warning(
                "⚠️ **Cloudburst Limitation:** Actual cloudburst prediction requires "
                "Doppler radar data (unavailable in this free-tier setup). "
                "This panel flags *atmospheric conditions favourable for cloudbursts*. "
                "HIGH here means conditions are dangerous — not that one will definitely occur.",
                icon="🌩️"
            )

        # ── SNOW & HAIL ───────────────────────────────────────────
        with tab4:
            section_header("❄️🧊", "Snow & Hail",
                           "Snow: wet bulb ≤ 0°C + precip · Hail: CAPE + freezing level + wind shear",
                           "#6366f1")

            # Current
            s_now, h_now, fl_now, wb_now, frz_now = score_snow_hail(
                om["now"], owm, lat, elev, True)
            # +3h
            s_3h, h_3h, fl_3h, wb_3h, frz_3h = score_snow_hail(
                om["h2"], None, lat, elev, False)
            # +6h
            s_6h, h_6h, fl_6h, wb_6h, frz_6h = score_snow_hail(
                om["h6"], None, lat, elev, False)

            # ── Snow row ──────────────────────────────────────────
            st.markdown("""
            <div style="font-size:13px;font-weight:700;color:#6366f1;
                        text-transform:uppercase;letter-spacing:.06em;
                        margin:10px 0 6px;">❄️ Snow Risk</div>
            """, unsafe_allow_html=True)

            sn1, sn2, sn3 = st.columns(3)
            snow_flags_now = [f for f in fl_now if "SNOW" in f or "Wet bulb" in f
                              or "temp" in f or "Precipitation" in f
                              or "snowfall" in f.lower() or "elevation" in f.lower()]
            snow_flags_3h  = [f for f in fl_3h  if "SNOW" in f or "Wet bulb" in f
                              or "temp" in f or "Precipitation" in f
                              or "snowfall" in f.lower() or "elevation" in f.lower()]
            snow_flags_6h  = [f for f in fl_6h  if "SNOW" in f or "Wet bulb" in f
                              or "temp" in f or "Precipitation" in f
                              or "snowfall" in f.lower() or "elevation" in f.lower()]

            with sn1: st.markdown(
                time_card("🕐 Current", s_now, snow_flags_now,
                          f"Wet bulb: {wb_now:.1f}°C · Temp: {om['now'].get('temperature_2m',0):.1f}°C"),
                unsafe_allow_html=True)
            with sn2: st.markdown(
                time_card("🕑 +3 Hours", s_3h, snow_flags_3h,
                          f"Wet bulb: {wb_3h:.1f}°C · Temp: {om['h2'].get('temperature_2m',0):.1f}°C"),
                unsafe_allow_html=True)
            with sn3: st.markdown(
                time_card("🕕 +6 Hours", s_6h, snow_flags_6h,
                          f"Wet bulb: {wb_6h:.1f}°C · Temp: {om['h6'].get('temperature_2m',0):.1f}°C"),
                unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Hail row ──────────────────────────────────────────
            st.markdown("""
            <div style="font-size:13px;font-weight:700;color:#0891b2;
                        text-transform:uppercase;letter-spacing:.06em;
                        margin:6px 0 6px;">🧊 Hail Risk</div>
            """, unsafe_allow_html=True)

            hl1, hl2, hl3 = st.columns(3)
            hail_flags_now = [f for f in fl_now if "HAIL" in f or "CAPE" in f
                              or "Freezing" in f or "shear" in f.lower()
                              or "CIN" in f or "Thunderstorm" in f]
            hail_flags_3h  = [f for f in fl_3h  if "HAIL" in f or "CAPE" in f
                              or "Freezing" in f or "shear" in f.lower()
                              or "CIN" in f or "Thunderstorm" in f]
            hail_flags_6h  = [f for f in fl_6h  if "HAIL" in f or "CAPE" in f
                              or "Freezing" in f or "shear" in f.lower()
                              or "CIN" in f or "Thunderstorm" in f]

            with hl1: st.markdown(
                time_card("🕐 Current", h_now, hail_flags_now,
                          f"Freezing level: {frz_now:.0f}m · Elev: {elev:.0f}m"),
                unsafe_allow_html=True)
            with hl2: st.markdown(
                time_card("🕑 +3 Hours", h_3h, hail_flags_3h,
                          f"Freezing level: {frz_3h:.0f}m"),
                unsafe_allow_html=True)
            with hl3: st.markdown(
                time_card("🕕 +6 Hours", h_6h, hail_flags_6h,
                          f"Freezing level: {frz_6h:.0f}m"),
                unsafe_allow_html=True)

            # ── Science note ──────────────────────────────────────
            temp_now = om["now"].get("temperature_2m", 20) or 20
            effective_frz = frz_now - elev
            st.info(
                f"🧠 **How thresholds were computed for this location** — "
                f"Climate zone: {climate_zone(lat).title()} · "
                f"Elevation: {elev:.0f}m · "
                f"Effective freezing level above ground: {effective_frz:.0f}m · "
                f"Surface temp now: {temp_now:.1f}°C · "
                f"Wet bulb now: {wb_now:.1f}°C",
                icon="ℹ️"
            )

            if abs(lat) < 20:
                st.warning(
                    "⚠️ **Tropical location detected.** Snow is climatologically "
                    "very rare here except at high elevations (>3000m). "
                    "LOW snow risk is expected and normal for this region.",
                    icon="🌴"
                )

        st.divider()
    st.caption(
        f"Updated: {datetime.now().strftime('%d %b %Y, %H:%M')} · "
        "OpenWeatherMap (current) + Open-Meteo (forecast, CAPE, LI, CIN) · "
        "Thresholds: IMD definitions + climate zone + elevation adjustment · "
        "ERA6 integration planned 2027"
    )
