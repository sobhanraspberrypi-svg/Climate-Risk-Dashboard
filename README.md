# 🌧️ Flash Rainfall Predictor

> Real-time weather risk monitor for **Storm Rainfall, Flash Rain, Cloudburst, Snow and Hail** — any city, worldwide.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![Streamlit](https://img.shields.io/badge/streamlit-1.32-red) ![Open--Meteo](https://img.shields.io/badge/Open--Meteo-free-green) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## What This Project Does

Most weather apps tell you it is raining **after it has started**. This project flags dangerous atmospheric conditions **before** they produce rainfall — giving residents, commuters, and city systems a 2–6 hour head start on flash rain events, and a 6–12 hour window on storm rainfall.

It monitors **four distinct weather hazards** for any searched city worldwide:

| Hazard | Definition | Lead Time |
|---|---|---|
| 🌧 Storm Rainfall | Sustained heavy rain — IMD threshold >64.5mm in 24 hrs | 6–12 hours |
| ⛈️ Flash Rain | Intense localised burst — IMD threshold >50mm in 1–2 hrs | 2–6 hours |
| 💥 Cloudburst | Extreme event — IMD threshold 100mm+ in 1 hr | Conditions only* |
| ❄️🧊 Snow & Hail | Frozen precipitation risk using wet bulb + freezing level | 3–6 hours |

*Cloudburst precise prediction requires Doppler radar — this project flags favourable conditions.

---

## How It Works

### Data Sources

Two free APIs power the entire system — no paid tier needed:

**OpenWeatherMap** — current observed conditions (temperature, humidity, cloud cover, active rainfall, wind speed, pressure). This is what is happening right now at the surface.

**Open-Meteo** — hourly atmospheric forecast data up to 16 days ahead, including variables that go deep into the atmosphere, not just the surface. No API key required.

### What Open-Meteo Provides That Makes Prediction Possible

| Variable | What It Means |
|---|---|
| **CAPE** (J/kg) | Convective Available Potential Energy — how much energy the atmosphere has stored for storm updrafts. The single most important flash rain predictor. |
| **Lifted Index** | How unstable the atmosphere is. Negative = a rising air parcel keeps rising, forming deep storm clouds. Below -4 is dangerous. |
| **CIN** (J/kg) | Convective Inhibition — a cap that suppresses storms. When it falls below 20 J/kg the cap breaks and stored CAPE fires rapidly. |
| **Freezing Level Height** | The altitude where temperature hits 0°C. Critical for hail — if below 5000m, hailstones survive the fall to ground. |
| **Wind Shear** | Speed difference between 10m and 80m winds. High shear organises storms and sustains hailstone growth in updrafts. |
| **Precipitation Probability** | Open-Meteo's own model forecast — used directly for storm rainfall scoring. |
| **Snowfall (cm)** | Forecast snowfall used as a confirmatory signal for snow risk. |

### The Risk Scoring Engine

Rather than machine learning (which requires years of labelled historical data), this project uses a **physics-based rule scoring system** derived from IMD (India Meteorological Department) thresholds and established atmospheric science.

Each hazard has its own scorer. Every scorer produces a score 0–100 and maps it to LOW / MODERATE / HIGH.

**What makes scoring dynamic worldwide — no city hardcoding:**

**1. Climate Zone from Latitude**
The same CAPE value means different things in different parts of the world. In equatorial regions (Jakarta, Lagos) the atmosphere is always moist so storms fire at lower CAPE. In temperate zones (London, Toronto) you need much higher CAPE before convection organises.

```
Equatorial  (0–15°)  : CAPE HIGH threshold = 800 J/kg
Tropical    (15–25°) : CAPE HIGH threshold = 1000 J/kg
Subtropical (25–40°) : CAPE HIGH threshold = 1500 J/kg
Temperate   (40–60°) : CAPE HIGH threshold = 2000 J/kg
Polar       (60°+)   : CAPE HIGH threshold = 3000 J/kg
```

**2. Elevation from Open-Meteo**
Fetched automatically for every coordinate. Higher cities start closer to the freezing level so storms fire at lower CAPE. Bengaluru at 920m gets thresholds multiplied by 0.85. Shimla at 2300m gets 0.65.

**3. Time-of-Day Weighting**
Convective storms are afternoon phenomena — driven by surface heating. CAPE at 3 PM is far more dangerous than the same CAPE at 3 AM. The scorer applies a time multiplier that peaks at 15:00 local time for tropical cities, 14:00 for subtropical, 13:00 for temperate.

**4. Effective Freezing Level for Hail**
For hail, what matters is not the absolute freezing level but how far above the ground it sits. A freezing level of 4500m means very different things for Mumbai (11m elevation) versus Bengaluru (920m elevation). The code computes `effective freezing level = freezing level - city elevation` automatically.

**5. Wet Bulb Temperature for Snow**
Snow can fall even when the air temperature is +2°C if the wet bulb temperature is at or below 0°C — evaporative cooling makes falling precipitation turn to snow mid-air. The Stull (2011) wet bulb formula is computed from temperature and humidity with no extra API call.

---

## Quickstart

```bash
git clone https://github.com/YOUR_USERNAME/flash-rainfall-predictor
cd flash-rainfall-predictor
pip install -r requirements.txt

cp .env.example .env
# Add your free OpenWeatherMap key to .env

streamlit run app.py
```

Get a free OpenWeatherMap API key at [openweathermap.org/api](https://openweathermap.org/api) — activates in about 10 minutes. Open-Meteo needs no key.

### Usage

1. Select a country from the dropdown
2. Type a state/province (optional but improves accuracy for common city names)
3. Type a city name and click Search
4. Add multiple cities — they all appear on the map simultaneously
5. Click each tab to see risk across all four hazard types and time horizons

---

## Project Structure

```
flash-rainfall-predictor/
├── app.py            # Entire application — single file
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Limitations — Being Honest

**Cloudburst precise timing** requires Doppler radar feeds. Open-Meteo is a 14km grid model — it cannot resolve the 5–10km scale of a cloudburst. This project flags dangerous atmospheric setups, not confirmed events.

**30-minute outlook** is an interpolation between two hourly values — not a true sub-hourly model. Treat it as directional.

**Snow in tropical cities** will almost always show LOW. This is correct — it is climatologically appropriate. A warning appears automatically for cities below 20° latitude.

**Hail size** cannot be estimated without radar. The project flags hail risk (will it hail?) not hail intensity (how large?).

---

## Roadmap

- [ ] ERA6 reanalysis integration when data releases (ECMWF, expected 2027) — 14km resolution vs ERA5's 31km
- [ ] IMD Nowcast API for official Indian short-range alerts
- [ ] SMS alerts via Fast2SMS when risk turns HIGH
- [ ] Historical event overlay — past flash rain events on the map
- [ ] Doppler radar feed integration for cloudburst detection

---

## Data Sources & Credits

- [OpenWeatherMap](https://openweathermap.org/) — real-time surface observations
- [Open-Meteo](https://open-meteo.com/) — free atmospheric forecast (CAPE, LI, CIN, freezing level, snowfall)
- IMD (India Meteorological Department) — rainfall threshold definitions
- Stull, R. (2011) — wet bulb temperature approximation formula

---

## License

MIT
