"""DataUpdateCoordinator for the Niles ZR-6 integration."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FAST_POLL_SECONDS,
    FAST_POLL_WINDOW_SECONDS,
)
from .protocol import NilesZR6Client, NilesZR6Error, ZoneStatus

_LOGGER = logging.getLogger(__name__)


class NilesZR6Coordinator(DataUpdateCoordinator[dict[int, ZoneStatus]]):
    """Polls all configured zones in a single short-lived connection."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: NilesZR6Client,
        zones: list[int],
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        linked_zones: list[int] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.zones = zones
        self.linked_zones: set[int] = set(linked_zones or [])
        self.last_response: datetime | None = None
        self._base_interval = timedelta(seconds=scan_interval)
        self._fast_until = 0.0

    def verify_zones_for(self, zone: int) -> list[int]:
        """Zones to verify after a power/source command on ``zone``.

        With a configured Zone Linking group, commands on a linked zone are
        verified for the whole group and commands on other zones only for
        themselves. Without configuration all zones are verified (safe
        default for unknown amp linking).
        """
        if not self.linked_zones:
            return list(self.zones)
        if zone in self.linked_zones:
            group = {zone} | self.linked_zones
            return [z for z in self.zones if z in group]
        return [zone]

    def notify_activity(self) -> None:
        """Poll faster for a short window after user interaction."""
        self._fast_until = time.monotonic() + FAST_POLL_WINDOW_SECONDS
        fast = timedelta(seconds=FAST_POLL_SECONDS)
        if self.update_interval != fast:
            self.update_interval = fast

    async def _async_update_data(self) -> dict[int, ZoneStatus]:
        try:
            data = await self.client.async_get_status(self.zones)
        except NilesZR6Error as err:
            raise UpdateFailed(str(err)) from err
        self.last_response = dt_util.utcnow()
        # If a zone's reply was discarded this cycle (e.g. active-zone race
        # with another controller), keep its last known status instead of
        # flapping to unavailable.
        merged: dict[int, ZoneStatus] = dict(self.data) if self.data else {}
        merged.update(data)
        if self._fast_until and time.monotonic() >= self._fast_until:
            self._fast_until = 0.0
            self.update_interval = self._base_interval
        return {z: s for z, s in merged.items() if z in self.zones}

    def apply_status(self, status: ZoneStatus | None) -> None:
        """Merge a fresh single-zone status (from a verified command)."""
        if status is None:
            return
        self.apply_statuses({status.zone: status})

    def apply_statuses(self, statuses: dict[int, ZoneStatus] | None) -> None:
        """Merge fresh zone statuses (from a verified command).

        Lets entities update immediately after a command without scheduling a
        full poll cycle. Multiple zones may change at once on amps with the
        Zone Linking feature enabled.
        """
        if not statuses:
            return
        self.notify_activity()
        self.last_response = dt_util.utcnow()
        merged: dict[int, ZoneStatus] = dict(self.data) if self.data else {}
        for zone, status in statuses.items():
            if zone in self.zones:
                merged[zone] = status
        self.async_set_updated_data(merged)
