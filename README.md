# 🌍 OpenAQ Integration for Home Assistant

<img src="https://user-images.githubusercontent.com/8487728/230648638-35060664-46ef-4d75-9d37-f10dd683b737.png" alt="OpenAQ Logo" width="160"/>

This is a **custom Home Assistant integration** that connects to the [OpenAQ API](https://openaq.org) to provide **real-time air quality data** from thousands of monitoring stations worldwide.

---

## ✨ Features

- 🌫️ Fetches live air quality data (PM1, PM2.5, PM10, CO, NO₂, SO₂, O₃, CO₂, etc.)
- 🧭 Calculates **US AQI** (Air Quality Index) automatically
- 📊 Exposes AQI value, level, and main pollutant as sensors
- 🕒 Updates automatically every 5 minutes
- ⚙️ Multi-station support (up to 3 stations)
- 🧹 Cleanly handles station removal from UI
- 🪶 Lightweight and fully async (no YAML required)
- 🌍 Available in English and Romanian

---

## 🧩 Installation

### Option 1 — One-click installation from HACS (recommended)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zenguru84&repository=ha-openaq&category=integration)

### Option 2 — manual installation
1. Copy the folder `custom_components/openaq` into your Home Assistant config directory:  
   ```
   /config/custom_components/openaq/
   ```
2. Restart Home Assistant

---

## ⚙️ Configuration

1. Go to **Settings → Devices & Services → Add Integration → OpenAQ**
2. Enter your **OpenAQ API Key** (get one free from [OpenAQ](https://explore.openaq.org/))
3. Enter the **Station ID** (for example: `2163078`)
4. Done — your sensors will appear automatically.

To add more stations later:
> Go to the **gear icon (Options)** in the integration → Add another Station ID.

---

## 📈 Exposed Entities

Each station will appear as a **device** under the OpenAQ integration and expose multiple sensor entities, including:

| Sensor | Description | Unit |
|--------|--------------|------|
| PM1 | Particulate Matter ≤1 μm | µg/m³ |
| PM2.5 | Particulate Matter ≤2.5 μm | µg/m³ |
| PM10 | Particulate Matter ≤10 μm | µg/m³ |
| CO₂ | Carbon Dioxide | ppm |
| CO | Carbon Monoxide | ppm |
| NO₂ | Nitrogen Dioxide | µg/m³ |
| O₃ | Ozone | µg/m³ |
| SO₂ | Sulfur Dioxide | µg/m³ |
| AQI | U.S. Air Quality Index | 0–500 |
| AQI Level | Text description (Good / Moderate / Unhealthy, etc.) | — |
| AQI Main Pollutant | Parameter that defines AQI | — |

---

## 🧮 Update Frequency

- **Latest measurements:** every 5 minutes  
- **Station metadata:** every 12 hours  

---

## 🧰 Troubleshooting

If Home Assistant fails to start after deleting a station:
- Make sure your internet connection allows outbound HTTPS to `api.openaq.org`.

If no data appears:
- Check your API key validity.
- Verify that the Station ID exists in OpenAQ Explorer.

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!  
Feel free to open an [issue](https://github.com/zenguru84/ha-openaq/issues) or submit a Pull Request.

---

## 📜 License

This project is distributed under the [MIT License](LICENSE).

---

## 💙 Acknowledgements

- [OpenAQ](https://openaq.org) for providing open, public air quality data  
- [Home Assistant](https://www.home-assistant.io) for the integration framework

---

### 🏷️ Example Screenshots

*(screenshots incoming)*

---

### 🍺 If you find my work helpful, consider supporting it:

[![Buy Me a Beer](https://img.shields.io/badge/🍺-Buy%20Me%20a%20Beer-ffca28?style=for-the-badge)](https://buymeacoffee.com/zenguru84)

---



> © 2025 [zenguru84](https://github.com/zenguru84) — OpenAQ Home Assistant Integration
