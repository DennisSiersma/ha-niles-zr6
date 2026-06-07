"""Unit tests for the ZR-6 protocol parser (no Home Assistant required)."""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "niles_zr6"),
)

from protocol import CMD_OFF, CMD_SOURCE, CMD_VOL_UP, parse_usc  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
