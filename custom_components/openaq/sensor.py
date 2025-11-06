from __future__ import annotations
import logging
from datetime import timedelta
import async_timeout
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
)
from .__init__ import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL_META = timedelta(hours=12)
SCAN_INTERVAL_LATEST = timedelta(minutes=5)  


# ----------------- helpers HTTP -----------------
async def _fetch_json(session, url: str, headers: dict):
    try:
        async with async_timeout.timeout(15):
            resp = await session.get(url, headers=headers)
            resp.raise_for_status()
            return await resp.json()
    except Exception as err:
        raise UpdateFailed(f"Error fetching {url}: {err}") from err


def _meta_root(meta_data: dict) -> dict:
    if not meta_data:
        return {}
    results = meta_data.get("results", [])
    return results[0] if results else {}


def _find_sensor_id(meta_root: dict, pname: str):
    for s in meta_root.get("sensors", []):
        param = s.get("parameter") or {}
        if param.get("name") == pname:
            return s.get("id")
    return None


def _latest_value(latest_data: dict, sid):
    if not latest_data or sid is None:
        return None
    for row in latest_data.get("results", []):
        if row.get("sensorsId") == sid:
            return row.get("value")
    return None


def _latest_datetime_local(latest_data: dict):
    results = (latest_data or {}).get("results", [])
    if not results:
        return None
    dt = results[0].get("datetime") or {}
    return dt.get("local")


# ----------------- AQI helpers -----------------
def _aqi_us_from_pm25(pm25):
    if pm25 is None:
        return None
    x = float(pm25)
    if x <= 12.0:   return (50-0)/(12.0-0.0)*(x-0.0)+0
    if x <= 35.4:   return (100-51)/(35.4-12.1)*(x-12.1)+51
    if x <= 55.4:   return (150-101)/(55.4-35.5)*(x-35.5)+101
    if x <= 150.4:  return (200-151)/(150.4-55.5)*(x-55.5)+151
    if x <= 250.4:  return (300-201)/(250.4-150.5)*(x-150.5)+201
    if x <= 500.4:  return (500-301)/(500.4-250.5)*(x-250.5)+301
    return 500.0


def _aqi_us_from_pm10(pm10):
    if pm10 is None:
        return None
    x = float(pm10)
    if x <= 54:   return (50-0)/(54-0)*(x-0)+0
    if x <= 154:  return (100-51)/(154-55)*(x-55)+51
    if x <= 254:  return (150-101)/(254-155)*(x-155)+101
    if x <= 354:  return (200-151)/(354-255)*(x-255)+151
    if x <= 424:  return (300-201)/(424-355)*(x-355)+201
    if x <= 604:  return (500-301)/(604-425)*(x-425)+301
    return 500.0


def _aqi_level_text(v: int | None) -> str | None:
    if v is None:
        return None
    if v <= 50: return "Good"
    if v <= 100: return "Moderate"
    if v <= 150: return "Unhealthy for Sensitive Groups"
    if v <= 200: return "Unhealthy"
    if v <= 300: return "Very Unhealthy"
    return "Hazardous"


# ----------------- setup entry -----------------
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    api_key: str = entry.data["api_key"]
    stations: list[str] = list(entry.options.get("stations", []))
    session = async_get_clientsession(hass)
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    all_entities: list[SensorEntity] = []

    for location_id in stations:
        url_meta = f"https://api.openaq.org/v3/locations/{location_id}"
        url_latest = f"https://api.openaq.org/v3/locations/{location_id}/latest"

        coordinator_meta = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=f"OpenAQ Meta {location_id}",
            update_method=lambda u=url_meta: _fetch_json(session, u, headers),
            update_interval=SCAN_INTERVAL_META,
        )
        coordinator_latest = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=f"OpenAQ Latest {location_id}",
            update_method=lambda u=url_latest: _fetch_json(session, u, headers),
            update_interval=SCAN_INTERVAL_LATEST,
        )

        await coordinator_meta.async_config_entry_first_refresh()
        await coordinator_latest.async_config_entry_first_refresh()

        meta_root = _meta_root(coordinator_meta.data)
        location_name = meta_root.get("name") or f"Station {location_id}"

        unsub = async_track_time_interval(
            hass,
            lambda now: hass.async_create_task(coordinator_latest.async_request_refresh()),
            SCAN_INTERVAL_LATEST,
        )
        entry.async_on_unload(unsub)

        wanted_params = [
            ("pm1",  "PM1",   SensorDeviceClass.PM1,   CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            ("pm25", "PM2.5", SensorDeviceClass.PM25,  CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            ("pm10", "PM10",  SensorDeviceClass.PM10,  CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            ("co2",  "CO₂",   SensorDeviceClass.CO2,  CONCENTRATION_PARTS_PER_MILLION),
            ("co",   "CO",    SensorDeviceClass.CO, CONCENTRATION_PARTS_PER_MILLION),
            ("no2",  "NO₂",   SensorDeviceClass.NITROGEN_DIOXIDE, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            ("o3",   "O₃",    SensorDeviceClass.OZONE, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            ("so2",  "SO₂",   SensorDeviceClass.SULPHUR_DIOXIDE, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            ("um003","PM0.3 Count", None, None),
        ]

        sids: dict[str, int | None] = {}
        for pname, pretty, devclass, unit in wanted_params:
            sid = _find_sensor_id(meta_root, pname)
            sids[pname] = sid
            if sid is None:
                continue
            precision = 0 if unit == CONCENTRATION_PARTS_PER_MILLION else 2
            all_entities.append(
                OpenAQParamSensor(
                    entry=entry,
                    coordinator=coordinator_latest,
                    location_id=location_id,
                    location_name=location_name,
                    parameter_name=pname,
                    title=pretty,
                    sensor_id=sid,
                    device_class=devclass,
                    unit=unit,
                    precision=precision,
                )
            )

        all_entities.extend([
            OpenAQAQUSValue(entry, coordinator_latest, location_id, location_name, sids.get("pm25"), sids.get("pm10")),
            OpenAQAQUSMainPollutant(entry, coordinator_latest, location_id, location_name, sids.get("pm25"), sids.get("pm10")),
            OpenAQAQUSLevel(entry, coordinator_latest, location_id, location_name, sids.get("pm25"), sids.get("pm10")),
        ])

    async_add_entities(all_entities)


# ----------------- entities -----------------
class OpenAQBaseEntity(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry, coordinator, location_id: str, location_name: str):
        super().__init__(coordinator)
        self._entry = entry
        self._location_id = location_id
        self._location_name = location_name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self._entry.entry_id}_{self._location_id}")},
            "name": self._location_name,
            "manufacturer": "OpenAQ",
            "configuration_url": "https://openaq.org/",
        }


class OpenAQParamSensor(OpenAQBaseEntity):
    def __init__(
        self,
        entry, coordinator, location_id, location_name,
        parameter_name, title, sensor_id, device_class, unit, precision=2,
    ):
        super().__init__(entry, coordinator, location_id, location_name)
        self._parameter_name = parameter_name
        self._sensor_id = sensor_id
        self._attr_name = title
        self._attr_unique_id = f"{entry.entry_id}_{location_id}_{parameter_name}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._precision = precision
        self._attr_suggested_display_precision = precision

    @property
    def native_value(self):
        val = _latest_value(self.coordinator.data, self._sensor_id)
        if val is None:
            return None
        try:
            return round(float(val), self._precision)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        return {
            "updated": _latest_datetime_local(self.coordinator.data),
            "parameter": self._parameter_name,
            "sensors_id": self._sensor_id,
            "location_id": self._location_id,
        }


class _AQIBase(OpenAQBaseEntity):
    def __init__(self, entry, coordinator, location_id, location_name, pm25_sid, pm10_sid):
        super().__init__(entry, coordinator, location_id, location_name)
        self._pm25_sid = pm25_sid
        self._pm10_sid = pm10_sid

    def _vals(self):
        pm25 = _latest_value(self.coordinator.data, self._pm25_sid) if self._pm25_sid else None
        pm10 = _latest_value(self.coordinator.data, self._pm10_sid) if self._pm10_sid else None
        aqi25 = _aqi_us_from_pm25(pm25) if pm25 is not None else None
        aqi10 = _aqi_us_from_pm10(pm10) if pm10 is not None else None
        return pm25, pm10, aqi25, aqi10


class OpenAQAQUSValue(_AQIBase):
    _attr_name = "AQI"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry, coordinator, location_id, location_name, pm25_sid, pm10_sid):
        super().__init__(entry, coordinator, location_id, location_name, pm25_sid, pm10_sid)
        self._attr_unique_id = f"{entry.entry_id}_{location_id}_aqi"

    @property
    def native_value(self):
        _, _, aqi25, aqi10 = self._vals()
        vals = [v for v in (aqi25, aqi10) if v is not None]
        return round(max(vals)) if vals else None

    @property
    def extra_state_attributes(self):
        pm25, pm10, aqi25, aqi10 = self._vals()
        overall = self.native_value
        return {
            "pm25_ugm3": round(float(pm25), 2) if pm25 is not None else None,
            "pm10_ugm3": round(float(pm10), 2) if pm10 is not None else None,
            "pm25_aqi": round(aqi25) if aqi25 is not None else None,
            "pm10_aqi": round(aqi10) if aqi10 is not None else None,
            "main_pollutant": "PM2.5" if (aqi25 or -1) >= (aqi10 or -1) else "PM10" if aqi10 is not None else None,
            "level": _aqi_level_text(overall) if overall is not None else None,
            "updated": _latest_datetime_local(self.coordinator.data),
            "location_id": self._location_id,
        }


class OpenAQAQUSMainPollutant(_AQIBase):
    _attr_name = "AQI Main Pollutant"
    _attr_state_class = None

    def __init__(self, entry, coordinator, location_id, location_name, pm25_sid, pm10_sid):
        super().__init__(entry, coordinator, location_id, location_name, pm25_sid, pm10_sid)
        self._attr_unique_id = f"{entry.entry_id}_{location_id}_aqi_main"

    @property
    def native_value(self):
        _, _, aqi25, aqi10 = self._vals()
        if aqi25 is None and aqi10 is None:
            return None
        return "PM2.5" if (aqi25 or -1) >= (aqi10 or -1) else "PM10"


class OpenAQAQUSLevel(_AQIBase):
    _attr_name = "AQI Level"
    _attr_state_class = None

    def __init__(self, entry, coordinator, location_id, location_name, pm25_sid, pm10_sid):
        super().__init__(entry, coordinator, location_id, location_name, pm25_sid, pm10_sid)
        self._attr_unique_id = f"{entry.entry_id}_{location_id}_aqi_level"

    @property
    def native_value(self):
        _, _, aqi25, aqi10 = self._vals()
        vals = [v for v in (aqi25, aqi10) if v is not None]
        return _aqi_level_text(round(max(vals))) if vals else None
