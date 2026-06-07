"""Connection diagnostic binary sensor for the Niles ZR-6."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up the connection binary sensor."""
    coordinator: NilesZR6Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NilesConnectionSensor(coordinator, entry)])


class NilesConnectionSensor(
    CoordinatorEntity[NilesZR6Coordinator], BinarySensorEntity
):
    """On when the last poll of the ZR-6 returned a valid response."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Connection"

    def __init__(self, coordinator: NilesZR6Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    @property
    def available(self) -> bool:
        """Always available: this sensor reports the connection state itself."""
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success
