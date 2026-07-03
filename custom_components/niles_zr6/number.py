"""Number platform: bass and treble per zone for the Niles ZR-6."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NUM_ZONES, CONF_ZONE_NAMES, DOMAIN
from .coordinator import NilesZR6Coordinator
from .protocol import TONE_MAX, TONE_MIN, NilesZR6Error

_LOGGER = logging.getLogger(__name__)

TONE_CONTROLS = ("bass", "treble")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up bass/treble number entities, two per zone."""
    coordinator: NilesZR6Coordinator = hass.data[DOMAIN][entry.entry_id]
    conf = {**entry.data, **entry.options}
    zone_names: dict[str, str] = conf.get(CONF_ZONE_NAMES, {})

    entities = [
        NilesToneNumber(
            coordinator,
            entry,
            zone,
            zone_names.get(str(zone), f"Zone {zone}"),
            control,
        )
        for zone in range(1, conf[CONF_NUM_ZONES] + 1)
        for control in TONE_CONTROLS
    ]
    async_add_entities(entities)


class NilesToneNumber(CoordinatorEntity[NilesZR6Coordinator], NumberEntity):
    """Bass or treble control for one zone (-7..+7)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = TONE_MIN
    _attr_native_max_value = TONE_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: NilesZR6Coordinator,
        entry: ConfigEntry,
        zone: int,
        zone_name: str,
        control: str,
    ) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._control = control
        self._attr_name = f"{zone_name} {control}"
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone}_{control}"
        self._attr_icon = (
            "mdi:speaker" if control == "bass" else "mdi:music-clef-treble"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Niles ZR-6",
            manufacturer="Niles Audio",
            model="ZR-6 MultiZone Receiver",
        )

    @property
    def _status(self):
        return self.coordinator.data.get(self._zone) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self._status is not None

    @property
    def native_value(self) -> float | None:
        status = self._status
        if status is None:
            return None
        return float(getattr(status, self._control))

    async def async_set_native_value(self, value: float) -> None:
        try:
            status = await self.coordinator.client.async_set_tone(
                self._zone, self._control, int(value)
            )
        except NilesZR6Error as err:
            _LOGGER.error(
                "Zone %s set %s failed: %s", self._zone, self._control, err
            )
            await self.coordinator.async_request_refresh()
            return
        if status is not None:
            self.coordinator.apply_status(status)
        else:
            await self.coordinator.async_request_refresh()
