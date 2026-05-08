# ⛈️ Climate - Risk - Dashboard

> Near real-time flash rain risk monitor for Indian metro cities.  
> Built with OpenWeatherMap + rule-based IMD thresholds. No ML needed.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![Streamlit](https://img.shields.io/badge/streamlit-1.32-red) ![License](https://img.shields.io/badge/license-MIT-green)

---

## What it does

Pulls live weather conditions for **Bengaluru, Mumbai, Hyderabad, Chennai, Pune, Delhi** every 15 minutes and flags flash rain risk based on IMD (India Meteorological Department) precursor thresholds:

| Condition | Threshold | Why it matters |
|---|---|---|
| Humidity | ≥ 85% | Saturated air — convective trigger |
| Cloud cover | ≥ 85% | Deep convective cloud buildup |
| Rainfall | ≥ 7.5 mm/hr | IMD definition of heavy rain |
| Thunderstorm active | — | Direct storm indicator |
| Low pressure | ≤ 1005 hPa | Atmospheric instability |
| Wind speed | ≥ 10 m/s | Wind shear precursor |

Risk levels: **HIGH** / **MODERATE** / **LOW** shown on a live Folium map.

## Quickstart

```bash
git clone https://github.com/YOUR_USERNAME/flashguard-lite
cd flashguard-lite
pip install -r requirements.txt

cp .env.example .env
# Add your free OpenWeatherMap key to .env

streamlit run app.py
```

Get a free API key at [openweathermap.org/api](https://openweathermap.org/api) — activates in ~10 minutes.

## Screenshots

*(Add a screenshot after first run)*

## Roadmap
- [ ] IMD Nowcast API integration (official short-range alerts)
- [ ] Push notifications via Fast2SMS when risk turns HIGH
- [ ] Historical event timeline (past flash rain events by city)
- [ ] CAPE / Lifted Index from Open-Meteo for deeper nowcasting

## Data sources
- [OpenWeatherMap](https://openweathermap.org/) — real-time conditions
- [IMD](https://mausam.imd.gov.in/) — rain threshold definitions

## License
MIT
