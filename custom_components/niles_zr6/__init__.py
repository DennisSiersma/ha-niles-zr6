"""The Niles ZR-6 MultiZone Receiver integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_NUM_ZONES, DOMAIN
from .coordinator import NilesZR6Coordinator
from .protocol import NilesZR6Client

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Niles ZR-6 from a config entry."""
    conf = {**entry.data, **entry.options}
    client = NilesZR6Client(conf[CONF_HOST], conf[CONF_PORT])
    num_zones: int = conf[CONF_NUM_ZONES]
    zones = list(range(1, num_zones + 1))

    # Clean up entities for zones that are no longer configured.
    ent_reg = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if "_zone_" in reg_entry.unique_id:
            suffix = reg_entry.unique_id.rsplit("_zone_", 1)[1]
            if suffix.isdigit() and int(suffix) > num_zones:
                ent_reg.async_remove(reg_entry.entity_id)

    coordinator = NilesZR6Coordinator(hass, client, zones)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

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
