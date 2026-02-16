"""OpenAQ Air Quality component."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SCAN_INTERVAL_META = timedelta(hours=12)
SCAN_INTERVAL_LATEST = timedelta(minutes=5)


async def _fetch_json(session, url: str, headers: dict) -> dict:
    """Fetch JSON with proper response closing."""
    try:
        async with async_timeout.timeout(15):
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                return await resp.json()
    except Exception as err:
        raise UpdateFailed(f"Error fetching {url}: {err}") from err


def _meta_root(meta_data: dict) -> dict:
    if not meta_data:
        return {}
    results = meta_data.get("results", [])
    return results[0] if results else {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenAQ from a config entry.

    IMPORTANT (HA 2026.x):
    - Any ConfigEntryNotReady / ConfigEntryError must be raised BEFORE forwarding platforms.
    """
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})
    hass.data[DOMAIN][entry.entry_id]["reloading"] = False

    api_key: str = entry.data.get("api_key", "")
    stations: list[str] = list(entry.options.get("stations", []))

    session = async_get_clientsession(hass)
    headers = {"X-API-Key": api_key, "Accept": "application/json"}

    stations_data: dict[str, dict] = {}

    try:
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

            # Do first refresh here, not inside sensor platform.
            await coordinator_meta.async_config_entry_first_refresh()
            await coordinator_latest.async_config_entry_first_refresh()

            meta_root = _meta_root(coordinator_meta.data)
            location_name = meta_root.get("name") or f"Station {location_id}"

            stations_data[location_id] = {
                "location_name": location_name,
                "meta_root": meta_root,
                "coordinator_latest": coordinator_latest,
                "coordinator_meta": coordinator_meta,
            }

    except Exception as err:
        # This must happen before async_forward_entry_setups()
        raise ConfigEntryNotReady(f"OpenAQ not ready: {err}") from err

    hass.data[DOMAIN][entry.entry_id].update(
        {
            "session": session,
            "headers": headers,
            "stations": stations_data,
        }
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload OpenAQ config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload only if not currently removing a device."""
    if hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("reloading", False):
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def _prune_station_options(hass: HomeAssistant, entry_id: str, location_id: str) -> None:
    """Remove the deleted location from options after device removal."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry:
        return

    stations = [s for s in entry.options.get("stations", []) if s != location_id]
    if stations != entry.options.get("stations", []):
        hass.config_entries.async_update_entry(entry, options={"stations": stations})


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Handle 'Remove device' safely without triggering reload loops."""
    location_id = None
    for domain, ident in device_entry.identifiers:
        if domain == DOMAIN and ident.startswith(f"{entry.entry_id}_"):
            _, location_id = ident.split("_", 1)
            break

    if not location_id:
        return False

    hass.data[DOMAIN][entry.entry_id]["reloading"] = True
    try:
        hass.async_create_task(_prune_station_options(hass, entry.entry_id, location_id))
        return True
    finally:

        async def _unblock():
            await asyncio.sleep(2)
            if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
                hass.data[DOMAIN][entry.entry_id]["reloading"] = False

        hass.async_create_task(_unblock())
