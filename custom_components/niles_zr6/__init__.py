"""The Niles ZR-6 MultiZone Receiver integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

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
    client = NilesZR6Client(entry.data[CONF_HOST], entry.data[CONF_PORT])
    zones = list(range(1, entry.data[CONF_NUM_ZONES] + 1))

    coordinator = NilesZR6Coordinator(hass, client, zones)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
