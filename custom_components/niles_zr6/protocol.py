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
# The protocol document specifies commands terminated with a carriage return.
TERMINATOR = b"\r"

# Zone specific command (zsc) codes from the official protocol document.
CMD_SOURCE = {1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06"}
CMD_OFF = "10"
CMD_MUTE = "11"  # toggle
CMD_VOL_UP = "12"
CMD_VOL_DOWN = "13"
# Bass/treble step codes: the protocol document lists these in its hex-code
# table (80/81/82/83); zsc command codes are sent as decimal strings.
CMD_BASS_UP = "128"
CMD_BASS_DOWN = "129"
CMD_TREBLE_UP = "130"
CMD_TREBLE_DOWN = "131"

TONE_MIN = -7
TONE_MAX = 7

# Safety caps for closed-loop stepping.
MAX_VOLUME_STEPS = 110
MAX_VOLUME_ROUNDS = 4
MAX_TONE_STEPS = 16


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

    async def _zsc(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, zone: int, code: str
    ) -> None:
        """Send one zone specific command and validate its response."""
        await self._send(writer, f"zsc,{zone},{code}")
        response = await self._read_until_prefix(reader, ("rzsc",))
        if "FAIL" in response:
            raise NilesZR6Error(f"Command zsc,{zone},{code} failed: {response}")

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

    async def _poll_zone_retry(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        zone: int,
    ) -> ZoneStatus | None:
        status = await self._poll_zone(reader, writer, zone)
        if status is None:
            status = await self._poll_zone(reader, writer, zone)
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
                    status = await self._poll_zone_retry(reader, writer, zone)
                    if status is not None:
                        statuses[zone] = status
                    else:
                        _LOGGER.debug("No valid status for zone %s this cycle", zone)
                if not statuses:
                    raise NilesZR6Error("No zone status received from ZR-6")
                return statuses
            finally:
                await self._close(writer)

    async def async_zone_command(self, zone: int, code: str) -> ZoneStatus | None:
        """Send a zone specific command and verify the result in one session.

        Sends zsc,<zone>,<code>, then re-reads the status of that zone over
        the same connection so callers can update state immediately without a
        full poll cycle of all zones. Returns the fresh status, or None if
        the verification read failed (the command itself was still sent).
        """
        async with self._lock:
            reader, writer = await self._open()
            try:
                await self._flush_input(reader)
                await self._zsc(reader, writer, zone, code)
                return await self._poll_zone_retry(reader, writer, zone)
            finally:
                await self._close(writer)

    async def async_set_volume(self, zone: int, target: int) -> ZoneStatus | None:
        """Emulate absolute volume using up/down steps with status feedback.

        The ZR-6 has no absolute volume command. This performs a closed loop
        over a single connection: read the current level, send a batch of
        up/down steps sized to the remaining difference, re-read, and correct.
        The measured per-step delta is used to size subsequent batches.
        """
        target = max(0, min(100, int(target)))
        async with self._lock:
            reader, writer = await self._open()
            try:
                await self._flush_input(reader)
                status = await self._poll_zone_retry(reader, writer, zone)
                if status is None:
                    raise NilesZR6Error(f"Zone {zone}: no status; cannot set volume")
                step_size = 1  # measured on real hardware (1 point per step); refined after the first batch
                steps_sent = 0
                for _ in range(MAX_VOLUME_ROUNDS):
                    diff = target - status.volume
                    if abs(diff) <= 1:
                        break
                    code = CMD_VOL_UP if diff > 0 else CMD_VOL_DOWN
                    batch = max(1, min(abs(diff) // step_size, MAX_VOLUME_STEPS - steps_sent))
                    if batch <= 0:
                        break
                    before = status.volume
                    for _ in range(batch):
                        await self._zsc(reader, writer, zone, code)
                        steps_sent += 1
                    new_status = await self._poll_zone_retry(reader, writer, zone)
                    if new_status is None:
                        break
                    moved = abs(new_status.volume - before)
                    if moved == 0:
                        # At a limit, muted, or steps have no effect: stop.
                        status = new_status
                        break
                    step_size = max(1, round(moved / batch))
                    status = new_status
                    if steps_sent >= MAX_VOLUME_STEPS:
                        break
                return status
            finally:
                await self._close(writer)

    async def async_set_tone(self, zone: int, control: str, target: int) -> ZoneStatus | None:
        """Set bass or treble (-7..+7) using step commands with feedback.

        Steps one unit at a time and verifies movement via the zone status.
        Aborts if a step produces no change (protects against unsupported
        step codes on some firmware revisions).
        """
        if control not in ("bass", "treble"):
            raise ValueError(f"Unknown tone control: {control}")
        target = max(TONE_MIN, min(TONE_MAX, int(target)))
        up, down = (
            (CMD_BASS_UP, CMD_BASS_DOWN)
            if control == "bass"
            else (CMD_TREBLE_UP, CMD_TREBLE_DOWN)
        )
        async with self._lock:
            reader, writer = await self._open()
            try:
                await self._flush_input(reader)
                status = await self._poll_zone_retry(reader, writer, zone)
                if status is None:
                    raise NilesZR6Error(f"Zone {zone}: no status; cannot set {control}")
                for _ in range(MAX_TONE_STEPS):
                    current = getattr(status, control)
                    diff = target - current
                    if diff == 0:
                        break
                    await self._zsc(reader, writer, zone, up if diff > 0 else down)
                    new_status = await self._poll_zone_retry(reader, writer, zone)
                    if new_status is None:
                        break
                    if getattr(new_status, control) == current:
                        _LOGGER.warning(
                            "Zone %s: %s step had no effect (value stuck at %s); "
                            "aborting tone adjustment",
                            zone,
                            control,
                            current,
                        )
                        status = new_status
                        break
                    status = new_status
                return status
            finally:
                await self._close(writer)

    async def async_global_command(self, code: str) -> None:
        """Send a global (party mode) command: znt,<code>,h.

        Per the protocol document the hold/global function only supports
        source selection (01-06, turns all party-enabled zones on) and OFF
        (10, turns all zones off).
        """
        async with self._lock:
            reader, writer = await self._open()
            try:
                await self._flush_input(reader)
                await self._send(writer, f"znt,{code},h")
                response = await self._read_until_prefix(reader, ("rznt",))
                if "FAIL" in response:
                    raise NilesZR6Error(f"Command znt,{code},h failed: {response}")
            finally:
                await self._close(writer)

    async def async_tune(self, frequency: str) -> None:
        """Direct-tune the tuner: src,11,<frequency>.

        FM: 'XXX.X' (e.g. '102.7'); AM: 'XXXX' (e.g. '0560'). The tuner must
        be the selected source in the active zone.
        """
        async with self._lock:
            reader, writer = await self._open()
            try:
                await self._flush_input(reader)
                await self._send(writer, f"src,11,{frequency}")
                response = await self._read_until_prefix(reader, ("rsrc",))
                if "FAIL" in response:
                    raise NilesZR6Error(f"Command src,11,{frequency} failed: {response}")
            finally:
                await self._close(writer)

    async def async_send_raw(self, command: str) -> list[str]:
        """Send a raw protocol command and return all response lines.

        Intended for diagnostics/advanced use via the niles_zr6.send_command
        service.
        """
        async with self._lock:
            reader, writer = await self._open()
            try:
                await self._flush_input(reader)
                await self._send(writer, command)
                lines: list[str] = []
                for _ in range(10):
                    try:
                        line = await self._read_line(reader)
                    except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError):
                        break
                    if line:
                        _LOGGER.debug("RX: %s", line)
                        lines.append(line)
                return lines
            finally:
                await self._close(writer)
