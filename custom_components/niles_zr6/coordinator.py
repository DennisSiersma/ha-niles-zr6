"""DataUpdateCoordinator for the Niles ZR-6 integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SCAN_INTERVAL_SECONDS
from .protocol import NilesZR6Client, NilesZR6Error, ZoneStatus

_LOGGER = logging.getLogger(__name__)


class NilesZR6Coordinator(DataUpdateCoordinator[dict[int, ZoneStatus]]):
    """Polls all configured zones in a single short-lived connection."""

    def __init__(
        self, hass: HomeAssistant, client: NilesZR6Client, zones: list[int]
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
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
        return data
