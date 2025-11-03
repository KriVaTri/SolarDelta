from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_SOLAR_ENTITY,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ENTITIES,
    CONF_NAME,
    CONF_STATUS_ENTITY,
    CONF_STATUS_STRING,
    CONF_RESET_ENTITY,
    CONF_RESET_STRING,
    LEGACY_CONF_TRIGGER_ENTITY,
    LEGACY_CONF_TRIGGER_STRING_1,
)
from .coordinator import SolarDeltaCoordinator

# This integration is configured via config entries only (no YAML)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the solardelta domain (no global services; services are per-entry)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarDelta from a config entry and register per-entry services."""
    entry_name = entry.data.get(CONF_NAME) or entry.title or "SolarDelta"
    solar_entity = entry.options.get(CONF_SOLAR_ENTITY) or entry.data.get(CONF_SOLAR_ENTITY)

    device_entity = (
        entry.options.get(CONF_DEVICE_ENTITY)
        or entry.data.get(CONF_DEVICE_ENTITY)
        or _first_or_none(entry.options.get(CONF_DEVICE_ENTITIES))
        or _first_or_none(entry.data.get(CONF_DEVICE_ENTITIES))
    )

    status_entity = entry.options.get(CONF_STATUS_ENTITY) or entry.data.get(CONF_STATUS_ENTITY)
    status_string = entry.options.get(CONF_STATUS_STRING) or entry.data.get(CONF_STATUS_STRING)

    # Reset fields with backward-compat for legacy trigger_* fields
    reset_entity = (
        entry.options.get(CONF_RESET_ENTITY)
        or entry.data.get(CONF_RESET_ENTITY)
        or entry.options.get(LEGACY_CONF_TRIGGER_ENTITY)
        or entry.data.get(LEGACY_CONF_TRIGGER_ENTITY)
    )
    reset_string = (
        entry.options.get(CONF_RESET_STRING)
        or entry.data.get(CONF_RESET_STRING)
        or entry.options.get(LEGACY_CONF_TRIGGER_STRING_1)
        or entry.data.get(LEGACY_CONF_TRIGGER_STRING_1)
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL)
    if scan_interval is None:
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, 0)

    coordinator = SolarDeltaCoordinator(
        hass=hass,
        solar_entity=solar_entity,
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
        # will be set by sensor platform setup:
        # "avg_session_entity": ...
        # "avg_year_entity": ...
        # "avg_lifetime_entity": ...
        "per_entry_services": [],  # filled below
    }

    # Register per-entry services with a unique suffix based on the entry's name
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

    service_names = {
        "reset_avg_session": f"reset_avg_session_{suffix}",
        "reset_avg_year": f"reset_avg_year_{suffix}",
        "reset_avg_lifetime": f"reset_avg_lifetime_{suffix}",
    }

    # Register and remember per-entry services so we can remove them on unload
    hass.services.async_register(DOMAIN, service_names["reset_avg_session"], _handle_reset_session_entry)
    hass.services.async_register(DOMAIN, service_names["reset_avg_year"], _handle_reset_year_entry)
    hass.services.async_register(DOMAIN, service_names["reset_avg_lifetime"], _handle_reset_lifetime_entry)
    hass.data[DOMAIN][entry.entry_id]["per_entry_services"] = list(service_names.values())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Remove per-entry services
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    for svc in data.get("per_entry_services", []):
        try:
            hass.services.async_remove(DOMAIN, svc)
        except Exception:
            pass

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data and (coordinator := data.get("coordinator")):
            await coordinator.async_shutdown()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return unloaded


def _first_or_none(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change (name is immutable)."""
    await hass.config_entries.async_reload(entry.entry_id)
