"""Diagnostics support for the Niles ZR-6 integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import NilesZR6Coordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: NilesZR6Coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry_data": dict(entry.data),
        "entry_options": dict(entry.options),
        "zones": coordinator.zones,
        "update_interval_seconds": (
            coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None
        ),
        "last_update_success": coordinator.last_update_success,
        "last_response": (
            coordinator.last_response.isoformat()
            if coordinator.last_response
            else None
        ),
        "zone_status": {
            zone: asdict(status)
            for zone, status in (coordinator.data or {}).items()
        },
    }
