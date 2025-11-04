from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import State, callback, HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from .const import DOMAIN
from .coordinator import SolarDeltaCoordinator


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


class SolarCoverageSensor(CoordinatorEntity[SolarDeltaCoordinator], SensorEntity):
    """Current coverage percentage sensor (non-persistent)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:percent"
    _attr_has_entity_name = False

    def __init__(self, coordinator: SolarDeltaCoordinator, entry_id: str, display_name: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._display_name = display_name
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_coverage"

    @property
    def name(self) -> str | None:
        return f"solardelta {self._display_name} coverage"

    @property
    def native_value(self) -> float | int | None:
        data = self.coordinator.data or {}
        cov = data.get("coverage_pct")
        if cov is None:
            return None
        return _round_coverage(float(cov))

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "SolarDelta",
            "manufacturer": "KriVaTri",
            "model": "SolarDelta",
        }


class SolarCoverageGridSensor(CoordinatorEntity[SolarDeltaCoordinator], SensorEntity):
    """Current grid-aware coverage percentage sensor (non-persistent)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:percent"
    _attr_has_entity_name = False

    def __init__(self, coordinator: SolarDeltaCoordinator, entry_id: str, display_name: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._display_name = display_name
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_coverage_grid"

    @property
    def name(self) -> str | None:
        # Same as original, with "grid" appended
        return f"solardelta {self._display_name} coverage grid"

    @property
    def native_value(self) -> float | int | None:
        data = self.coordinator.data or {}
        cov = data.get("coverage_grid_pct")
        if cov is None:
            return None
        return _round_coverage(float(cov))

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "SolarDelta",
            "manufacturer": "KriVaTri",
            "model": "SolarDelta",
        }


class _AvgBase(CoordinatorEntity[SolarDeltaCoordinator], SensorEntity):
    """Base class for time-weighted average sensors."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:percent"
    _file_suffix: str  # override in subclasses
    _attr_has_entity_name = False

    def __init__(self, coordinator: SolarDeltaCoordinator, entry_id: str, display_name: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._display_name = display_name
        self._name_slug = slugify(display_name).lower()

        # Name-based storage key
        self._store_key = f"{DOMAIN}_name_{self._name_slug}_{self._file_suffix}.json"

        self._sum_cov_dt: float = 0.0  # coverage * seconds
        self._sum_dt: float = 0.0  # seconds (elapsed active time)
        self._last_ts_utc = dt_util.utcnow()
        self._current_value: float | int = 0

        self._store = Store(self.coordinator.hass, 1, self._store_key)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        data = await self._store.async_load() or {}

        self._sum_cov_dt = float(data.get("sum_cov_dt", 0.0))
        self._sum_dt = float(data.get("sum_dt", 0.0))
        ts = data.get("last_ts")
        if ts:
            try:
                parsed = dt_util.parse_datetime(ts)
                self._last_ts_utc = parsed if parsed is not None else dt_util.utcnow()
            except Exception:
                self._last_ts_utc = dt_util.utcnow()
        else:
            self._last_ts_utc = dt_util.utcnow()
        self._current_value = data.get("current_value", 0)
        self._load_extra(data)
        self.async_write_ha_state()

    def _load_extra(self, data: dict) -> None:
        return

    async def _persist(self) -> None:
        payload = {
            "sum_cov_dt": self._sum_cov_dt,
            "sum_dt": self._sum_dt,
            "last_ts": dt_util.utcnow().isoformat(),
            "current_value": self._current_value,
        }
        payload.update(self._persist_extra())
        await self._store.async_save(payload)

    def _persist_extra(self) -> dict:
        return {}

    def _accumulate(self, coverage: Optional[float | int], dt_seconds: float, allowed: bool) -> None:
        if not allowed:
            return
        if coverage is None:
            return
        try:
            cov = float(coverage)
        except (ValueError, TypeError):
            return
        if dt_seconds <= 0:
            return
        self._sum_cov_dt += cov * dt_seconds
        self._sum_dt += dt_seconds
        if self._sum_dt > 0:
            avg = self._sum_cov_dt / self._sum_dt
            self._current_value = _round_coverage(avg)

    async def _reset_to_zero(self) -> None:
        self._sum_cov_dt = 0.0
        self._sum_dt = 0.0
        self._current_value = 0
        self._last_ts_utc = dt_util.utcnow()
        self.async_write_ha_state()
        await self._persist()

    @property
    def native_value(self) -> float | int | None:
        return self._current_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose elapsed active time as days, hours, and minutes."""
        secs = int(self._sum_dt)
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        return {
            "active_seconds": secs,
            "active_time": f"{days}d {hours}h {minutes}m",
        }

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "SolarDelta",
            "manufacturer": "KriVaTri",
            "model": "SolarDelta",
        }

    def _maybe_reset_on_update(self, now_utc) -> None:
        return

    def _pre_update(self, now_utc) -> None:
        return

    def _post_update(self) -> None:
        return

    def _now_and_dt(self) -> tuple[Any, float]:
        now_utc = dt_util.utcnow()
        dt_seconds = (now_utc - self._last_ts_utc).total_seconds()
        if dt_seconds < 0:
            dt_seconds = 0.0
        self._last_ts_utc = now_utc
        return now_utc, dt_seconds

    def _coverage_and_allowed(self) -> tuple[Optional[float | int], bool]:
        data = self.coordinator.data or {}
        # Prefer new per-average gating, fallback to legacy flag if needed
        allowed = bool(
            data.get("conditions_allowed_unaware", data.get("conditions_allowed", True))
        )
        return data.get("coverage_pct"), allowed

    @callback
    def _handle_coordinator_update(self) -> None:
        try:
            now_utc, dt_seconds = self._now_and_dt()
            self._maybe_reset_on_update(now_utc)
            self._pre_update(now_utc)

            coverage, allowed = self._coverage_and_allowed()
            self._accumulate(coverage, dt_seconds, allowed)

            self._post_update()
            self.async_write_ha_state()
            self.coordinator.hass.async_create_task(self._persist())
        except Exception:
            self.async_write_ha_state()


class SolarCoverageAvgSessionSensor(_AvgBase):
    _file_suffix = "avg_session"

    def __init__(
        self,
        coordinator: SolarDeltaCoordinator,
        entry_id: str,
        display_name: str,
        reset_entity: Optional[str],
    ) -> None:
        super().__init__(coordinator, entry_id, display_name)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_avg_session"
        self._reset_entity = reset_entity
        self._last_reset_norm: Optional[str] = None

    @property
    def name(self) -> str | None:
        return f"solardelta {self._display_name} avg session"

    def _load_extra(self, data: dict) -> None:
        self._last_reset_norm = data.get("last_reset_norm")

    def _persist_extra(self) -> dict:
        return {
            "last_reset_norm": self._last_reset_norm,
        }

    def _normalize_state(self, st: Optional[State]) -> Optional[str]:
        if st is None:
            return None
        s = st.state
        if s in (None, "unknown", "unavailable"):
            return s
        return str(s).strip().lower()

    def _maybe_reset_on_update(self, now_utc) -> None:
        """Reset average when reset sensor changes from any known non-target state to the configured reset string."""
        if not self._reset_entity:
            return

        # Current normalized reset state
        cur_state = self.coordinator.hass.states.get(self._reset_entity)
        cur_norm = self._normalize_state(cur_state)

        # Target: configured reset string (normalized)
        target = self.coordinator.reset_string
        target_norm = str(target).strip().lower() if target else None

        prev = self._last_reset_norm

        # Do NOT reset when previous is None/unknown/unavailable/target;
        # reset only when moving from some other known state to the target.
        if target_norm and prev not in (None, "unknown", "unavailable", target_norm) and cur_norm == target_norm:
            self._sum_cov_dt = 0.0
            self._sum_dt = 0.0
            self._current_value = 0

        self._last_reset_norm = cur_norm

    async def async_reset_avg_session(self) -> None:
        """Service handler to reset session average to 0."""
        await self._reset_to_zero()


class SolarCoverageAvgYearSensor(_AvgBase):
    _file_suffix = "avg_year"

    def __init__(self, coordinator: SolarDeltaCoordinator, entry_id: str, display_name: str) -> None:
        super().__init__(coordinator, entry_id, display_name)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_avg_year"
        self._year: Optional[int] = None

    @property
    def name(self) -> str | None:
        return f"solardelta {self._display_name} avg year"

    def _pre_update(self, now_utc) -> None:
        now_local = dt_util.now()
        current_year = now_local.year
        if self._year is None:
            self._year = current_year
        elif self._year != current_year:
            self._year = current_year
            self._sum_cov_dt = 0.0
            self._sum_dt = 0.0
            self._current_value = 0

    async def async_reset_avg_year(self) -> None:
        self._year = dt_util.now().year
        await self._reset_to_zero()


class SolarCoverageAvgLifetimeSensor(_AvgBase):
    _file_suffix = "avg_lifetime"

    def __init__(self, coordinator: SolarDeltaCoordinator, entry_id: str, display_name: str) -> None:
        super().__init__(coordinator, entry_id, display_name)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_avg_lifetime"

    @property
    def name(self) -> str | None:
        return f"solardelta {self._display_name} avg lifetime"

    async def async_reset_avg_lifetime(self) -> None:
        await self._reset_to_zero()


# Grid-aware average base (reads coverage_grid_pct)
class _AvgBaseGrid(_AvgBase):
    def _coverage_and_allowed(self) -> tuple[Optional[float | int], bool]:
        data = self.coordinator.data or {}
        allowed = bool(
            data.get("conditions_allowed_grid", data.get("conditions_allowed", True))
        )
        return data.get("coverage_grid_pct"), allowed


class SolarCoverageAvgSessionGridSensor(_AvgBaseGrid):
    _file_suffix = "avg_session_grid"

    def __init__(
        self,
        coordinator: SolarDeltaCoordinator,
        entry_id: str,
        display_name: str,
        reset_entity: Optional[str],
    ) -> None:
        super().__init__(coordinator, entry_id, display_name)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_avg_session_grid"
        self._reset_entity = reset_entity
        self._last_reset_norm: Optional[str] = None

    @property
    def name(self) -> str | None:
        return f"solardelta {self._display_name} avg session grid"

    def _load_extra(self, data: dict) -> None:
        self._last_reset_norm = data.get("last_reset_norm")

    def _persist_extra(self) -> dict:
        return {"last_reset_norm": self._last_reset_norm}

    def _normalize_state(self, st: Optional[State]) -> Optional[str]:
        if st is None:
            return None
        s = st.state
        if s in (None, "unknown", "unavailable"):
            return s
        return str(s).strip().lower()

    def _maybe_reset_on_update(self, now_utc) -> None:
        if not self._reset_entity:
            return
        cur_state = self.coordinator.hass.states.get(self._reset_entity)
        cur_norm = self._normalize_state(cur_state)
        target = self.coordinator.reset_string
        target_norm = str(target).strip().lower() if target else None
        prev = self._last_reset_norm
        if target_norm and prev not in (None, "unknown", "unavailable", target_norm) and cur_norm == target_norm:
            self._sum_cov_dt = 0.0
            self._sum_dt = 0.0
            self._current_value = 0
        self._last_reset_norm = cur_norm

    async def async_reset_avg_session(self) -> None:
        await self._reset_to_zero()


class SolarCoverageAvgYearGridSensor(_AvgBaseGrid):
    _file_suffix = "avg_year_grid"

    def __init__(self, coordinator: SolarDeltaCoordinator, entry_id: str, display_name: str) -> None:
        super().__init__(coordinator, entry_id, display_name)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_avg_year_grid"
        self._year: Optional[int] = None

    @property
    def name(self) -> str | None:
        return f"solardelta {self._display_name} avg year grid"

    def _pre_update(self, now_utc) -> None:
        now_local = dt_util.now()
        current_year = now_local.year
        if self._year is None:
            self._year = current_year
        elif self._year != current_year:
            self._year = current_year
            self._sum_cov_dt = 0.0
            self._sum_dt = 0.0
            self._current_value = 0

    async def async_reset_avg_year(self) -> None:
        self._year = dt_util.now().year
        await self._reset_to_zero()


class SolarCoverageAvgLifetimeGridSensor(_AvgBaseGrid):
    _file_suffix = "avg_lifetime_grid"

    def __init__(self, coordinator: SolarDeltaCoordinator, entry_id: str, display_name: str) -> None:
        super().__init__(coordinator, entry_id, display_name)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_avg_lifetime_grid"

    @property
    def name(self) -> str | None:
        return f"solardelta {self._display_name} avg lifetime grid"

    async def async_reset_avg_lifetime(self) -> None:
        await self._reset_to_zero()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up SolarDelta sensors for a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: SolarDeltaCoordinator = data["coordinator"]
    display_name: str = data.get("name") or "SolarDelta"
    reset_entity: Optional[str] = data.get("reset_entity")

    # Core coverage sensors
    coverage = SolarCoverageSensor(coordinator, entry.entry_id, display_name)
    coverage_grid = SolarCoverageGridSensor(coordinator, entry.entry_id, display_name)

    # Averages (original)
    avg_session = SolarCoverageAvgSessionSensor(
        coordinator=coordinator,
        entry_id=entry.entry_id,
        display_name=display_name,
        reset_entity=reset_entity,
    )
    avg_year = SolarCoverageAvgYearSensor(
        coordinator=coordinator,
        entry_id=entry.entry_id,
        display_name=display_name,
    )
    avg_lifetime = SolarCoverageAvgLifetimeSensor(
        coordinator=coordinator,
        entry_id=entry.entry_id,
        display_name=display_name,
    )

    # Averages (grid-aware)
    avg_session_grid = SolarCoverageAvgSessionGridSensor(
        coordinator=coordinator,
        entry_id=entry.entry_id,
        display_name=display_name,
        reset_entity=reset_entity,
    )
    avg_year_grid = SolarCoverageAvgYearGridSensor(
        coordinator=coordinator,
        entry_id=entry.entry_id,
        display_name=display_name,
    )
    avg_lifetime_grid = SolarCoverageAvgLifetimeGridSensor(
        coordinator=coordinator,
        entry_id=entry.entry_id,
        display_name=display_name,
    )

    # Expose references for services
    data["avg_session_entity"] = avg_session
    data["avg_year_entity"] = avg_year
    data["avg_lifetime_entity"] = avg_lifetime
    data["avg_session_grid_entity"] = avg_session_grid
    data["avg_year_grid_entity"] = avg_year_grid
    data["avg_lifetime_grid_entity"] = avg_lifetime_grid

    async_add_entities(
        [
            coverage,
            coverage_grid,
            avg_session,
            avg_year,
            avg_lifetime,
            avg_session_grid,
            avg_year_grid,
            avg_lifetime_grid,
        ]
    )
