from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PCT_MAX = 100.0  # for clamping to percentage upper bound


def _norm_str(val: str | None) -> str:
    return (val or "").strip().casefold()


def _state_matches(state: State | None, candidates: list[str]) -> bool:
    """Case-insensitive exact match of state.state to any candidate string."""
    if state is None:
        return False
    current = str(state.state).strip().casefold()
    if not candidates:
        return True
    return any(current == _norm_str(c) for c in candidates)


def _to_watts(st: State | None, *, allow_negative: bool = False) -> float | None:
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


def _clamp_pct(x: float) -> float:
    return max(0.0, min(x, PCT_MAX))


def _compute_unaware_pct(solar_w: float | None, device_w: float | None, allowed_base: bool) -> float:
    if not allowed_base or solar_w is None or device_w is None or device_w <= 0:
        return 0.0
    return _clamp_pct((solar_w / device_w) * 100.0)


def _compute_grid_pct(solar_w: float | None, grid_w: float | None, allowed_base: bool) -> float:
    if not allowed_base or solar_w is None or grid_w is None:
        return 0.0
    # Home load derived from balance: Solar - HomeLoad = Grid  => HomeLoad = Solar - Grid
    home_load = solar_w - grid_w
    if home_load <= 0:
        return PCT_MAX
    if solar_w <= 0:
        return 0.0
    return _clamp_pct((solar_w / home_load) * 100.0)


class SolarDeltaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        solar_entity: str,
        grid_entity: str | None = None,
        *,
        # Support separate import/export sensors (if your config_flow provides these)
        grid_separate: bool = False,
        grid_import_entity: str | None = None,
        grid_export_entity: str | None = None,
        device_entity: str = "",
        status_entity: str | None = None,
        status_string: str | None = None,
        reset_entity: str | None = None,
        reset_string: str | None = None,
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

        # Grid configuration: either a single net sensor or separate import/export
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
        self._unsub: list[Callable[[], None]] = []

        # Seed initial data to avoid None
        self.data = {
            "coverage_pct": 0.0,
            "coverage_grid_pct": 0.0,
            # Back-compat: legacy gating flag (kept equal to unaware gating)
            "conditions_allowed": False,
            # New: per-average gating
            "conditions_allowed_unaware": False,
            "conditions_allowed_grid": False,
            "status_ok": True,
            "reset_ok": True,
        }

    @property
    def reset_string(self) -> str | None:
        """Return the configured reset string (single)."""
        return self._reset_string

    def _conditions_ok(self) -> tuple[bool, bool, bool]:  # noqa: PLR0912
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

    def _compute_grid_net_watts(self) -> float | None:
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
        # Single net sensor path
        if not self._grid_entity:
            return None
        st = self.hass.states.get(self._grid_entity)
        return _to_watts(st, allow_negative=True)

    def _compute_now(self) -> dict[str, Any]:
        """Compute coverage from current states with per-average gating."""
        allowed_by_status, status_ok, reset_ok = self._conditions_ok()

        solar_state = self.hass.states.get(self._solar_entity)
        device_state = self.hass.states.get(self._device_entity)

        solar_w = _to_watts(solar_state)
        device_w = _to_watts(device_state)
        grid_w = self._compute_grid_net_watts()

        # Base allowing requires status ok (or none) and a positive device power
        device_positive = device_w is not None and device_w > 0.0
        allowed_base = bool(allowed_by_status and device_positive)

        # Per-average gating:
        # - Unaware requires Solar present (device already checked by allowed_base)
        # - Grid-aware requires Solar and Grid present (device already checked)
        conditions_allowed_unaware = bool(allowed_base and (solar_w is not None))
        conditions_allowed_grid = bool(allowed_base and (solar_w is not None) and (grid_w is not None))

        # Instantaneous coverage values (still computed for UI even if averages pause)
        pct = _compute_unaware_pct(solar_w, device_w, allowed_base)
        pct_grid = _compute_grid_pct(solar_w, grid_w, allowed_base)

        return {
            "solar_w": solar_w,
            "grid_w": grid_w,
            "device_w": device_w,
            "coverage_pct": float(pct),
            "coverage_grid_pct": float(pct_grid),
            # Back-compat: keep legacy flag; map to unaware gating
            "conditions_allowed": conditions_allowed_unaware,
            # New per-average flags
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
            # Already in the HA loop
            self.async_set_updated_data(payload)
        else:
            # Schedule safely onto the HA loop
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
                # Any relevant state change triggers recompute (and notifies sensors)
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

        # Perform one initial refresh so sensors have values, and if periodic is set,
        # the coordinator will continue refreshing at the configured interval.
        await super().async_config_entry_first_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Periodic refresh when scan_interval > 0."""
        return self._compute_now()

    async def async_shutdown(self) -> None:
        for unsub in self._unsub:
            with contextlib.suppress(Exception):
                unsub()
        self._unsub.clear()
