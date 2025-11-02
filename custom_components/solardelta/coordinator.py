from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional, Iterable
import logging

from homeassistant.core import HomeAssistant, callback, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)


def _to_watts(state: Optional[State]) -> Optional[float]:
    """Convert a power sensor state to watts, handling W and kW; negatives become 0."""
    if state is None:
        return None
    if state.state in ("unknown", "unavailable", None):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        return None

    unit = (state.attributes.get("unit_of_measurement") or "").strip().lower()
    if unit in ("kw", "kilowatt", "kilowatts"):
        value *= 1000.0
    elif unit in ("w", "watt", "watts", ""):
        pass  # treat as W
    else:
        _LOGGER.debug(
            "Unexpected unit for %s: %s (treating as W)",
            state.entity_id,
            state.attributes.get("unit_of_measurement"),
        )
    # Treat negative as 0
    if value < 0:
        value = 0.0
    return value


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _state_matches(state: Optional[State], targets: Iterable[str]) -> bool:
    """Case-insensitive match of state against any target string.
    Empty targets list means 'no condition', which returns True.
    """
    targets_n = [_norm(t) for t in targets if t is not None and str(t) != ""]
    if not targets_n:
        return True
    if state is None:
        return False
    current = _norm(state.state)
    return current in targets_n


def _round_coverage(value: float) -> float | int:
    """Round to 1 decimal, except exact 0 or 100 shown without decimals."""
    # Clamp first
    if value < 0.0:
        value = 0.0
    if value > 100.0:
        value = 100.0

    if value == 0.0:
        return 0
    if value == 100.0:
        return 100
    # epsilon to reduce float artifacts
    v = round(value + 1e-9, 1)
    if v <= 0.0:
        return 0
    if v >= 100.0:
        return 100
    return v


class SolarDeltaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that computes a single solar coverage percentage.

    Modes:
    - scan_interval == 0: push-only (subscribe to entity changes; immediate updates)
    - scan_interval > 0: poll-only (scheduled refresh; no immediate push on changes)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        solar_entity: str,
        device_entity: str,
        status_entity: Optional[str] = None,
        status_string: Optional[str] = None,
        trigger_entity: Optional[str] = None,
        trigger_string_1: Optional[str] = None,
        trigger_string_2: Optional[str] = None,
        trigger_block: Optional[str] = None,  # NEW: comma-separated blocked values
        scan_interval_seconds: int = 0,
    ) -> None:
        periodic = scan_interval_seconds and scan_interval_seconds > 0
        super().__init__(
            hass,
            logger=_LOGGER,
            name="solardelta coordinator",
            update_interval=(timedelta(seconds=scan_interval_seconds) if periodic else None),
        )
        self._solar_entity = solar_entity
        self._device_entity = device_entity
        self._status_entity = status_entity
        self._status_string = status_string
        self._trigger_entity = trigger_entity
        self._trigger_string_1 = trigger_string_1
        self._trigger_string_2 = trigger_string_2
        self._trigger_block = trigger_block  # NEW (raw string)
        self._periodic = bool(periodic)
        self._unsub: list[callable] = []

    def _conditions_ok(self) -> tuple[bool, bool, bool]:
        """Return (allowed, status_ok, trigger_ok) based on configured conditions."""
        # Status check: one string
        status_ok = True
        if self._status_entity:
            status_state = self.hass.states.get(self._status_entity)
            status_ok = _state_matches(status_state, [self._status_string])

        # Trigger check: first string required, second optional
        trigger_ok = True
        if self._trigger_entity:
            trigger_state = self.hass.states.get(self._trigger_entity)

            # Allowed list
            triggers_allowed: list[str] = []
            if self._trigger_string_1:
                triggers_allowed.append(self._trigger_string_1)
            if self._trigger_string_2:
                triggers_allowed.append(self._trigger_string_2)

            # NEW: Blocked list (comma-separated string -> list)
            blocked: list[str] = []
            if self._trigger_block:
                blocked = [part.strip() for part in str(self._trigger_block).split(",") if part.strip()]

            # If blocked matches, trigger fails immediately
            if blocked and _state_matches(trigger_state, blocked):
                trigger_ok = False
            else:
                # Otherwise require allowed match (empty allowed means True)
                trigger_ok = _state_matches(trigger_state, triggers_allowed)

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
            pct = _round_coverage((solar_w / device_w) * 100.0)

        return {
            "solar_w": solar_w,
            "device_w": device_w,
            "coverage_pct": pct,
            "conditions_allowed": allowed,
            "status_ok": status_ok,
            "trigger_ok": trigger_ok,
        }

    def _setup_subscriptions(self) -> None:
        # Clear any previous subscriptions
        for unsub in self._unsub:
            try:
                unsub()
            except Exception:
                pass
        self._unsub.clear()

        # In periodic mode, do NOT subscribe (poll-only behavior)
        if self._periodic:
            _LOGGER.debug("solardelta: periodic mode enabled; not subscribing to push updates")
            return

        # Push-only mode: subscribe to entity changes for immediate updates
        @callback
        def _state_changed(event):
            self.async_set_updated_data(self._compute_now())

        entity_ids = [self._solar_entity, self._device_entity]
        if self._status_entity:
            entity_ids.append(self._status_entity)
        if self._trigger_entity:
            entity_ids.append(self._trigger_entity)

        self._unsub.append(async_track_state_change_event(self.hass, entity_ids, _state_changed))
