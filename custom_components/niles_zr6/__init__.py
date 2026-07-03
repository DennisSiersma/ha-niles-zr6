"""The Niles ZR-6 MultiZone Receiver integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import (
    ATTR_COMMAND,
    ATTR_FREQUENCY,
    ATTR_SOURCE,
    CONF_NUM_ZONES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    NUM_SOURCES,
    SERVICE_ALL_ZONES_OFF,
    SERVICE_ALL_ZONES_SOURCE,
    SERVICE_SEND_COMMAND,
    SERVICE_TUNE,
)
from .coordinator import NilesZR6Coordinator
from .protocol import CMD_OFF, CMD_SOURCE, NilesZR6Client, NilesZR6Error

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SENSOR,
]

SERVICE_ALL_ZONES_SOURCE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SOURCE): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=NUM_SOURCES)
        )
    }
)
SERVICE_TUNE_SCHEMA = vol.Schema({vol.Required(ATTR_FREQUENCY): cv.string})
SERVICE_SEND_COMMAND_SCHEMA = vol.Schema({vol.Required(ATTR_COMMAND): cv.string})


def _get_coordinator(hass: HomeAssistant) -> NilesZR6Coordinator:
    """Return the coordinator of the first loaded entry."""
    coordinators: dict[str, NilesZR6Coordinator] = hass.data.get(DOMAIN, {})
    for coordinator in coordinators.values():
        return coordinator
    raise HomeAssistantError("Niles ZR-6 is not set up")


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain-level services (idempotent)."""

    if hass.services.has_service(DOMAIN, SERVICE_ALL_ZONES_SOURCE):
        return

    async def _all_zones_source(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        source: int = call.data[ATTR_SOURCE]
        try:
            await coordinator.client.async_global_command(CMD_SOURCE[source])
        except NilesZR6Error as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_request_refresh()

    async def _all_zones_off(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        try:
            await coordinator.client.async_global_command(CMD_OFF)
        except NilesZR6Error as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_request_refresh()

    async def _tune(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        try:
            await coordinator.client.async_tune(call.data[ATTR_FREQUENCY])
        except NilesZR6Error as err:
            raise HomeAssistantError(str(err)) from err

    async def _send_command(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass)
        try:
            lines = await coordinator.client.async_send_raw(call.data[ATTR_COMMAND])
        except NilesZR6Error as err:
            raise HomeAssistantError(str(err)) from err
        return {"response": lines}

    hass.services.async_register(
        DOMAIN,
        SERVICE_ALL_ZONES_SOURCE,
        _all_zones_source,
        schema=SERVICE_ALL_ZONES_SOURCE_SCHEMA,
    )
    hass.services.async_register(DOMAIN, SERVICE_ALL_ZONES_OFF, _all_zones_off)
    hass.services.async_register(
        DOMAIN, SERVICE_TUNE, _tune, schema=SERVICE_TUNE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        _send_command,
        schema=SERVICE_SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Niles ZR-6 from a config entry."""
    conf = {**entry.data, **entry.options}
    client = NilesZR6Client(conf[CONF_HOST], conf[CONF_PORT])
    num_zones: int = conf[CONF_NUM_ZONES]
    zones = list(range(1, num_zones + 1))
    scan_interval: int = conf.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    # Clean up entities for zones that are no longer configured.
    ent_reg = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if "_zone_" in reg_entry.unique_id:
            suffix = reg_entry.unique_id.rsplit("_zone_", 1)[1]
            # unique_ids look like <entry>_zone_<n> or <entry>_zone_<n>_bass.
            zone_part = suffix.split("_", 1)[0]
            if zone_part.isdigit() and int(zone_part) > num_zones:
                ent_reg.async_remove(reg_entry.entity_id)

    coordinator = NilesZR6Coordinator(hass, client, zones, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
