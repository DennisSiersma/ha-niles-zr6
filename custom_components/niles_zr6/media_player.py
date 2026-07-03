"""Media player platform for the Niles ZR-6 MultiZone Receiver."""

from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NUM_ZONES, CONF_SOURCES, CONF_ZONE_NAMES, DOMAIN
from .coordinator import NilesZR6Coordinator
from .protocol import (
    CMD_MUTE,
    CMD_OFF,
    CMD_SOURCE,
    CMD_VOL_DOWN,
    CMD_VOL_UP,
    NilesZR6Error,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up media player entities, one per zone."""
    coordinator: NilesZR6Coordinator = entry.runtime_data
    conf = {**entry.data, **entry.options}
    zone_names: dict[str, str] = conf.get(CONF_ZONE_NAMES, {})
    sources: list[str] = conf.get(
        CONF_SOURCES, [f"Source {i}" for i in range(1, 7)]
    )

    entities = [
        NilesZoneMediaPlayer(
            coordinator,
            entry,
            zone,
            zone_names.get(str(zone), f"Zone {zone}"),
            sources,
        )
        for zone in range(1, conf[CONF_NUM_ZONES] + 1)
    ]
    async_add_entities(entities)


class NilesZoneMediaPlayer(CoordinatorEntity[NilesZR6Coordinator], MediaPlayerEntity):
    """One zone of the Niles ZR-6."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NilesZR6Coordinator,
        entry: ConfigEntry,
        zone: int,
        name: str,
        sources: list[str],
    ) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._sources = sources
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone}"
        self._attr_source_list = list(sources)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Niles ZR-6",
            manufacturer="Niles Audio",
            model="ZR-6 MultiZone Receiver",
            configuration_url=None,
        )

    @property
    def _status(self):
        return self.coordinator.data.get(self._zone) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self._status is not None

    @property
    def state(self) -> MediaPlayerState | None:
        status = self._status
        if status is None:
            return None
        return MediaPlayerState.ON if status.power else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        status = self._status
        if status is None:
            return None
        return status.volume / 100

    @property
    def is_volume_muted(self) -> bool | None:
        status = self._status
        if status is None:
            return None
        return status.muted

    @property
    def source(self) -> str | None:
        status = self._status
        if status is None or not 1 <= status.source <= len(self._sources):
            return None
        return self._sources[status.source - 1]

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        status = self._status
        if status is None:
            return None
        return {"bass": status.bass, "treble": status.treble, "zone": self._zone}

    async def _async_command(self, code: str, verify_all: bool = False) -> None:
        """Send a command; the client verifies and returns fresh statuses.

        Power and source commands can affect multiple zones at once on amps
        with Zone Linking enabled, so those callers set verify_all=True to
        re-read every configured zone in the same session.
        """
        try:
            statuses = await self.coordinator.client.async_zone_command(
                self._zone,
                code,
                verify_zones=self.coordinator.verify_zones_for(self._zone)
                if verify_all
                else None,
            )
        except NilesZR6Error as err:
            _LOGGER.error("Zone %s command %s failed: %s", self._zone, code, err)
            await self.coordinator.async_request_refresh()
            return
        if statuses:
            self.coordinator.apply_statuses(statuses)
        else:
            await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the zone on by selecting the last known source.

        The ZR-6 has no discrete 'on' command; selecting a source powers the
        zone on.
        """
        status = self._status
        source = status.source if status and 1 <= status.source <= 6 else 1
        await self._async_command(CMD_SOURCE[source], verify_all=True)

    async def async_turn_off(self) -> None:
        await self._async_command(CMD_OFF, verify_all=True)

    async def async_volume_up(self) -> None:
        await self._async_command(CMD_VOL_UP)

    async def async_volume_down(self) -> None:
        await self._async_command(CMD_VOL_DOWN)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set an absolute volume level (0..1) via step emulation."""
        target = round(volume * 100)
        try:
            status = await self.coordinator.client.async_set_volume(
                self._zone, target
            )
        except NilesZR6Error as err:
            _LOGGER.error("Zone %s set volume failed: %s", self._zone, err)
            await self.coordinator.async_request_refresh()
            return
        if status is not None:
            self.coordinator.apply_status(status)
        else:
            await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute is a toggle on the ZR-6; only send when state differs."""
        if self.is_volume_muted != mute:
            await self._async_command(CMD_MUTE)

    async def async_select_source(self, source: str) -> None:
        if source not in self._sources:
            _LOGGER.warning("Unknown source: %s", source)
            return
        await self._async_command(
            CMD_SOURCE[self._sources.index(source) + 1], verify_all=True
        )
