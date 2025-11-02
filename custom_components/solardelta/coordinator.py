from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _norm_str(val: Optional[str]) -> str:
    return (val or "").strip().casefold()


def _state_matches(state: Optional[State], candidates: list[str]) -> bool:
    """Case-insensitive exact match of state.state to any candidate string."""
    if state is None:
        return False
    current = str(state.state).strip().casefold()
    if not candidates:
        return True
    for c in candidates:
        if current == _norm_str(c):
            return True
    return False


def _to_watts(st: Optional[State]) -> Optional[float]:
    """Parse a power value; supports W and kW; negatives -> 0; non-numeric -> None."""
    if st is None:
        return None
    try:
        val = float(str(st.state))
    except (TypeError, ValueError):
        return None
    unit = str(st.attributes.get("unit_of_measurement", "")).strip().lower()
    if unit == "kw":
        val *= 1000.0
    if val < 0:
        val = 0.0
    return val


class SolarDeltaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        solar_entity: str,
        device_entity: str,
        status_entity: Optional[str] = None,
        status_string: Optional[str] = None,
        trigger_entity: Optional[str] = None,
        trigger_string_1: Optional[str] = None,
        scan_interval_seconds: int = 0,
    ) -> None:
        periodic = bool(scan_interval_seconds and int(scan_interval_seconds) > 0)
        super().__init__(
            hass,
            logger=_LOGGER,
            name="solardelta coordinator",
            update_interval=(timedelta(seconds=int(scan_interval_seconds)) if periodic else None),
        )
        self._solar_entity = solar_entity
        self._device_entity = device_entity
        self._status_entity = status_entity
        self._status_string = status_string
        self._trigger_entity = trigger_entity
        self._trigger_string_1 = trigger_string_1

        self._periodic = periodic
        self._unsub: list[callable] = []

        # Seed initial data to avoid None
        self.data = {
            "coverage_pct": 0.0,
            "conditions_allowed": False,
            "status_ok": True,
            "trigger_ok": True,
        }

    @property
    def trigger_string(self) -> Optional[str]:
        """Return the configured trigger string (single)."""
        return self._trigger_string_1

    def _conditions_ok(self) -> tuple[bool, bool, bool]:
        """Return (allowed, status_ok, trigger_ok)."""
        status_ok = True
        if self._status_entity:
            status_state = self.hass.states.get(self._status_entity)
            status_ok = _state_matches(status_state, [self._status_string] if self._status_string else [])

        trigger_ok = True
        if self._trigger_entity:
            trigger_state = self.hass.states.get(self._trigger_entity)
            triggers: list[str] = [self._trigger_string_1] if self._trigger_string_1 else []
            trigger_ok = _state_matches(trigger_state, triggers)

        allowed = status_ok and trigger_ok
        return allowed, status_ok, trigger_ok

    def _compute_now(self) -> dict[str, Any]:
        """Compute coverage from current states, honoring conditions."""
        allowed, status_ok, trigger_ok = self._conditions_ok()

        solar_state = self.hass.states.get(self._solar_entity)
        device_state = self.hass.states.get(self._device_entity)

        solar_w = _to_watts(solar_state)
        device_w = _to_watts(device_state)

        if not allowed:
            pct: float | int = 0
        elif solar_w is None or device_w is None or device_w <= 0:
            pct = 0
        else:
            pct = (solar_w / device_w) * 100.0
            # clamp
            if pct < 0.0:
                pct = 0.0
            if pct > 100.0:
                pct = 100.0

        return {
            "solar_w": solar_w,
            "device_w": device_w,
            "coverage_pct": float(pct),
            "conditions_allowed": allowed,
            "status_ok": status_ok,
            "trigger_ok": trigger_ok,
        }

    def _publish_now(self) -> None:
        """Compute and publish immediately."""
        try:
            payload = self._compute_now()
            self.async_set_updated_data(payload)
        except Exception:
            _LOGGER.exception("SolarDelta compute failed")

    async def async_config_entry_first_refresh(self) -> None:
        """Set up listeners and publish initial data."""
        # Subscribe to relevant entities
        watch = [self._solar_entity, self._device_entity, self._status_entity, self._trigger_entity]
        watch = [e for e in watch if e]

        if watch:
            def _on_change(event):
                self._publish_now()

            unsub = async_track_state_change_event(self.hass, watch, _on_change)
            self._unsub.append(unsub)

        # Initial publish so sensors have values without waiting
        self._publish_now()

        # If periodic is configured, Coordinator will call _async_update_data on schedule
        await super().async_config_entry_first_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Periodic refresh when scan_interval > 0."""
        return self._compute_now()

    async def async_shutdown(self) -> None:
        for unsub in self._unsub:
            try:
                unsub()
            except Exception:
                pass
        self._unsub.clear()
