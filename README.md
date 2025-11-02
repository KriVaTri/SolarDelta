# SolarDelta (this is a beta version and a project in progress)

[![GitHub release (latest SemVer including pre-releases)](https://img.shields.io/github/v/release/KriVaTri/solardelta?include_prereleases)](https://github.com/KriVaTri/solardelta/releases)
[![Release date](https://img.shields.io/github/release-date/KriVaTri/solardelta?include_prereleases)](https://github.com/KriVaTri/solardelta/releases)

Home Assistant custom integration that compares solar production with a device’s consumption and exposes four percentage sensors per entry (coverage + three persistent averages):
- Coverage percentage: how much of a device’s consumption is currently covered by solar (solar / device * 100), clamped to 0–100%.
- Rounding: values are shown with 1 decimal, except exact 0% or 100% (no decimals).
- Negative power values are treated as 0.
- Conditions: calculation only occurs when both status and trigger entities match the configured strings.

Configuration (via UI):
- Name: a custom label for this entry; the entity will be named “solardelta <Name>”.
- Solar sensor: select your solar production sensor (sensor).
- Device sensor: select your device consumption sensor (sensor).
- Status entity: an entity (sensor or binary_sensor) representing the device status.
- Status match: a string to match against the status entity’s state (case-insensitive).
- Trigger entity: an entity (sensor or binary_sensor) to trigger on.
- Trigger match 1: required string to match against the trigger entity’s state (case-insensitive).
- Trigger match 2: optional second string to match.
- Scan interval (seconds): 0 = disabled (push-only updates); >0 adds periodic recalculation at the given interval.

Behavior:
- Push updates: listens to changes of solar, device, status, and trigger entities.
- Optional polling: if scan interval > 0, it also recalculates on that schedule.
- If conditions fail, the sensor reports 0%.
- Units (W vs kW) are normalized automatically.

Average sensors (persistent):
- solardelta <Name> avg session: time‑weighted average; holds when conditions drop; resets when the trigger goes to “on” from any known state.
- solardelta <Name> avg year: time‑weighted average; holds when conditions drop; auto‑resets on New Year (local time). Also resettable via service solardelta.reset_avg_year.
- solardelta <Name> avg lifetime: time‑weighted average; holds when conditions drop; never resets. Resettable via service solardelta.reset_avg_lifetime.

Changing settings later:
- Use Configure on the integration to change sensors/strings and scan interval.
- The Name cannot be changed after setup. If you need a different name, delete the entry and create a new one.

Branding:
- Integration tile/logo: add `icon.png` and `logo.png` in `custom_components/solardelta/` (256×256 PNGs). (yet to be done)
- Entity icons: percentage sensors use `mdi:percent`.

Installation:
- Copy the `custom_components/solardelta` folder into your Home Assistant config.
- Restart Home Assistant.
- Settings → Devices & Services → “Add Integration” → SolarDelta.

License:
MIT