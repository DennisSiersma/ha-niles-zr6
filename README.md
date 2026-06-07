# Niles ZR-6 MultiZone Receiver — Home Assistant integration

A custom Home Assistant integration for the **Niles ZR-6 MultiZone Receiver**, controlled over its RS-232 port via an **RS232-over-IP bridge** (raw TCP / telnet).

Each zone becomes a `media_player` entity with:

- Power on/off
- Source selection (6 sources)
- Volume up/down and volume level display (0–100%, read from the amp)
- Mute
- Bass/treble shown as state attributes
- State updates by polling the receiver

> **Note:** the ZR-6 protocol has **no absolute volume set** command — only volume up/down steps. The current volume *level* is read back from the receiver and shown on the entity, but dragging a volume slider is not supported.

## Hardware setup

Connect the ZR-6's 3.5 mm RS-232 jack (tip = TX, ring = RX, sleeve = GND) to an RS232-to-IP adapter configured as a raw TCP server:

| Setting | Value |
|---|---|
| Baud rate | 38,400 |
| Data bits | 8 |
| Stop bits | 1 |
| Parity | None |
| Flow control | None |

## Sharing the bridge with other controllers (e.g. Node-RED)

Most RS232-over-IP bridges accept **only one TCP client at a time**. This integration therefore deliberately uses a **connect → send → read → disconnect** pattern for every poll and command, instead of keeping a persistent socket open. This lets it coexist with other automation tools (such as a Node-RED flow) talking to the same bridge.

Caveat: if the *other* client holds a persistent connection, this integration cannot get through. Configure your other tools to also use short-lived connections.

## Installation (HACS)

1. In HACS, open **⋮ → Custom repositories**.
2. Add `https://github.com/DennisSiersma/ha-niles-zr6` with type **Integration**.
3. Install **Niles ZR-6 MultiZone Receiver** and restart Home Assistant.

Manual alternative: copy `custom_components/niles_zr6` into your `config/custom_components/` folder and restart.

## Configuration

1. **Settings → Devices & Services → Add Integration → Niles ZR-6 MultiZone Receiver**.
2. Enter the bridge **host** (e.g. `192.168.1.250`), **port** (e.g. `23`) and the **number of zones** in use (1–18; a single ZR-6 chassis has 6).
3. On the next page, name your zones (e.g. Toilet, Eetkamer, Speelkamer, Woonkamer) and the 6 sources.

Zone status is polled every 30 seconds, and refreshed immediately after every command.

## Protocol reference

From the official Niles *"ZR-6 MultiZone Receiver RS-232C Control Protocols"* document. All commands are ASCII, terminated with a carriage return.

| Command | Meaning | Response |
|---|---|---|
| `znc,4,<zone>` | Make `<zone>` the active control zone | `rznc,4,<zone>` |
| `znc,5` | Request status of the active zone | `usc,2,<zone>,<source>,<on/off>,<volume 0-100>,<mute>,<bass -7..7>,<treble -7..7>` |
| `zsc,<zone>,<code>` | Zone-specific command (see codes below) | `rzsc,<zone>,<code>,OK` |
| `znt,<code>,h` | Global (party-mode) command, all zones | `rznt,<code>,OK` |
| `src,11,<freq>` | Direct tune the tuner (e.g. `102.7` or `0560`) | `rsrc,11,OK` |
| `usc,1` | Unsolicited: receiver ready after boot | — |
| `r<type>,<code>,FAIL,<fcode>` | Command failure response | — |

Zone-specific command codes used by this integration:

| Code | Action |
|---|---|
| `01`–`06` | Select source 1–6 (also powers the zone on) |
| `10` | Zone off |
| `11` | Mute (toggle) |
| `12` | Volume up |
| `13` | Volume down |

The full document also defines transport codes (play/pause/etc.), digit keys, and bass/treble hex codes.

## Credits

- Protocol: Niles Audio, *ZR-6 MultiZone Receiver RS-232C Control Protocols* ([PDF](https://nilesaudio.com/sites/nilesaudio.com/files/_/techsupport/pdf/zr6_control_codes.pdf))
- Command behavior verified against a working Node-RED setup by Dennis Siersma.

## License

[MIT](LICENSE)
