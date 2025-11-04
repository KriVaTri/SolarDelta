from __future__ import annotations

import asyncio
import contextlib
from typing import Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util import slugify

from .const import (
    CONF_DEVICE_ENTITY,
    CONF_GRID_ENTITY,
    CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY,
    CONF_GRID_SEPARATE,
    CONF_NAME,
    CONF_RESET_ENTITY,
    CONF_RESET_STRING,
    CONF_SOLAR_ENTITY,
    CONF_STATUS_ENTITY,
    CONF_STATUS_STRING,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SolarDeltaCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Fixed service names (hassfest-friendly)
SVC_RESET_SESSION = "reset_avg_session"
SVC_RESET_YEAR = "reset_avg_year"
SVC_RESET_LIFETIME = "reset_avg_lifetime"
SVC_RESET_SESSION_GRID = "reset_avg_session_grid"
SVC_RESET_YEAR_GRID = "reset_avg_year_grid"
SVC_RESET_LIFETIME_GRID = "reset_avg_lifetime_grid"
SVC_RESET_ALL = "reset_all_averages"

_ALL_SERVICES: tuple[str, ...] = (
    SVC_RESET_SESSION,
    SVC_RESET_YEAR,
    SVC_RESET_LIFETIME,
    SVC_RESET_SESSION_GRID,
    SVC_RESET_YEAR_GRID,
    SVC_RESET_LIFETIME_GRID,
    SVC_RESET_ALL,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


def _iter_entry_data(hass: HomeAssistant) -> Iterable[tuple[str, dict]]:
    for key, data in (hass.data.get(DOMAIN) or {}).items():
        # Skip internal flags (underscored keys)
        if key.startswith("_"):
            continue
        if isinstance(data, dict):
            yield key, data


def _find_entry_id(hass: HomeAssistant, *, entry_id: str | None, name: str | None) -> str | None:
    """Resolve which entry to operate on using entry_id or name."""
    if entry_id:
        return entry_id if entry_id in (hass.data.get(DOMAIN) or {}) else None
    if name:
        name_norm = (name or "").strip().casefold()
        for eid, data in _iter_entry_data(hass):
            display = (data.get("name") or "").strip().casefold()
            if display == name_norm:
                return eid
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_name = entry.data.get(CONF_NAME) or entry.title or "SolarDelta"

    solar_entity = entry.options.get(CONF_SOLAR_ENTITY) or entry.data.get(CONF_SOLAR_ENTITY)

    # Grid config
    grid_separate = bool(
        entry.options.get(CONF_GRID_SEPARATE)
        if entry.options.get(CONF_GRID_SEPARATE) is not None
        else entry.data.get(CONF_GRID_SEPARATE) or False
    )
    grid_entity = entry.options.get(CONF_GRID_ENTITY) or entry.data.get(CONF_GRID_ENTITY)
    grid_import = entry.options.get(CONF_GRID_IMPORT_ENTITY) or entry.data.get(CONF_GRID_IMPORT_ENTITY)
    grid_export = entry.options.get(CONF_GRID_EXPORT_ENTITY) or entry.data.get(CONF_GRID_EXPORT_ENTITY)

    device_entity = entry.options.get(CONF_DEVICE_ENTITY) or entry.data.get(CONF_DEVICE_ENTITY)

    status_entity = entry.options.get(CONF_STATUS_ENTITY) or entry.data.get(CONF_STATUS_ENTITY)
    status_string = entry.options.get(CONF_STATUS_STRING) or entry.data.get(CONF_STATUS_STRING)

    reset_entity = entry.options.get(CONF_RESET_ENTITY) or entry.data.get(CONF_RESET_ENTITY)
    reset_string = entry.options.get(CONF_RESET_STRING) or entry.data.get(CONF_RESET_STRING)

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL)
    if scan_interval is None:
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, 0)

    coordinator = SolarDeltaCoordinator(
        hass=hass,
        solar_entity=solar_entity,
        grid_entity=grid_entity,
        grid_separate=grid_separate,
        grid_import_entity=grid_import,
        grid_export_entity=grid_export,
        device_entity=device_entity,
        status_entity=status_entity,
        status_string=status_string,
        reset_entity=reset_entity,
        reset_string=reset_string,
        scan_interval_seconds=int(scan_interval or 0),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "name": entry_name,
        "status_entity": status_entity,
        "reset_entity": reset_entity,
    }

    # One-time global service registration (fixed names, hassfest-friendly)
    if not hass.data[DOMAIN].get("_services_registered"):
        hass.services.async_register(DOMAIN, SVC_RESET_SESSION, _handle_reset_session)
        hass.services.async_register(DOMAIN, SVC_RESET_YEAR, _handle_reset_year)
        hass.services.async_register(DOMAIN, SVC_RESET_LIFETIME, _handle_reset_lifetime)
        hass.services.async_register(DOMAIN, SVC_RESET_SESSION_GRID, _handle_reset_session_grid)
        hass.services.async_register(DOMAIN, SVC_RESET_YEAR_GRID, _handle_reset_year_grid)
        hass.services.async_register(DOMAIN, SVC_RESET_LIFETIME_GRID, _handle_reset_lifetime_grid)
        hass.services.async_register(DOMAIN, SVC_RESET_ALL, _handle_reset_all)
        hass.data[DOMAIN]["_services_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    return True


async def _handle_reset_session(call: ServiceCall) -> None:
    await _handle_reset(call, [("avg_session_entity", "async_reset_avg_session")])


async def _handle_reset_year(call: ServiceCall) -> None:
    await _handle_reset(call, [("avg_year_entity", "async_reset_avg_year")])


async def _handle_reset_lifetime(call: ServiceCall) -> None:
    await _handle_reset(call, [("avg_lifetime_entity", "async_reset_avg_lifetime")])


async def _handle_reset_session_grid(call: ServiceCall) -> None:
    await _handle_reset(call, [("avg_session_grid_entity", "async_reset_avg_session")])


async def _handle_reset_year_grid(call: ServiceCall) -> None:
    await _handle_reset(call, [("avg_year_grid_entity", "async_reset_avg_year")])


async def _handle_reset_lifetime_grid(call: ServiceCall) -> None:
    await _handle_reset(call, [("avg_lifetime_grid_entity", "async_reset_avg_lifetime")])


async def _handle_reset_all(call: ServiceCall) -> None:
    await _handle_reset(
        call,
        [
            ("avg_session_entity", "async_reset_avg_session"),
            ("avg_year_entity", "async_reset_avg_year"),
            ("avg_lifetime_entity", "async_reset_avg_lifetime"),
            ("avg_session_grid_entity", "async_reset_avg_session"),
            ("avg_year_grid_entity", "async_reset_avg_year"),
            ("avg_lifetime_grid_entity", "async_reset_avg_lifetime"),
        ],
    )


async def _handle_reset(call: ServiceCall, ops: list[tuple[str, str]]) -> None:
    """Resolve entry by entry_id or name and invoke the requested reset(s)."""
    hass = call.hass
    entry_id = _find_entry_id(
        hass,
        entry_id=str(call.data.get("entry_id") or "").strip() or None,
        name=str(call.data.get("name") or "").strip() or None,
    )
    if not entry_id:
        return

    data = hass.data[DOMAIN].get(entry_id) or {}
    tasks: list = []
    for key, method in ops:
        ent = data.get(key)
        if ent and hasattr(ent, method):
            tasks.append(getattr(ent, method)())
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        coordinator = data.get("coordinator") if isinstance(data, dict) else None
        if coordinator:
            await coordinator.async_shutdown()

        # If no entries left, remove global services
        if DOMAIN in hass.data and not any(k for k in hass.data[DOMAIN].keys() if not k.startswith("_")):
            for svc in _ALL_SERVICES:
                with contextlib.suppress(Exception):
                    hass.services.async_remove(DOMAIN, svc)
            hass.data[DOMAIN].pop("_services_registered", None)

        if not hass.data.get(DOMAIN):
            hass.data.pop(DOMAIN, None)

    return unloaded


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
