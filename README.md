
# SolarDelta (this is a beta version)

[![GitHub release (latest SemVer including pre-releases)](https://img.shields.io/github/v/release/KriVaTri/solardelta?include_prereleases)](https://github.com/KriVaTri/solardelta/releases)

Home Assistant custom integration that compares solar production with a device’s consumption and exposes four percentage sensors per entry (coverage + three persistent averages):
- Coverage percentage: how much of a device’s consumption is currently covered by solar.
- Rounding: values are shown with 1 decimal, except exact 0% or 100% (no decimals).
- Negative power values are treated as 0.
- Conditions: calculation only occurs when the device status equals the string provided by the user (or “none” to disable status checking) and device power > 0.
- This integration is mainly focused on solar coverage for EV charging, but can be used for other devices as well. For EV charging, the status sensor would typically be the charging status of the EV or the charger.

Configuration (via UI):
- Name: a custom label for this entry; the entity will be named “solardelta {name}”.
- Solar power sensor: select your solar production sensor (sensor).
- Device power sensor: select your device consumption sensor (sensor).
- Status entity: an entity (sensor or binary_sensor) representing the device status.
- Status match: a string to match against the status entity’s state (case-insensitive); “none” will disable this condition.
- Reset entity: an entity (sensor or binary_sensor) to trigger a session-average reset.
- Reset match: a string to match against the reset entity’s state (case-insensitive).
- Scan interval (seconds): 0 = disabled (event-driven updates only); > 0 adds periodic recalculation at the given interval.

Behavior:
- Push updates: listens to changes of the solar power, device power, device status, and reset entity.
- Optional polling: if scan interval > 0, it also recalculates on that schedule.
- If conditions aren’t met (status doesn’t match unless “none”, or device power ≤ 0), the coverage sensor reports 0%. Average sensors hold during these periods (no accumulation).
- Units (W vs kW) are normalized automatically.

Average sensors (persistent):
- solardelta {name} avg session: time‑weighted average; holds when conditions drop; resets when the reset entity’s state changes from any known non‑target to the configured reset match string. Also resettable via per‑entry service: solardelta.reset_avg_session_{entry_slug}.
- solardelta {name} avg year: time‑weighted average; holds when conditions drop; auto‑resets on New Year (local time). Also resettable via per‑entry service: solardelta.reset_avg_year_{entry_slug}.
- solardelta {name} avg lifetime: time‑weighted average; holds when conditions drop; never resets. Resettable via per‑entry service: solardelta.reset_avg_lifetime_{entry_slug}.
- If an entry or the integration has been deleted, reinstalling the integration or creating an entry with the same name will restore its previous data.

Active duration attributes (on each average sensor):
- What it is: the total elapsed “active” time (in seconds and DD:HH:MM) that contributed to that sensor’s average.
- How it behaves: increases only while conditions are allowed (the same periods used to compute the average), and resets exactly when that average resets (session reset, New Year, or the relevant reset service).
- What it is not: it’s not wall‑clock time since the sensor was created; periods when conditions aren’t met do not count.

Changing settings later:
- Use Configure on the integration to change sensors/strings and scan interval.
- The Name cannot be changed after initial setup. If you need a different name, delete the entry and create a new one or change its friendly name if you need to keep its stored data.

Installation:
- Through HACS: add a custom repository: [KriVaTri/solardelta](https://github.com/KriVaTri/solardelta)
- Or copy the `custom_components/solardelta` folder into your Home Assistant configuration directory.
- Restart Home Assistant.
- Settings → Devices & Services → “Add Integration” → SolarDelta.

License:
MIT
