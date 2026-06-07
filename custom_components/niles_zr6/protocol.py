"""Low-level RS-232-over-IP protocol client for the Niles ZR-6 MultiZone Receiver.

Protocol reference: "ZR-6 MultiZone Receiver RS-232C Control Protocols" (Niles Audio).

Important design note: many RS232-over-IP bridges accept only ONE TCP client at
a time. To allow other controllers (e.g. Node-RED) to share the bridge, this
client deliberately uses a connect -> send -> read -> disconnect pattern for
every operation instead of holding a persistent socket. All operations are
serialized with an asyncio lock.

This module has no Home Assistant dependencies so it can be unit-tested
standalone.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 3.0
TERMINATOR = b"\r\n"

# Zone specific command (zsc) codes from the official protocol document.
CMD_SOURCE = {1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06"}
CMD_OFF = "10"
CMD_MUTE = "11"  # toggle
CMD_VOL_UP = "12"
CMD_VOL_DOWN = "13"


@dataclass
class ZoneStatus:
    """Parsed status of one zone (from a 'usc,2,...' response)."""

    zone: int
    source: int  # 1-6
    power: bool
    volume: int  # 0-100
    muted: bool
    bass: int  # -7..+7
    treble: int  # -7..+7


def parse_usc(line: str) -> ZoneStatus | None:
    """Parse a zone status response line.

    Format: usc,2,<zone>,<source>,<on/off>,<volume>,<mute>,<bass>,<treble>
    Example: usc,2,2,3,1,14,0,0,0
    """
    line = line.strip()
    if not line.startswith("usc,"):
        return None
    parts = line.split(",")
    # usc,1 is the unsolicited "ready" message after boot; usc,2 is a status reply.
    if len(parts) < 9 or parts[1] != "2":
        return None
    try:
        return ZoneStatus(
            zone=int(parts[2]),
            source=int(parts[3]),
            power=parts[4] == "1",
            volume=int(parts[5]),
            muted=parts[6] == "1",
            bass=int(parts[7]),
            treble=int(parts[8]),
        )
    except ValueError:
        return None


class NilesZR6Error(Exception):
    """Communication error with the ZR-6."""


class NilesZR6Client:
    """Asyncio client using short-lived TCP connections."""

    def __init__(self, host: str, port: int = 23) -> None:
        self._host = host
        self._port = port
        self._lock = asyncio.Lock()

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), CONNECT_TIMEOUT
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise NilesZR6Error(
                f"Cannot connect to {self._host}:{self._port}: {err}"
            ) from err

    @staticmethod
    async def _close(writer: asyncio.StreamWriter) -> None:
        try:
            writer.close()
            await writer.wait_closed()
        except OSError:
            pass

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, command: str) -> None:
        _LOGGER.debug("TX: %s", command)
        writer.write(command.encode("ascii") + TERMINATOR)
        await writer.drain()

    @staticmethod
    async def _read_line(reader: asyncio.StreamReader) -> str:
        # Responses are terminated with a carriage return.
        data = await asyncio.wait_for(reader.readuntil(b"\r"), READ_TIMEOUT)
        return data.decode("ascii", errors="ignore").strip()

    async def _read_until_prefix(
        self, reader: asyncio.StreamReader, prefixes: tuple[str, ...], max_lines: int = 10
    ) -> str:
        """Read lines until one starts with an expected prefix.

        Skips empty lines (leftover line feeds) and unrelated unsolicited
        messages. Returns \"\" on timeout/EOF.
        """
        for _ in range(max_lines):
            try:
                line = await self._read_line(reader)
            except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError):
                return ""
            if not line:
                continue
            _LOGGER.debug("RX: %s", line)
            if line.startswith(prefixes):
                return line
        return ""

    @staticmethod
    async def _flush_input(reader: asyncio.StreamReader) -> None:
        """Discard any stale buffered data (e.g. replies to another client's
        commands relayed by the RS232 bridge, or leftovers from a previous
        connection)."""
        for _ in range(10):
            try:
                data = await asyncio.wait_for(reader.read(1024), 0.15)
            except (asyncio.TimeoutError, OSError):
                return
            if not data:
                return

    async def _poll_zone(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        zone: int,
    ) -> ZoneStatus | None:
        """Select a zone, query its status, and validate the reply.

        Returns None if no valid reply for *this* zone was received (e.g.
        because another controller changed the amp's active control zone
        between our select and query).
        """
        await self._send(writer, f"znc,4,{zone}")
        rznc = await self._read_until_prefix(reader, ("rznc,4,",))
        if rznc:
            parts = rznc.split(",")
            if len(parts) >= 3 and parts[2].strip() != str(zone):
                _LOGGER.debug(
                    "Zone %s: select confirmed a different zone (%s)", zone, rznc
                )
        await self._send(writer, "znc,5")
        line = await self._read_until_prefix(reader, ("usc,2",))
        status = parse_usc(line)
        if status is None:
            _LOGGER.debug("Zone %s: no status reply", zone)
            return None
        if status.zone != zone:
            # Another controller (e.g. Node-RED) changed the active zone
            # between our select and query. Never attribute this reply.
            _LOGGER.debug(
                "Zone %s: discarding status reply for zone %s", zone, status.zone
            )
            return None
        return status

    async def async_get_status(self, zones: list[int]) -> dict[int, ZoneStatus]:
        """Poll status for the given zones over one short-lived connection.

        The ZR-6 only reports status for the active control zone, so for each
        zone we first make it active (znc,4,<zone>) and then request status
        (znc,5). Each reply is validated against the requested zone and
        retried once on mismatch, so interleaved commands from another
        controller can never corrupt zone states.
        """
        async with self._lock:
            reader, writer = await self._open()
            try:
                await self._flush_input(reader)
                statuses: dict[int, ZoneStatus] = {}
                for zone in zones:
                    status = await self._poll_zone(reader, writer, zone)
                    if status is None:
                        # Retry once: re-select and re-query this zone.
                        status = await self._poll_zone(reader, writer, zone)
                    if status is not None:
                        statuses[zone] = status
                    else:
                        _LOGGER.debug("No valid status for zone %s this cycle", zone)
                if not statuses:
                    raise NilesZR6Error("No zone status received from ZR-6")
                return statuses
            finally:
                await self._close(writer)

    async def async_zone_command(self, zone: int, code: str) -> None:
        """Send a zone specific command: zsc,<zone>,<code>."""
        async with self._lock:
            reader, writer = await self._open()
            try:
                await self._send(writer, f"zsc,{zone},{code}")
                response = await self._read_until_prefix(reader, ("rzsc",))
                if "FAIL" in response:
                    raise NilesZR6Error(f"Command zsc,{zone},{code} failed: {response}")
            finally:
                await self._close(writer)
