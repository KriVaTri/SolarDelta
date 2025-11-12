# SolarDelta

[![GitHub release (latest SemVer including pre-releases)](https://img.shields.io/github/v/release/KriVaTri/solardelta?include_prereleases)](https://github.com/KriVaTri/solardelta/releases)

Home Assistant custom integration that compares solar production with a device’s consumption and exposes percentage sensors per entry.

Highlights:
- Grid‑unaware coverage sensors (does not take into account other loads): use Solar and Device power only.
- Grid‑aware coverage sensors (takes into account other loads): additionally incorporate a Grid power sensor.
- Flexible grid inputs:
  - Single net grid power sensor (positive = export, negative = import), or
  - Separate positive‑only sensors for Import and Export (net = Export − Import; negatives are clamped to 0).
- Three persistent averages (session, year, lifetime) for both grid‑unaware and grid‑aware coverage.
- Per‑average gating: averages pause when required inputs are missing (unknown/unavailable).
  - Grid‑unaware requires Solar to be available.
  - Grid‑aware requires both Solar and Grid to be available (Grid = net or Import+Export).
  - Both also require Device power > 0 and status allowed.
- Immediate session reset: reacts instantly to Reset entity changes, even when a scan interval is configured.
- Rounding: values are shown with 1 decimal, except exact 0% or 100% (no decimals).
- Units (W vs kW) are normalized automatically.
- Negative values:
  - Solar/Device: negative readings are treated as 0.
  - Grid single sensor: negatives are allowed (import), positives allowed (export).
  - Grid separate sensors: both Import/Export are clamped to a minimum of 0, then net is Export − Import.

Use cases:
- Designed for solar coverage tracking (e.g., EV charging), but can be used for any device with measurable power draw.

## Table of contents

- [Highlights](#highlights)
- [Use cases](#use-cases)
- [Sensors created per entry](#sensors-created-per-entry)
- [Configuration (via UI)](#configuration-via-ui)
- [Behavior](#behavior)
  - [Grid semantics](#grid-semantics)
  - [Unknown/unavailable handling](#unknownunavailable-handling)
- [Average sensors (persistent)](#average-sensors-persistent)
  - [Active duration attributes (on each average sensor)](#active-duration-attributes-on-each-average-sensor)
- [Services](#services)
- [Changing settings later](#changing-settings-later)
- [Installation](#installation)
- [License](#license)

---

## Sensors created per entry

Grid‑unaware (Solar + Device):
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
- The two “coverage” sensors are non‑persistent (instant values).
- The six “avg …” sensors are persistent across restarts and updates.

## Configuration (via UI)

Two‑step setup flow:

Step 1
- Name: a custom label; entities will be named “solardelta {name} …”.
- Use separate grid import/export sensors: checkbox
  - Off (default): you will select one net Grid power sensor in Step 2.
  - On: you will select two sensors (Import and Export) in Step 2.

Step 2 (fields shown depend on the checkbox)
- Solar power sensor: select your solar production sensor (sensor).
- If “separate grid sensors” is Off:
  - Grid power sensor: net grid, Positive = export, Negative = import (sensor).
- If “separate grid sensors” is On:
  - Grid import power sensor: positive‑only import (sensor).
  - Grid export power sensor: positive‑only export (sensor).
- Device power sensor: select your device’s consumption sensor (sensor).
- Status entity: an entity (sensor or binary_sensor) representing the device status.
- Status match: a string to match against the status entity’s state (case‑insensitive); “none” disables status checking.
- Reset entity: an entity (sensor or binary_sensor) that triggers a session‑average reset.
- Reset match: a string to match against the reset entity’s state (case‑insensitive).
- Scan interval (seconds): 0 = disabled (event‑driven only); > 0 adds periodic recalculation at the given interval.

Validation:
- If separate grid sensors are enabled, both Import and Export sensors are required.
- If disabled, the single net Grid sensor is required.

## Behavior

- Push updates: listens to changes of Solar, Grid (net or separate), Device, Status, and Reset entities.
- Optional polling: if scan interval > 0, it also recalculates on that schedule.
- Session reset detection is immediate on Reset entity state changes, regardless of scan interval.

### Grid semantics

- Single net Grid sensor: positive = export (sending to grid), negative = import (taking from grid).
- Separate sensors: the integration computes net grid internally as Export − Import (both inputs expected to be positive‑only, negatives are clamped to 0).
- Grid‑unaware coverage uses only Solar and Device.
- Grid‑aware coverage uses Solar and inferred home load from the power balance: Solar − HomeLoad = Grid ⇒ HomeLoad = Solar − Grid.

### Unknown/unavailable handling

- Unknown/unavailable readings are treated as missing (None), not as zero.
- Instantaneous coverage sensors show 0% when inputs are missing.
- Averages pause according to per‑average gating:
  - Grid‑unaware averages pause if Solar is missing.
  - Grid‑aware averages pause if Solar or Grid (net or either Import/Export) is missing.
  - Both require Device > 0 and status allowed; otherwise they pause.

## Average sensors (persistent)

- solardelta {name} avg session:
  - Time‑weighted average; holds (pauses) when gating conditions drop.
  - Resets when the Reset entity’s state transitions from any known non‑target to the configured Reset match. Detection is immediate.
- solardelta {name} avg year:
  - Time‑weighted average; holds (pauses) when gating conditions drop.
  - Auto‑resets at the start of a new year (local time).
- solardelta {name} avg lifetime:
  - Time‑weighted average; holds (pauses) when gating conditions drop.
  - Never resets automatically.

Grid‑aware averages behave the same way but compute from the grid‑aware coverage and pause if Grid is missing.

Persistence details:
- Each average stores accumulated coverage×time, active time, and last timestamp in Home Assistant’s storage.
- Persistence keys are derived from the entry’s display name; renaming the entry starts fresh under a new key.

### Active duration attributes (on each average sensor)

- active_seconds: the total elapsed “active” seconds contributing to the average.
- active_time: human‑readable format (DD:HH:MM) of the same duration.
- Only increases while gating conditions are allowed and resets with the corresponding average reset.

## Services

Per‑entry dynamic services are registered when each entry loads. Replace {entry_slug} with the slugified entry name (lowercase):

- solardelta.reset_avg_session_{entry_slug}
- solardelta.reset_avg_year_{entry_slug}
- solardelta.reset_avg_lifetime_{entry_slug}
- solardelta.reset_avg_session_grid_{entry_slug}
- solardelta.reset_avg_year_grid_{entry_slug}
- solardelta.reset_avg_lifetime_grid_{entry_slug}
- solardelta.reset_all_averages_{entry_slug}  (resets all six averages above)

Notes:
- These dynamic services don’t show input fields in the UI. Call them with no data.
- “Reset all” resets grid‑unaware and grid‑aware averages together.
- Warning: The only way to restore data after a reset is to restore from a Home Assistant backup/snapshot taken before the reset.

## Changing settings later

- Use “Configure” on the integration to change sensors/strings, grid mode (single vs separate), and the scan interval.
- The Name cannot be changed after initial setup. If you need a different name, delete the entry and create a new one (or adjust friendly names if you want to keep stored data).

## Installation

- Through HACS: add a custom repository: [KriVaTri/solardelta](https://github.com/KriVaTri/solardelta)
- Or copy the `custom_components/solardelta` folder into your Home Assistant configuration directory.
- Restart Home Assistant.
- Settings → Devices & Services → “Add Integration” → SolarDelta.

## License

MIT
