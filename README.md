
# SolarDelta (beta)

[![GitHub release (latest SemVer including pre-releases)](https://img.shields.io/github/v/release/KriVaTri/solardelta?include_prereleases)](https://github.com/KriVaTri/solardelta/releases)

Home Assistant custom integration that compares solar production with a device’s consumption and exposes percentage sensors per entry.

Highlights:
- Grid‑unaware coverage sensors: use Solar and Device power only.
- Grid‑aware coverage sensors: additionally incorporate a Grid power sensor (supports negative values for import and positive for export).
- Three persistent averages (session, year, lifetime) for both grid‑unaware and grid‑aware coverage.
- Rounding: values are shown with 1 decimal, except exact 0% or 100% (no decimals).
- Units (W vs kW) are normalized automatically.
- Negative values:
  - Solar/device inputs: negative readings are treated as 0.
  - Grid input: negatives are allowed (import), positives allowed (export).

Use cases:
- Designed for solar coverage tracking (e.g., EV charging), but it can be used for any device with a measurable power draw.

## Sensors created per entry

Grid‑unaware (based on Solar and Device):
- solardelta {name} coverage
- solardelta {name} avg session
- solardelta {name} avg year
- solardelta {name} avg lifetime

Grid‑aware (Solar + Device + Grid):
- solardelta {name} coverage grid
- solardelta {name} avg session grid
- solardelta {name} avg year grid
- solardelta {name} avg lifetime grid

Notes:
- The two “coverage” sensors are non-persistent.
- The six “avg …” sensors are persistent across restarts, updates, etc.

## Configuration (via UI)

- Name: a custom label for this entry; entities will be named “solardelta {name} …”.
- Solar power sensor: select your solar production sensor (sensor).
- Grid power sensor: select your net grid sensor (sensor). Negative = import, positive = export.
- Device power sensor: select your device’s consumption sensor (sensor).
- Status entity: an entity (sensor or binary_sensor) representing the device status.
- Status match: a string to match against the status entity’s state (case-insensitive); “none” disables status checking.
- Reset entity: an entity (sensor or binary_sensor) that triggers a session-average reset.
- Reset match: a string to match against the reset entity’s state (case-insensitive).
- Scan interval (seconds): 0 = disabled (event-driven updates only); > 0 adds periodic recalculation at the given interval.

## Behavior

- Push updates: listens to changes of Solar, Grid, Device, Status, and Reset entities.
- Optional polling: if scan interval > 0, it also recalculates on that schedule.
- Conditions:
  - If Status match is “none”, status is ignored.
  - Device power must be > 0 for coverage calculations and for averages to accumulate time.
  - If conditions aren’t met, the coverage sensors report 0%. Average sensors hold (no accumulation) during these periods.

## Average sensors (persistent)

- solardelta {name} avg session:
  - Time‑weighted average; holds when conditions drop.
  - Resets when the Reset entity’s state transitions from any known non‑target to the configured Reset match.
- solardelta {name} avg year:
  - Time‑weighted average; holds when conditions drop.
  - Auto‑resets at the start of a new year (local time).
- solardelta {name} avg lifetime:
  - Time‑weighted average; holds when conditions drop.
  - Never resets automatically.

Grid‑aware average sensors behave the same way but compute from the grid‑aware coverage.

Persistence details:
- Each average stores accumulated coverage*time, active time, and last timestamp in Home Assistant’s storage.
- Persistence keys are derived from the entry’s display name; renaming the entry starts fresh under a new key.

### Active duration attributes (on each average sensor)

- active_seconds: the total elapsed “active” seconds contributing to the average.
- active_time: human-readable format (DD:HH:MM) of the same duration.
- Only increases while conditions are allowed and resets with the corresponding average reset.

## Services

Per-entry dynamic services are registered when each entry loads. Replace {entry_slug} with the slugified entry name (lowercase):

- solardelta.reset_avg_session_{entry_slug}
- solardelta.reset_avg_year_{entry_slug}
- solardelta.reset_avg_lifetime_{entry_slug}
- solardelta.reset_avg_session_grid_{entry_slug}
- solardelta.reset_avg_year_grid_{entry_slug}
- solardelta.reset_avg_lifetime_grid_{entry_slug}
- solardelta.reset_all_averages_{entry_slug}  (resets all six averages above)

Notes:
- These dynamic services don’t show input fields in the UI. Call them with no data.
- “Reset all” is a convenience service that resets grid‑unaware and grid‑aware averages together.
- Warning, the only way to restore data after reset is to restore from a Home Assistant backup/snapshot taken before the reset.

## Changing settings later

- Use “Configure” on the integration to change sensors/strings and the scan interval.
- The Name cannot be changed after initial setup. If you need a different name, delete the entry and create a new one (or adjust friendly names if you want to keep stored data).

## Installation

- Through HACS: add a custom repository: [KriVaTri/solardelta](https://github.com/KriVaTri/solardelta)
- Or copy the `custom_components/solardelta` folder into your Home Assistant configuration directory.
- Restart Home Assistant.
- Settings → Devices & Services → “Add Integration” → SolarDelta.

## License

MIT
- Use Configure on the integration to change sensors/strings and scan interval.
- The Name cannot be changed after initial setup. If you need a different name, delete the entry and create a new one or change its friendly name if you need to keep its stored data.

Installation:
- Through HACS: add a custom repository: [KriVaTri/solardelta](https://github.com/KriVaTri/solardelta)
- Or copy the `custom_components/solardelta` folder into your Home Assistant configuration directory.
- Restart Home Assistant.
- Settings → Devices & Services → “Add Integration” → SolarDelta.

License:
MIT
