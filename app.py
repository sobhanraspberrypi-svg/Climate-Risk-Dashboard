"""
FlashGuard Lite — Real-time Flash Rain Monitor for Indian Metro Cities
Run: streamlit run app.py
"""

import os
import requests
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────
CITIES = {
    "Bengaluru": {"lat": 12.9716, "lon": 77.5946},
    "Mumbai":    {"lat": 19.0760, "lon": 72.8777},
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867},
    "Chennai":   {"lat": 13.0827, "lon": 80.2707},
    "Pune":      {"lat": 18.5204, "lon": 73.8567},
    "Delhi":     {"lat": 28.6139, "lon": 77.2090},
}

API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# ── Data fetching ─────────────────────────────────────────────────
@st.cache_data(ttl=900)   # cache 15 min
def fetch_weather(city: str, lat: float, lon: float) -> dict | None:
    if not API_KEY:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    try:
        r = requests.get(url, params={
            "lat": lat, "lon": lon,
            "appid": API_KEY, "units": "metric"
        }, timeout=8)
        r.raise_for_status()
        d = r.json()
        return {
            "city": city,
            "lat": lat,
            "lon": lon,
            "temp_c":       round(d["main"]["temp"], 1),
            "humidity_pct": d["main"]["humidity"],
            "pressure_hpa": d["main"]["pressure"],
            "cloud_pct":    d["clouds"]["all"],
            "wind_speed_ms": round(d["wind"]["speed"], 1),
            "rain_1h_mm":   d.get("rain", {}).get("1h", 0),
            "weather_main": d["weather"][0]["main"],
            "weather_desc": d["weather"][0]["description"].title(),
            "fetched_at":   datetime.now().strftime("%H:%M IST"),
        }
    except Exception:
        return None


# ── Rule-based risk scorer ────────────────────────────────────────
def compute_risk(w: dict) -> tuple[str, str, list[str]]:
    """
    Returns (risk_level, hex_color, list_of_triggered_rules)
    Rules based on IMD flash rain precursors — no ML needed.
    """
    flags = []
    score = 0

    if w["humidity_pct"] >= 85:
        score += 30
        flags.append(f"Humidity {w['humidity_pct']}% (≥85)")

    if w["cloud_pct"] >= 85:
        score += 25
        flags.append(f"Cloud cover {w['cloud_pct']}% (≥85)")

    if w["rain_1h_mm"] >= 7.5:     # IMD: heavy rain = 7.5mm/hr
        score += 30
        flags.append(f"Active rain {w['rain_1h_mm']} mm/hr")
    elif w["rain_1h_mm"] > 0:
        score += 15
        flags.append(f"Light rain {w['rain_1h_mm']} mm/hr")

    if w["weather_main"] in ("Thunderstorm",):
        score += 25
        flags.append("Thunderstorm active")

    if w["wind_speed_ms"] >= 10:
        score += 10
        flags.append(f"Strong wind {w['wind_speed_ms']} m/s")

    if w["pressure_hpa"] <= 1005:
        score += 10
        flags.append(f"Low pressure {w['pressure_hpa']} hPa")

    if score >= 65:
        return "HIGH", "#ef4444", flags
    elif score >= 35:
        return "MODERATE", "#f59e0b", flags
    else:
        return "LOW", "#22c55e", flags


# ── Page setup ────────────────────────────────────────────────────
st.set_page_config(page_title="FlashGuard Lite", page_icon="⛈️", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .risk-high     { background:#fee2e2; color:#991b1b; border-radius:8px; padding:4px 12px; font-weight:600; }
    .risk-moderate { background:#fef3c7; color:#92400e; border-radius:8px; padding:4px 12px; font-weight:600; }
    .risk-low      { background:#dcfce7; color:#166534; border-radius:8px; padding:4px 12px; font-weight:600; }
</style>
""", unsafe_allow_html=True)

st.title("⛈️ FlashGuard Lite")
st.caption("Near real-time flash rain risk monitor — Indian metro cities")

# ── API key guard ─────────────────────────────────────────────────
if not API_KEY:
    st.warning(
        "**Set your OpenWeatherMap API key to see live data.**\n\n"
        "1. Get a free key at [openweathermap.org/api](https://openweathermap.org/api)\n"
        "2. Create a `.env` file in this folder: `OPENWEATHER_API_KEY=your_key`\n"
        "3. Restart the app"
    )
    st.info("Demo mode: showing placeholder layout below.", icon="ℹ️")

# ── Fetch all cities ──────────────────────────────────────────────
with st.spinner("Fetching live conditions..."):
    results = []
    for city, coords in CITIES.items():
        w = fetch_weather(city, coords["lat"], coords["lon"])
        if w:
            level, color, flags = compute_risk(w)
            w["risk_level"] = level
            w["risk_color"] = color
            w["flags"] = flags
            results.append(w)

st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y, %H:%M IST')} · Refreshes every 15 min")
st.divider()

# ── Map ───────────────────────────────────────────────────────────
col_map, col_table = st.columns([3, 2])

with col_map:
    st.subheader("Live Risk Map")
    m = folium.Map(location=[17.5, 78.5], zoom_start=5, tiles="CartoDB positron")

    if results:
        for w in results:
            color_map = {"HIGH": "red", "MODERATE": "orange", "LOW": "green"}
            folium.CircleMarker(
                location=[w["lat"], w["lon"]],
                radius=22,
                color=color_map[w["risk_level"]],
                fill=True,
                fill_opacity=0.6,
                popup=folium.Popup(
                    f"<b>{w['city']}</b><br>"
                    f"Risk: <b>{w['risk_level']}</b><br>"
                    f"Rain: {w['rain_1h_mm']} mm/hr<br>"
                    f"Humidity: {w['humidity_pct']}%<br>"
                    f"Cloud: {w['cloud_pct']}%<br>"
                    f"{w['weather_desc']}",
                    max_width=180,
                ),
                tooltip=f"{w['city']} — {w['risk_level']}",
            ).add_to(m)
    else:
        # Demo markers
        for city, coords in CITIES.items():
            folium.CircleMarker(
                location=[coords["lat"], coords["lon"]],
                radius=18,
                color="gray",
                fill=True,
                fill_opacity=0.3,
                tooltip=f"{city} — No data (add API key)",
            ).add_to(m)

    st_folium(m, width=None, height=400)

# ── City cards ────────────────────────────────────────────────────
with col_table:
    st.subheader("City Conditions")
    if results:
        for w in results:
            risk_class = f"risk-{w['risk_level'].lower()}"
            with st.container(border=True):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**{w['city']}**  ·  {w['weather_desc']}")
                    st.caption(f"🌡 {w['temp_c']}°C  💧 {w['humidity_pct']}%  ☁️ {w['cloud_pct']}%  💨 {w['wind_speed_ms']} m/s")
                    if w["flags"]:
                        for flag in w["flags"]:
                            st.caption(f"⚡ {flag}")
                with c2:
                    st.markdown(f'<span class="{risk_class}">{w["risk_level"]}</span>', unsafe_allow_html=True)
                    if w["rain_1h_mm"] > 0:
                        st.metric("Rain", f"{w['rain_1h_mm']} mm/hr")
    else:
        st.info("Live data will appear here once you add your API key.")

# ── Summary banner for active alerts ─────────────────────────────
st.divider()
high_risk = [w for w in results if w["risk_level"] == "HIGH"]
moderate_risk = [w for w in results if w["risk_level"] == "MODERATE"]

if high_risk:
    cities_str = ", ".join(w["city"] for w in high_risk)
    st.error(f"⚠️ **HIGH flash rain risk** currently in: {cities_str}")
elif moderate_risk:
    cities_str = ", ".join(w["city"] for w in moderate_risk)
    st.warning(f"🌧 **Moderate risk** currently in: {cities_str}. Monitor conditions.")
elif results:
    st.success("✅ Conditions are calm across all monitored cities right now.")

# ── Footer ────────────────────────────────────────────────────────
st.caption("Data: OpenWeatherMap · Risk rules based on IMD flash rain thresholds · Refreshes every 15 min")
