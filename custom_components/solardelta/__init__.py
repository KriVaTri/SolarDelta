from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_SOLAR_ENTITY,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ENTITIES,
    CONF_NAME,
    CONF_STATUS_ENTITY,
    CONF_STATUS_STRING,
    CONF_TRIGGER_ENTITY,
    CONF_TRIGGER_STRING_1,
    CONF_TRIGGER_STRING_2,
)
from .coordinator import SolarDeltaCoordinator

# This integration is configured via config entries only (no YAML)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register services for the solardelta domain."""

    async def _iter_targets(type_key: str, entity_ids: list[str] | None):
        for _entry_id, data in list(hass.data.get(DOMAIN, {}).items()):
            entity = data.get(type_key)
            if entity is None:
                continue
            if entity_ids:
                if getattr(entity, "entity_id", None) in entity_ids:
                    yield entity
            else:
                yield entity

    async def _handle_reset_year(call: ServiceCall):
        entity_ids = call.data.get("entity_id")
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        async for ent in _iter_targets("avg_year_entity", entity_ids):
            if hasattr(ent, "async_reset_avg_year"):
                await ent.async_reset_avg_year()

    async def _handle_reset_lifetime(call: ServiceCall):
        entity_ids = call.data.get("entity_id")
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        async for ent in _iter_targets("avg_lifetime_entity", entity_ids):
            if hasattr(ent, "async_reset_avg_lifetime"):
                await ent.async_reset_avg_lifetime()

    if not hass.services.has_service(DOMAIN, "reset_avg_year"):
        hass.services.async_register(
            DOMAIN,
            "reset_avg_year",
            _handle_reset_year,
            schema=vol.Schema({vol.Optional("entity_id"): cv.entity_ids}),
        )
    if not hass.services.has_service(DOMAIN, "reset_avg_lifetime"):
        hass.services.async_register(
            DOMAIN,
            "reset_avg_lifetime",
            _handle_reset_lifetime,
            schema=vol.Schema({vol.Optional("entity_id"): cv.entity_ids}),
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarDelta from a config entry."""
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
    trigger_entity = entry.options.get(CONF_TRIGGER_ENTITY) or entry.data.get(CONF_TRIGGER_ENTITY)
    trigger_string_1 = entry.options.get(CONF_TRIGGER_STRING_1) or entry.data.get(CONF_TRIGGER_STRING_1)
    trigger_string_2 = entry.options.get(CONF_TRIGGER_STRING_2) or entry.data.get(CONF_TRIGGER_STRING_2)

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL)
    if scan_interval is None:
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, 0)

    coordinator = SolarDeltaCoordinator(
        hass=hass,
        solar_entity=solar_entity,
        device_entity=device_entity,
        status_entity=status_entity,
        status_string=status_string,
        trigger_entity=trigger_entity,
        trigger_string_1=trigger_string_1,
        trigger_string_2=trigger_string_2,
        scan_interval_seconds=int(scan_interval or 0),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "name": entry_name,
        "status_entity": status_entity,
        "status_string": status_string,
        "trigger_entity": trigger_entity,
        "trigger_string_1": trigger_string_1,
        "trigger_string_2": trigger_string_2,
        "scan_interval": scan_interval,
        "avg_year_entity": None,
        "avg_lifetime_entity": None,
    }

    entry.async_on_unload(entry.add_update_listener(_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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
