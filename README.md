# SolarDelta (this is a beta version and a project in progress)

[![GitHub release (latest SemVer including pre-releases)](https://img.shields.io/github/v/release/KriVaTri/solardelta?include_prereleases)](https://github.com/KriVaTri/solardelta/releases)

Home Assistant custom integration that compares solar production with a device’s consumption and exposes four percentage sensors per entry (coverage + three persistent averages):
- Coverage percentage: how much of a device’s consumption is currently covered by solar.
- Rounding: values are shown with 1 decimal, except exact 0% or 100% (no decimals).
- Negative power values are treated as 0.
- Conditions: calculation only occurs when status device = the string provided by the user (not case-sensitive) and device power consumption > 0.
- This integration is mainly focused on EV charging consumption, but can be used for other devices. In case of EV charging, the status sensor would be the charging status of the EV or wallbox, this string is usually "charging". The reset sensor can be a sensor detecting if the vehicle is getting plugged in to the wallbox, this string is usually "on". These strings can be anything (they are not case sensitive) but must match the sensor or binary_sensor status string exactly. If no trigger sensor exist, the status sensor and its string can be used instead.

Configuration (via UI):
- Name: a custom label for this entry; the entity will be named “solardelta {name}”.
- Solar sensor: select your solar production sensor (sensor).
- Device sensor: select your device consumption sensor (sensor).
- Status entity: an entity (sensor or binary_sensor) representing the device status.
- Status match: a string to match against the status entity’s state (case-insensitive).
- Trigger entity: an entity (sensor or binary_sensor) to trigger on.
- Trigger match: a string to match against the trigger entity’s state (case-insensitive).
- Scan interval (seconds): 0 = disabled (push-only updates); >0 adds periodic recalculation at the given interval.

Behavior:
- Push updates: listens to changes of solar, device, status, and trigger entities.
- Optional polling: if scan interval > 0, it also recalculates on that schedule.
- If conditions fail, the sensor reports 0%.
- Units (W vs kW) are normalized automatically.

Average sensors (persistent):
- solardelta {name} avg session: time‑weighted average; holds when conditions drop; resets when the trigger sensor state changes from any known state to the string provided during configuration e.g. "on".
- solardelta {name} avg year: time‑weighted average; holds when conditions drop; auto‑resets on New Year (local time). Also resettable via service solardelta.reset_avg_year.
- solardelta {name} avg lifetime: time‑weighted average; holds when conditions drop; never resets. Resettable via service solardelta.reset_avg_lifetime.
- If an entry or the integration has been deleted, reinstalling the integration or creating an entry with the same name will restore its previous data.

Active duration attributes (on each average sensor):
- What it is: the total elapsed “active” time (in seconds and DD:HH:MM) that contributed to that sensor’s average.
- How it behaves: increases only while conditions are allowed (the same periods used to compute the average), and resets exactly when that average resets (session trigger, New Year, or the relevant reset service).
- What it is not: it’s not wall‑clock time since the sensor was created; periods when conditions aren’t met do not count.

Changing settings later:
- Use Configure on the integration to change sensors/strings and scan interval.
- The Name cannot be changed after initial setup. If you need a different name, delete the entry and create a new one or change its friendly name if you need to keep its stored data.

Installation:
- Through HACS: add a custom repository. (https://github.com/KriVaTri/solardelta)
- Or copy the `custom_components/solardelta` folder into your Home Assistant config.
- Restart Home Assistant.
- Settings → Devices & Services → “Add Integration” → SolarDelta.

License:
MIT
