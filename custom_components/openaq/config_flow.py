from __future__ import annotations

import voluptuous as vol
import async_timeout
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .__init__ import DOMAIN

class OpenAQConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._location_id: str | None = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if self._async_current_entries():
                errors["base"] = "single_instance_allowed"
            else:
                api_key = user_input["api_key"]
                try:
                    await _probe_key(self.hass, api_key)
                except ValueError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    pass
                if not errors:
                    self._api_key = api_key
                    return await self.async_step_station()

        schema = vol.Schema({vol.Required("api_key"): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_station(self, user_input=None):
        errors = {}
        assert self._api_key is not None

        if user_input is not None:
            loc = (user_input.get("location_id") or "").strip()
            if not loc:
                errors["location_id"] = "required"
            else:
                try:
                    name = await _validate_location(self.hass, self._api_key, loc)
                    if not name:
                        errors["location_id"] = "not_found"
                    else:
                        self._location_id = loc
                        title = f"OpenAQ Stations"
                        return self.async_create_entry(
                            title=title,
                            data={"api_key": self._api_key},
                            options={"stations": [self._location_id]},
                        )
                except ValueError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    errors["base"] = "cannot_connect"

        schema = vol.Schema({vol.Required("location_id"): str})
        return self.async_show_form(step_id="station", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return OpenAQOptionsFlow(entry)


class OpenAQOptionsFlow(config_entries.OptionsFlow):

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None):
        errors = {}
        api_key: str = self.entry.data.get("api_key", "")
        stations: list[str] = list(self.entry.options.get("stations", []))

        if user_input is not None:
            loc = (user_input.get("add_location_id") or "").strip()

            if not loc:
                errors["add_location_id"] = "required"
            elif loc in stations:
                errors["base"] = "already_configured"
            elif len(stations) >= 3:
                errors["base"] = "max_entries_reached"
            else:
                try:
                    name = await _validate_location(self.hass, api_key, loc)
                    if not name:
                        errors["add_location_id"] = "not_found"
                    else:
                        stations.append(loc)
                        return self.async_create_entry(title="", data={"stations": stations})
                except ValueError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    errors["base"] = "cannot_connect"

        schema = vol.Schema({vol.Required("add_location_id"): str})
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "list": ", ".join(stations) if stations else "none"
            },
        )


# ------- helpers -------

async def _probe_key(hass, api_key: str) -> None:
    url = "https://api.openaq.org/v3/locations/0"
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    session = async_get_clientsession(hass)
    async with async_timeout.timeout(10):
        async with session.get(url, headers=headers) as resp:
            if resp.status == 401:
                raise ValueError("invalid_auth")

async def _validate_location(hass, api_key: str, location_id: str) -> str | None:
    url = f"https://api.openaq.org/v3/locations/{location_id}"
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    session = async_get_clientsession(hass)
    async with async_timeout.timeout(15):
        async with session.get(url, headers=headers) as resp:
            if resp.status == 401:
                raise ValueError("invalid_auth")
            resp.raise_for_status()
            data = await resp.json()
            results = data.get("results", [])
            return results[0].get("name") if results else None
