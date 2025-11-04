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


def _to_watts(st: Optional[State], *, allow_negative: bool = False) -> Optional[float]:
    """Parse a power value; supports W and kW; negatives optional; non-numeric -> None."""
    if st is None:
        return None
    try:
        val = float(str(st.state))
    except (TypeError, ValueError):
        return None
    unit = str(st.attributes.get("unit_of_measurement", "")).strip().lower()
    if unit == "kw":
        val *= 1000.0
    if not allow_negative and val < 0:
        val = 0.0
    return val


class SolarDeltaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        solar_entity: str,
        grid_entity: Optional[str] = None,
        *,
        # Separate import/export mode (when provided by config)
        grid_separate: bool = False,
        grid_import_entity: Optional[str] = None,
        grid_export_entity: Optional[str] = None,
        device_entity: str = "",
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

        # Grid configuration (single net or separate)
        self._grid_entity = grid_entity
        self._grid_separate = bool(grid_separate)
        self._grid_import_entity = grid_import_entity
        self._grid_export_entity = grid_export_entity

        self._device_entity = device_entity
        self._status_entity = status_entity
        self._status_string = status_string
        self._reset_entity = reset_entity
        self._reset_string = reset_string

        self._periodic = periodic
        self._unsub: list[callable] = []

        # Initial payload
        self.data = {
            "coverage_pct": 0.0,
            "coverage_grid_pct": 0.0,
            # Legacy gate (mapped to unaware)
            "conditions_allowed": False,
            # New per-average gates
            "conditions_allowed_unaware": False,
            "conditions_allowed_grid": False,
            "status_ok": True,
            "reset_ok": True,
        }

    @property
    def reset_string(self) -> Optional[str]:
        return self._reset_string

    def _conditions_ok(self) -> tuple[bool, bool, bool]:
        """Return (allowed_by_status_only, status_ok, reset_ok)."""
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

        allowed_by_status_only = True if none_status else status_ok
        return allowed_by_status_only, status_ok, reset_ok

    def _compute_grid_net_watts(self) -> Optional[float]:
        """Return net grid power (+export, -import) or None."""
        if self._grid_separate:
            if not self._grid_import_entity or not self._grid_export_entity:
                return None
            st_imp = self.hass.states.get(self._grid_import_entity)
            st_exp = self.hass.states.get(self._grid_export_entity)
            imp_w = _to_watts(st_imp, allow_negative=False)
            exp_w = _to_watts(st_exp, allow_negative=False)
            if imp_w is None or exp_w is None:
                return None
            return exp_w - imp_w
        if not self._grid_entity:
            return None
        st = self.hass.states.get(self._grid_entity)
        return _to_watts(st, allow_negative=True)

    def _compute_now(self) -> dict[str, Any]:
        """Compute coverage with per-average gating."""
        allowed_by_status, status_ok, reset_ok = self._conditions_ok()

        solar_state = self.hass.states.get(self._solar_entity)
        device_state = self.hass.states.get(self._device_entity)

        solar_w = _to_watts(solar_state)
        device_w = _to_watts(device_state)
        grid_w = self._compute_grid_net_watts()

        # Base gate: status allowed AND device > 0
        device_positive = device_w is not None and device_w > 0.0
        allowed_base = bool(allowed_by_status and device_positive)

        # Per-average gates
        conditions_allowed_unaware = bool(allowed_base and (solar_w is not None))
        conditions_allowed_grid = bool(allowed_base and (solar_w is not None) and (grid_w is not None))

        # Grid-unaware instantaneous coverage
        if not allowed_base:
            pct: float | int = 0
        elif solar_w is None or device_w is None or device_w <= 0:
            pct = 0
        else:
            pct = (solar_w / device_w) * 100.0
            pct = 0.0 if pct < 0.0 else 100.0 if pct > 100.0 else pct

        # Grid-aware instantaneous coverage
        if not allowed_base:
            pct_grid: float | int = 0
        elif solar_w is None or (grid_w is None):
            pct_grid = 0
        else:
            home_load = solar_w - grid_w  # Solar − HomeLoad = Grid
            if home_load <= 0:
                pct_grid = 100
            elif solar_w <= 0:
                pct_grid = 0
            else:
                pct_grid = (solar_w / home_load) * 100.0
                pct_grid = 0.0 if pct_grid < 0.0 else 100.0 if pct_grid > 100.0 else pct_grid

        return {
            "solar_w": solar_w,
            "grid_w": grid_w,
            "device_w": device_w,
            "coverage_pct": float(pct),
            "coverage_grid_pct": float(pct_grid),
            # Legacy flag mapped to unaware
            "conditions_allowed": conditions_allowed_unaware,
            # Per-average flags
            "conditions_allowed_unaware": conditions_allowed_unaware,
            "conditions_allowed_grid": conditions_allowed_grid,
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
            self.async_set_updated_data(payload)
        else:
            self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, payload)

    async def async_config_entry_first_refresh(self) -> None:
        """Set up listeners and perform initial refresh."""
        # Event-driven for main sensors only when periodic is disabled
        watch_main = [
            self._solar_entity,
            self._grid_entity,
            getattr(self, "_grid_import_entity", None),
            getattr(self, "_grid_export_entity", None),
            self._device_entity,
            self._status_entity,
        ]
        watch_main = [e for e in watch_main if e]

        if not self._periodic and watch_main:
            def _on_change(event):
                # Any relevant state change triggers recompute
                self._publish_now()

            unsub = async_track_state_change_event(self.hass, watch_main, _on_change)
            self._unsub.append(unsub)

        # Always watch reset_entity to make session reset immediate, even when periodic
        if self._reset_entity:
            def _on_reset_change(event):
                # Push an immediate recompute so average sensors can detect the transition
                self._publish_now()

            unsub_reset = async_track_state_change_event(self.hass, [self._reset_entity], _on_reset_change)
            self._unsub.append(unsub_reset)

        # Initial refresh; if periodic is set, the coordinator will continue on schedule
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
