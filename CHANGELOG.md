# Changelog

## 1.3.0 (2026-07-03)

### Added
- **Adaptive polling**: after any command the integration polls every 5 s for
  one minute, then falls back to the configured interval. Snappy dashboards
  during interaction without a permanently higher poll load.
- **Linked zones option** (options flow): tell the integration which zones
  form the amp's Zone Linking group. Power/source commands then verify only
  the relevant zones (the group for linked zones, just the zone itself for
  independent ones) instead of all zones — less bridge traffic and faster
  commands. Without configuration all zones are verified (safe default).

### Changed
- Modernized to the ``entry.runtime_data`` pattern (replaces ``hass.data``).
- CI: added ruff lint job.

## 1.2.1 (2026-07-03)

### Fixed
- **Exclusive mode: connection leak on failed setup.** When the first refresh
  failed (e.g. the bridge briefly held the previous connection), the
  persistent connection was never closed, wedging the single-client bridge
  for every subsequent retry. Setup failures and entry unload now always
  disconnect the client.

## 1.2.0 (2026-07-03)

### Added
- **Exclusive connection mode**: optional persistent TCP connection to the
  RS232 bridge (options flow: `connection_mode` = `shared`/`exclusive`).
  In exclusive mode the integration keeps one connection open with automatic
  reconnect when the bridge drops it — much lower per-command latency. Use
  shared (default) when other tools (e.g. Node-RED) share the bridge.
- README: documented the ZR-6 **Zone Linking** behavior discovered on real
  hardware, and the new connection mode.

### Notes
- Tests: 31 total, including persistent-mode reuse/reconnect scenarios
  against the fake ZR-6 TCP server.

## 1.1.1 (2026-07-03)

### Fixed
- **Zone Linking support**: power and source commands are applied by the amp
  to all zones in a configured Zone Linking group at once. The integration
  now re-reads **all** configured zones in the same TCP session after every
  power/source command (volume/mute/tone still verify only their own zone,
  as those remain independent per the ZR-6 manual). Previously the linked
  partner zones showed a stale state until the next poll (up to 30 s).
- `async_zone_command` now returns a dict of verified zone statuses;
  coordinator gained `apply_statuses` for multi-zone merges.

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
