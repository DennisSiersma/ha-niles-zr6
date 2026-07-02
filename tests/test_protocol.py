"""Unit tests for the ZR-6 protocol client (no Home Assistant required).

Includes a fake ZR-6 TCP server that speaks the documented protocol, so the
closed-loop volume/tone emulation and command verification are tested
end-to-end over real sockets.
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "niles_zr6"),
)

from protocol import (  # noqa: E402
    CMD_OFF,
    CMD_SOURCE,
    CMD_VOL_UP,
    NilesZR6Client,
    NilesZR6Error,
    parse_usc,
)


class TestParseUsc(unittest.TestCase):
    def test_example_from_protocol_doc(self):
        status = parse_usc("usc,2,2,3,1,14,0,0,0\r")
        self.assertIsNotNone(status)
        self.assertEqual(status.zone, 2)
        self.assertEqual(status.source, 3)
        self.assertTrue(status.power)
        self.assertEqual(status.volume, 14)
        self.assertFalse(status.muted)
        self.assertEqual(status.bass, 0)
        self.assertEqual(status.treble, 0)

    def test_zone_off_muted_negative_tone(self):
        status = parse_usc("usc,2,4,1,0,55,1,-3,7")
        self.assertEqual(status.zone, 4)
        self.assertFalse(status.power)
        self.assertEqual(status.volume, 55)
        self.assertTrue(status.muted)
        self.assertEqual(status.bass, -3)
        self.assertEqual(status.treble, 7)

    def test_ready_message_is_not_status(self):
        self.assertIsNone(parse_usc("usc,1"))

    def test_other_responses_ignored(self):
        self.assertIsNone(parse_usc("rznc,4,2"))
        self.assertIsNone(parse_usc("rzsc,3,01,OK"))
        self.assertIsNone(parse_usc(""))
        self.assertIsNone(parse_usc("usc,2,x,y,z,a,b,c,d"))

    def test_command_codes(self):
        self.assertEqual(CMD_SOURCE[3], "03")
        self.assertEqual(CMD_OFF, "10")
        self.assertEqual(CMD_VOL_UP, "12")


class FakeZone:
    def __init__(self):
        self.source = 1
        self.power = False
        self.volume = 20
        self.muted = False
        self.bass = 0
        self.treble = 0


class FakeZR6:
    """Minimal fake ZR-6 behind a TCP socket, per the protocol document."""

    def __init__(self, volume_step=2):
        self.zones = {z: FakeZone() for z in range(1, 7)}
        self.active_zone = 1
        self.volume_step = volume_step
        self.commands = []
        self.tone_supported = True
        self._server = None
        self.port = None

    async def start(self):
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        self._server.close()
        await self._server.wait_closed()

    def _status_line(self):
        z = self.zones[self.active_zone]
        return (
            f"usc,2,{self.active_zone},{z.source},{int(z.power)},"
            f"{z.volume},{int(z.muted)},{z.bass},{z.treble}\r"
        )

    def _apply_zsc(self, zone, code):
        z = self.zones[zone]
        if code in ("01", "02", "03", "04", "05", "06"):
            z.source = int(code)
            z.power = True
        elif code == "10":
            z.power = False
        elif code == "11":
            z.muted = not z.muted
        elif code == "12":
            z.volume = min(100, z.volume + self.volume_step)
        elif code == "13":
            z.volume = max(0, z.volume - self.volume_step)
        elif code == "128" and self.tone_supported:
            z.bass = min(7, z.bass + 1)
        elif code == "129" and self.tone_supported:
            z.bass = max(-7, z.bass - 1)
        elif code == "130" and self.tone_supported:
            z.treble = min(7, z.treble + 1)
        elif code == "131" and self.tone_supported:
            z.treble = max(-7, z.treble - 1)

    async def _handle(self, reader, writer):
        try:
            while True:
                try:
                    data = await reader.readuntil(b"\r")
                except (asyncio.IncompleteReadError, ConnectionResetError):
                    break
                cmd = data.decode("ascii").strip()
                if not cmd:
                    continue
                self.commands.append(cmd)
                parts = cmd.split(",")
                reply = ""
                if parts[0] == "znc" and parts[1] == "4":
                    self.active_zone = int(parts[2])
                    reply = f"rznc,4,{self.active_zone}\r"
                elif parts[0] == "znc" and parts[1] == "5":
                    reply = self._status_line()
                elif parts[0] == "zsc":
                    zone, code = int(parts[1]), parts[2]
                    self._apply_zsc(zone, code)
                    reply = f"rzsc,{zone},{code},OK\r"
                elif parts[0] == "znt":
                    code = parts[1]
                    if code not in ("01", "02", "03", "04", "05", "06", "10"):
                        reply = f"rznt,{code},FAIL,2\r"
                    else:
                        for z in self.zones.values():
                            if code == "10":
                                z.power = False
                            else:
                                z.source = int(code)
                                z.power = True
                        reply = f"rznt,{code},OK\r"
                elif parts[0] == "src" and parts[1] == "11":
                    reply = "rsrc,11,OK\r"
                else:
                    reply = f"r{parts[0]},{parts[1]},FAIL,2\r"
                writer.write(reply.encode("ascii"))
                await writer.drain()
        finally:
            writer.close()


class FakeServerTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = FakeZR6()
        await self.server.start()
        self.client = NilesZR6Client("127.0.0.1", self.server.port)

    async def asyncTearDown(self):
        await self.server.stop()


class TestStatusPolling(FakeServerTestCase):
    async def test_get_status_all_zones(self):
        self.server.zones[2].source = 3
        self.server.zones[2].power = True
        self.server.zones[2].volume = 42
        statuses = await self.client.async_get_status([1, 2, 3, 4])
        self.assertEqual(set(statuses), {1, 2, 3, 4})
        self.assertEqual(statuses[2].source, 3)
        self.assertTrue(statuses[2].power)
        self.assertEqual(statuses[2].volume, 42)

    async def test_commands_use_bare_cr_terminator(self):
        await self.client.async_get_status([1])
        # The fake server splits on \r; a trailing \n would show up as an
        # empty command or corrupt the next one. Verify clean commands.
        for cmd in self.server.commands:
            self.assertFalse(cmd.startswith("\n"))
            self.assertNotIn("\n", cmd)


class TestZoneCommand(FakeServerTestCase):
    async def test_command_returns_verified_status(self):
        status = await self.client.async_zone_command(3, CMD_SOURCE[4])
        self.assertIsNotNone(status)
        self.assertEqual(status.zone, 3)
        self.assertEqual(status.source, 4)
        self.assertTrue(status.power)
        self.assertEqual(self.server.zones[3].source, 4)

    async def test_off_command(self):
        self.server.zones[2].power = True
        status = await self.client.async_zone_command(2, CMD_OFF)
        self.assertIsNotNone(status)
        self.assertFalse(status.power)


class TestVolumeEmulation(FakeServerTestCase):
    async def test_volume_up_to_target(self):
        self.server.zones[1].volume = 20
        status = await self.client.async_set_volume(1, 60)
        self.assertIsNotNone(status)
        self.assertAlmostEqual(status.volume, 60, delta=1)

    async def test_volume_down_to_target(self):
        self.server.zones[1].volume = 80
        status = await self.client.async_set_volume(1, 30)
        self.assertAlmostEqual(status.volume, 30, delta=1)

    async def test_volume_with_step_size_one(self):
        self.server.volume_step = 1
        self.server.zones[1].volume = 10
        status = await self.client.async_set_volume(1, 25)
        self.assertAlmostEqual(status.volume, 25, delta=1)

    async def test_volume_with_large_step(self):
        self.server.volume_step = 5
        self.server.zones[1].volume = 0
        status = await self.client.async_set_volume(1, 50)
        self.assertAlmostEqual(status.volume, 50, delta=5)

    async def test_volume_already_at_target(self):
        self.server.zones[1].volume = 40
        status = await self.client.async_set_volume(1, 40)
        self.assertEqual(status.volume, 40)
        # No volume steps should have been sent.
        steps = [c for c in self.server.commands if c.startswith("zsc,1,12")]
        self.assertEqual(steps, [])

    async def test_volume_clamped_at_limit(self):
        self.server.zones[1].volume = 98
        status = await self.client.async_set_volume(1, 150)
        self.assertEqual(status.volume, 100)


class TestToneEmulation(FakeServerTestCase):
    async def test_bass_up(self):
        status = await self.client.async_set_tone(1, "bass", 4)
        self.assertEqual(status.bass, 4)

    async def test_treble_down(self):
        self.server.zones[2].treble = 3
        status = await self.client.async_set_tone(2, "treble", -5)
        self.assertEqual(status.treble, -5)

    async def test_tone_unsupported_aborts_safely(self):
        self.server.tone_supported = False
        status = await self.client.async_set_tone(1, "bass", 4)
        # Must not loop forever; value stays put.
        self.assertEqual(status.bass, 0)
        steps = [c for c in self.server.commands if c == "zsc,1,128"]
        self.assertEqual(len(steps), 1)

    async def test_invalid_control_rejected(self):
        with self.assertRaises(ValueError):
            await self.client.async_set_tone(1, "loudness", 1)


class TestGlobalAndRaw(FakeServerTestCase):
    async def test_global_source(self):
        await self.client.async_global_command(CMD_SOURCE[3])
        for zone in self.server.zones.values():
            self.assertEqual(zone.source, 3)
            self.assertTrue(zone.power)

    async def test_global_off(self):
        for zone in self.server.zones.values():
            zone.power = True
        await self.client.async_global_command(CMD_OFF)
        for zone in self.server.zones.values():
            self.assertFalse(zone.power)

    async def test_tune(self):
        await self.client.async_tune("102.7")
        self.assertIn("src,11,102.7", self.server.commands)

    async def test_send_raw_returns_lines(self):
        lines = await self.client.async_send_raw("znc,5")
        self.assertTrue(any(line.startswith("usc,2") for line in lines))

    async def test_failed_command_raises(self):
        with self.assertRaises(NilesZR6Error):
            await self.client.async_global_command("99")


class TestConnectionErrors(unittest.IsolatedAsyncioTestCase):
    async def test_connect_refused_raises(self):
        client = NilesZR6Client("127.0.0.1", 1)  # nothing listens here
        with self.assertRaises(NilesZR6Error):
            await client.async_get_status([1])


if __name__ == "__main__":
    unittest.main()
