from __future__ import annotations

import asyncio
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
        reset_entity: Optional[str] = None,
        reset_string: Optional[str] = None,
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
        self._reset_entity = reset_entity
        self._reset_string = reset_string

        self._periodic = periodic
        self._unsub: list[callable] = []

        # Seed initial data to avoid None
        self.data = {
            "coverage_pct": 0.0,
            "conditions_allowed": False,
            "status_ok": True,
            "reset_ok": True,
        }

    @property
    def reset_string(self) -> Optional[str]:
        """Return the configured reset string (single)."""
        return self._reset_string

    def _conditions_ok(self) -> tuple[bool, bool, bool]:
        """Return (allowed_by_status_only, status_ok, reset_ok).

        Rules:
        - If status_string == "none" (case-insensitive), ignore status entity; status_ok = True.
        - Otherwise, status_ok matches status_entity/state against status_string (if entity provided).
        - Reset sensor is observed (for session resets) but does NOT gate calculations.
        """
        # Handle "none" status string: ignore status checks entirely
        status_string_norm = _norm_str(self._status_string)
        none_status = status_string_norm == "none"

        if none_status:
            status_ok = True
        else:
            status_ok = True
            if self._status_entity:
                status_state = self.hass.states.get(self._status_entity)
                status_ok = _state_matches(status_state, [self._status_string] if self._status_string else [])

        reset_ok = True
        if self._reset_entity:
            reset_state = self.hass.states.get(self._reset_entity)
            resets: list[str] = [self._reset_string] if self._reset_string else []
            reset_ok = _state_matches(reset_state, resets)

        # If status is "none", allow by status unconditionally; else depend on status_ok
        allowed_by_status_only = True if none_status else status_ok
        return allowed_by_status_only, status_ok, reset_ok

    def _compute_now(self) -> dict[str, Any]:
        """Compute coverage from current states, honoring conditions:
        - If status_string == "none": only require device power > 0.
        - Else: status must match (if configured) AND device power > 0.
        """
        allowed_by_status, status_ok, reset_ok = self._conditions_ok()

        solar_state = self.hass.states.get(self._solar_entity)
        device_state = self.hass.states.get(self._device_entity)

        solar_w = _to_watts(solar_state)
        device_w = _to_watts(device_state)

        # Device sensor must be > 0 to allow calculations/accumulation
        device_positive = device_w is not None and device_w > 0.0

        allowed = bool(allowed_by_status and device_positive)

        if not allowed:
            pct: float | int = 0
        elif solar_w is None or device_w is None or device_w <= 0:
            # Redundant guard; kept for safety
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
            "reset_ok": reset_ok,
        }

    def _publish_now(self) -> None:
        """Compute and publish; always schedule on HA's event loop to avoid thread warnings."""
        payload = self._compute_now()
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is self.hass.loop:
            # Already in the HA loop
            self.async_set_updated_data(payload)
        else:
            # Schedule safely onto the HA loop
            self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, payload)

    async def async_config_entry_first_refresh(self) -> None:
        """Set up listeners and perform initial refresh."""
        # When periodic updates are configured (scan_interval > 0), do not subscribe to
        # state changes; rely on the DataUpdateCoordinator schedule only.
        # When scan_interval == 0, operate in event-driven mode and recompute on changes.
        # Keep reset_entity in watch so session average can observe changes and reset timely.
        watch = [self._solar_entity, self._device_entity, self._status_entity, self._reset_entity]
        watch = [e for e in watch if e]

        if not self._periodic and watch:
            def _on_change(event):
                # Any relevant state change triggers recompute (and notifies sensors)
                self._publish_now()

            unsub = async_track_state_change_event(self.hass, watch, _on_change)
            self._unsub.append(unsub)

        # Perform one initial refresh so sensors have values, and if periodic is set,
        # the coordinator will continue refreshing at the configured interval.
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
