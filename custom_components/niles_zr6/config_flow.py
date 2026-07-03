"""Config flow for the Niles ZR-6 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_CONNECTION_MODE,
    CONF_NUM_ZONES,
    CONF_SCAN_INTERVAL,
    CONF_SOURCES,
    CONF_ZONE_NAMES,
    DEFAULT_CONNECTION_MODE,
    DEFAULT_NUM_ZONES,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MAX_ZONES,
    MIN_SCAN_INTERVAL,
    MODE_EXCLUSIVE,
    MODE_SHARED,
    NUM_SOURCES,
)
from .protocol import NilesZR6Client, NilesZR6Error

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_NUM_ZONES, default=DEFAULT_NUM_ZONES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_ZONES)
        ),
    }
)


async def _async_validate_connection(host: str, port: int) -> bool:
    """Return True if the ZR-6 answers a status request."""
    client = NilesZR6Client(host, port)
    try:
        await client.async_get_status([1])
    except NilesZR6Error:
        return False
    return True


class NilesZR6ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Niles ZR-6."""

    VERSION = 1

    def __init__(self) -> None:
        self._base_data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "NilesZR6OptionsFlow":
        """Create the options flow."""
        return NilesZR6OptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: connection settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            )
            self._abort_if_unique_id_configured()

            if not await _async_validate_connection(
                user_input[CONF_HOST], user_input[CONF_PORT]
            ):
                errors["base"] = "cannot_connect"
            else:
                self._base_data = dict(user_input)
                return await self.async_step_names()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second step: zone and source names."""
        num_zones = self._base_data[CONF_NUM_ZONES]

        if user_input is not None:
            zone_names = {
                str(i): user_input[f"zone_{i}_name"].strip() or f"Zone {i}"
                for i in range(1, num_zones + 1)
            }
            sources = [
                user_input[f"source_{i}_name"].strip() or f"Source {i}"
                for i in range(1, NUM_SOURCES + 1)
            ]
            data = {
                **self._base_data,
                CONF_ZONE_NAMES: zone_names,
                CONF_SOURCES: sources,
            }
            return self.async_create_entry(
                title=f"Niles ZR-6 ({self._base_data[CONF_HOST]})", data=data
            )

        schema_dict: dict[Any, Any] = {}
        for i in range(1, num_zones + 1):
            schema_dict[vol.Required(f"zone_{i}_name", default=f"Zone {i}")] = str
        for i in range(1, NUM_SOURCES + 1):
            schema_dict[vol.Required(f"source_{i}_name", default=f"Source {i}")] = str

        return self.async_show_form(
            step_id="names", data_schema=vol.Schema(schema_dict)
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the bridge host/port of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            if not await _async_validate_connection(
                user_input[CONF_HOST], user_input[CONF_PORT]
            ):
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                vol.Required(CONF_PORT, default=entry.data[CONF_PORT]): int,
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )


class NilesZR6OptionsFlow(OptionsFlow):
    """Reconfigure zone count, scan interval and zone/source names."""

    def __init__(self) -> None:
        self._num_zones: int | None = None
        self._scan_interval: int | None = None
        self._connection_mode: str | None = None

    @property
    def _conf(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: number of zones and scan interval."""
        if user_input is not None:
            self._num_zones = user_input[CONF_NUM_ZONES]
            self._scan_interval = user_input[CONF_SCAN_INTERVAL]
            self._connection_mode = user_input[CONF_CONNECTION_MODE]
            return await self.async_step_names()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NUM_ZONES, default=self._conf[CONF_NUM_ZONES]
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_ZONES)),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self._conf.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Required(
                    CONF_CONNECTION_MODE,
                    default=self._conf.get(
                        CONF_CONNECTION_MODE, DEFAULT_CONNECTION_MODE
                    ),
                ): vol.In([MODE_SHARED, MODE_EXCLUSIVE]),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second step: zone and source names."""
        num_zones = self._num_zones or self._conf[CONF_NUM_ZONES]

        if user_input is not None:
            zone_names = {
                str(i): user_input[f"zone_{i}_name"].strip() or f"Zone {i}"
                for i in range(1, num_zones + 1)
            }
            sources = [
                user_input[f"source_{i}_name"].strip() or f"Source {i}"
                for i in range(1, NUM_SOURCES + 1)
            ]
            return self.async_create_entry(
                title="",
                data={
                    CONF_NUM_ZONES: num_zones,
                    CONF_SCAN_INTERVAL: self._scan_interval
                    or self._conf.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    CONF_CONNECTION_MODE: self._connection_mode
                    or self._conf.get(
                        CONF_CONNECTION_MODE, DEFAULT_CONNECTION_MODE
                    ),
                    CONF_ZONE_NAMES: zone_names,
                    CONF_SOURCES: sources,
                },
            )

        old_names: dict[str, str] = self._conf.get(CONF_ZONE_NAMES, {})
        old_sources: list[str] = self._conf.get(CONF_SOURCES, [])
        schema_dict: dict[Any, Any] = {}
        for i in range(1, num_zones + 1):
            schema_dict[
                vol.Required(
                    f"zone_{i}_name", default=old_names.get(str(i), f"Zone {i}")
                )
            ] = str
        for i in range(1, NUM_SOURCES + 1):
            default = old_sources[i - 1] if len(old_sources) >= i else f"Source {i}"
            schema_dict[vol.Required(f"source_{i}_name", default=default)] = str

        return self.async_show_form(
            step_id="names", data_schema=vol.Schema(schema_dict)
        )
