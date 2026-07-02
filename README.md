# Niles ZR-6 MultiZone Receiver — Home Assistant integration

A custom Home Assistant integration for the **Niles ZR-6 MultiZone Receiver**, controlled over its RS-232 port via an **RS232-over-IP bridge** (raw TCP / telnet).

Each zone becomes a `media_player` entity with:

- Power on/off
- Source selection (6 sources)
- **Absolute volume (slider)** — emulated with a closed loop of volume up/down steps and status feedback, since the ZR-6 protocol has no absolute volume command
- Volume up/down and mute
- Bass and treble as **number entities** per zone (-7..+7), plus as state attributes
- State updates by polling the receiver (interval configurable), with immediate per-zone verification after every command

Diagnostic entities: connection `binary_sensor` and last-response `sensor`. A diagnostics download is available on the config entry.

## Services

| Service | Description |
|---|---|
| `niles_zr6.all_zones_source` | Party mode: select source 1-6 in all party-enabled zones at once (`znt,<code>,h`) |
| `niles_zr6.all_zones_off` | Turn all zones off at once (`znt,10,h`) |
| `niles_zr6.tune` | Direct-tune the tuner (`src,11,<freq>`; FM `102.7`, AM `0560`) |
| `niles_zr6.send_command` | Send a raw protocol command and get the response lines back (diagnostics) |

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

Afterwards you can change the zone count, **poll interval**, and zone/source names via the entry's **Configure** button, and the bridge host/port via **⋯ → Reconfigure**.

Zone status is polled every 30 seconds by default (configurable 5–600 s). After every command the affected zone's status is verified over the same connection and updated immediately.

## Protocol reference

From the official Niles *"ZR-6 MultiZone Receiver RS-232C Control Protocols"* document. All commands are ASCII, terminated with a carriage return.

| Command | Meaning | Response |
|---|---|---|
| `znc,4,<zone>` | Make `<zone>` the active control zone | `rznc,4,<zone>` |
| `znc,5` | Request status of the active zone | `usc,2,<zone>,<source>,<on/off>,<volume 0-100>,<mute>,<bass -7..7>,<treble -7..7>` |
| `zsc,<zone>,<code>` | Zone-specific command (see codes below) | `rzsc,<zone>,<code>,OK` |
| `znt,<code>,h` | Global (party-mode) command, all party-enabled zones; only source select and off | `rznt,<code>,OK` |
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
| `128`/`129` | Bass up / down (hex `80`/`81` in the R-6L table) |
| `130`/`131` | Treble up / down (hex `82`/`83` in the R-6L table) |

The full document also defines transport codes (play/pause/etc.), digit keys, and tuner preset/scan codes.

## Development

Unit tests (no Home Assistant install required — includes a fake ZR-6 TCP server):

```bash
python -m pytest tests/ -v
```

CI runs [hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest/), [HACS validation](https://github.com/hacs/action) and the unit tests on every push and PR.

## Credits

- Protocol: Niles Audio, *ZR-6 MultiZone Receiver RS-232C Control Protocols* ([PDF](https://nilesaudio.com/sites/nilesaudio.com/files/_/techsupport/pdf/zr6_control_codes.pdf))
- Command behavior verified against a working Node-RED setup by Dennis Siersma.

## License

[MIT](LICENSE)
