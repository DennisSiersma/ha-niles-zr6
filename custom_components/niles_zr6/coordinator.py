"""DataUpdateCoordinator for the Niles ZR-6 integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
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
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.zones = zones
        self.last_response: datetime | None = None

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
        return {z: s for z, s in merged.items() if z in self.zones}

    def apply_status(self, status: ZoneStatus | None) -> None:
        """Merge a fresh single-zone status (from a verified command).

        Lets entities update immediately after a command without scheduling a
        full poll cycle of all zones.
        """
        if status is None or status.zone not in self.zones:
            return
        self.last_response = dt_util.utcnow()
        merged: dict[int, ZoneStatus] = dict(self.data) if self.data else {}
        merged[status.zone] = status
        self.async_set_updated_data(merged)
