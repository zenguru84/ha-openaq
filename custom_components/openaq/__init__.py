"""OpenAQ Air Quality component."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

DOMAIN = "openaq"
PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenAQ from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})
    hass.data[DOMAIN][entry.entry_id]["reloading"] = False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload OpenAQ config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload only if not currently removing a device."""
    if hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("reloading", False):
        return
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


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
        import asyncio

        async def _unblock():
            await asyncio.sleep(2)
            hass.data[DOMAIN][entry.entry_id]["reloading"] = False

        hass.async_create_task(_unblock())
