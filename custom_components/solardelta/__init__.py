from __future__ import annotations

import asyncio
import contextlib

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


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


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
        "per_entry_services": [],
    }

    # Dynamic per-entry services (keep existing behavior)
    suffix = slugify(entry_name).lower() or slugify(entry.entry_id).lower()

    async def _handle_reset_session_entry(call: ServiceCall) -> None:
        data = hass.data[DOMAIN].get(entry.entry_id) or {}
        ent = data.get("avg_session_entity")
        if ent and hasattr(ent, "async_reset_avg_session"):
            await ent.async_reset_avg_session()

    async def _handle_reset_year_entry(call: ServiceCall) -> None:
        data = hass.data[DOMAIN].get(entry.entry_id) or {}
        ent = data.get("avg_year_entity")
        if ent and hasattr(ent, "async_reset_avg_year"):
            await ent.async_reset_avg_year()

    async def _handle_reset_lifetime_entry(call: ServiceCall) -> None:
        data = hass.data[DOMAIN].get(entry.entry_id) or {}
        ent = data.get("avg_lifetime_entity")
        if ent and hasattr(ent, "async_reset_avg_lifetime"):
            await ent.async_reset_avg_lifetime()

    async def _handle_reset_session_grid_entry(call: ServiceCall) -> None:
        data = hass.data[DOMAIN].get(entry.entry_id) or {}
        ent = data.get("avg_session_grid_entity")
        if ent and hasattr(ent, "async_reset_avg_session"):
            await ent.async_reset_avg_session()

    async def _handle_reset_year_grid_entry(call: ServiceCall) -> None:
        data = hass.data[DOMAIN].get(entry.entry_id) or {}
        ent = data.get("avg_year_grid_entity")
        if ent and hasattr(ent, "async_reset_avg_year"):
            await ent.async_reset_avg_year()

    async def _handle_reset_lifetime_grid_entry(call: ServiceCall) -> None:
        data = hass.data[DOMAIN].get(entry.entry_id) or {}
        ent = data.get("avg_lifetime_grid_entity")
        if ent and hasattr(ent, "async_reset_avg_lifetime"):
            await ent.async_reset_avg_lifetime()

    async def _handle_reset_all_averages_entry(call: ServiceCall) -> None:
        data = hass.data[DOMAIN].get(entry.entry_id) or {}
        pairs = [
            ("avg_session_entity", "async_reset_avg_session"),
            ("avg_year_entity", "async_reset_avg_year"),
            ("avg_lifetime_entity", "async_reset_avg_lifetime"),
            ("avg_session_grid_entity", "async_reset_avg_session"),
            ("avg_year_grid_entity", "async_reset_avg_year"),
            ("avg_lifetime_grid_entity", "async_reset_avg_lifetime"),
        ]
        tasks = []
        for key, method in pairs:
            ent = data.get(key)
            if ent and hasattr(ent, method):
                tasks.append(getattr(ent, method)())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    service_names = {
        "reset_avg_session": f"reset_avg_session_{suffix}",
        "reset_avg_year": f"reset_avg_year_{suffix}",
        "reset_avg_lifetime": f"reset_avg_lifetime_{suffix}",
        "reset_avg_session_grid": f"reset_avg_session_grid_{suffix}",
        "reset_avg_year_grid": f"reset_avg_year_grid_{suffix}",
        "reset_avg_lifetime_grid": f"reset_avg_lifetime_grid_{suffix}",
        "reset_all_averages": f"reset_all_averages_{suffix}",
    }

    hass.services.async_register(DOMAIN, service_names["reset_avg_session"], _handle_reset_session_entry)
    hass.services.async_register(DOMAIN, service_names["reset_avg_year"], _handle_reset_year_entry)
    hass.services.async_register(DOMAIN, service_names["reset_avg_lifetime"], _handle_reset_lifetime_entry)
    hass.services.async_register(DOMAIN, service_names["reset_avg_session_grid"], _handle_reset_session_grid_entry)
    hass.services.async_register(DOMAIN, service_names["reset_avg_year_grid"], _handle_reset_year_grid_entry)
    hass.services.async_register(DOMAIN, service_names["reset_avg_lifetime_grid"], _handle_reset_lifetime_grid_entry)
    hass.services.async_register(DOMAIN, service_names["reset_all_averages"], _handle_reset_all_averages_entry)

    hass.data[DOMAIN][entry.entry_id]["per_entry_services"] = list(service_names.values())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    for svc in data.get("per_entry_services", []):
        with contextlib.suppress(Exception):
            hass.services.async_remove(DOMAIN, svc)

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        store = hass.data[DOMAIN].pop(entry.entry_id, None)
        coordinator = store.get("coordinator") if isinstance(store, dict) else None
        if coordinator:
            await coordinator.async_shutdown()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return unloaded


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
