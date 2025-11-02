from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _norm_str(val: Optional[str]) -> str:
    return (val or "").strip().casefold()


def _state_matches(state, candidates: list[str]) -> bool:
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
        interval = (
            timedelta(seconds=int(scan_interval_seconds))
            if scan_interval_seconds and int(scan_interval_seconds) > 0
            else None
        )
        # HA DataUpdateCoordinator now requires a logger argument
        super().__init__(hass, _LOGGER, name="solardelta", update_interval=interval)

        self.hass = hass
        self._solar_entity = solar_entity
        self._device_entity = device_entity
        self._status_entity = status_entity
        self._status_string = status_string
        self._trigger_entity = trigger_entity
        self._trigger_string_1 = trigger_string_1
        self._periodic = bool(interval is not None)
        self._interval_seconds = int(scan_interval_seconds or 0)
        self._unsub: list[callable] = []

    @property
    def trigger_string(self) -> Optional[str]:
        """Return the configured trigger string."""
        return self._trigger_string_1

    def _conditions_ok(self) -> tuple[bool, bool, bool]:
        """Return (allowed, status_ok, trigger_ok) based on configured conditions."""
        # Status check: one required string
        status_ok = True
        if self._status_entity:
            status_state = self.hass.states.get(self._status_entity)
            status_ok = _state_matches(status_state, [self._status_string] if self._status_string else [])

        # Trigger check: one required string
        trigger_ok = True
        if self._trigger_entity:
            trigger_state = self.hass.states.get(self._trigger_entity)
            trigger_ok = _state_matches(trigger_state, [self._trigger_string_1] if self._trigger_string_1 else [])

        allowed = status_ok and trigger_ok
        return allowed, status_ok, trigger_ok

    async def async_config_entry_first_refresh(self) -> None:
        # Placeholder for initial data load / subscriptions if needed.
        return

    async def async_shutdown(self) -> None:
        for u in self._unsub:
            try:
                u()
            except Exception:
                pass
        self._unsub.clear()

    async def async_reset_avg_year(self) -> None:
        # The reset is handled by the sensor entity via service; coordinator kept for back-compat.
        return
