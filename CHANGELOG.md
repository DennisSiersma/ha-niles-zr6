# Changelog

## 1.1.0 (2026-07-02)

### Added
- **Absolute volume** (`VOLUME_SET`): the volume slider now works. Since the
  ZR-6 has no absolute volume command, the level is set with a closed loop of
  volume up/down steps over a single connection, with status feedback and a
  measured per-step size (safety caps: max 60 steps / 4 correction rounds).
- **Bass and treble number entities** per zone (-7..+7), set via step codes
  (decimal 128/129/130/131 from the protocol document's hex table 80-83) with
  status verification. Adjustment aborts safely if the amp ignores the codes.
- **Services**:
  - `niles_zr6.all_zones_source` — party mode: select a source in all
    party-enabled zones at once (`znt,<code>,h`).
  - `niles_zr6.all_zones_off` — all zones off (`znt,10,h`).
  - `niles_zr6.tune` — direct-tune the tuner (`src,11,<freq>`).
  - `niles_zr6.send_command` — raw protocol command with response
    (returns response lines; for diagnostics).
- **Configurable poll interval** (5-600 s) in the options flow.
- **Reconfigure flow** for the bridge host/port (Settings → ⋯ → Reconfigure).
- **Diagnostics download** for the config entry (zone status, options,
  update health).
- Dutch translations for the new options/services.
- CI: GitHub Actions with hassfest, HACS validation and unit tests.

### Changed
- Commands now **verify in the same TCP session**: after `zsc` the affected
  zone's status is read back and merged immediately, instead of scheduling a
  full poll of all zones. Less bridge traffic, faster UI feedback.
- Command terminator fixed to a bare `\r` (carriage return) per the protocol
  document (was `\r\n`).

### Notes
- The global (`znt`) commands only affect zones with party mode enabled on
  the amp, per the Niles protocol document.
- Bass/treble step codes come from the protocol document's R-6L hex-code
  table; they are verified against zone status on every step and the
  integration stops if they have no effect on your firmware.

## 1.0.4

- Fix zone status flip-flop: flush stale input, validate `usc` reply zone
  against the requested zone, retry on mismatch, keep last known state on
  discarded replies.

## 1.0.3

- Options flow (zone count + zone/source names reconfigurable), stale zone
  entity cleanup.

## 1.0.2

- Diagnostic entities: connection binary_sensor, last-response timestamp
  sensor.

## 1.0.1

- Use `has_entity_name` for deterministic entity IDs
  (`media_player.niles_zr_6_<zone>`).

## 1.0.0

- Initial release: config flow, media_player per zone, RS232-over-IP.
