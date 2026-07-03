"""Last-response diagnostic sensor for the Niles ZR-6."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NilesZR6Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the last-response sensor."""
    coordinator: NilesZR6Coordinator = entry.runtime_data
    async_add_entities([NilesLastResponseSensor(coordinator, entry)])


class NilesLastResponseSensor(CoordinatorEntity[NilesZR6Coordinator], SensorEntity):
    """Timestamp of the last successful status response from the ZR-6."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Last response"

    def __init__(self, coordinator: NilesZR6Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_response"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    @property
    def available(self) -> bool:
        """Keep showing the last known response time even when polling fails."""
        return True

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_response
