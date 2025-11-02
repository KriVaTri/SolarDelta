from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers.selector import selector

from .const import (
    DOMAIN,
    CONF_SOLAR_ENTITY,
    CONF_DEVICE_ENTITY,
    CONF_NAME,
    CONF_STATUS_ENTITY,
    CONF_STATUS_STRING,
    CONF_TRIGGER_ENTITY,
    CONF_TRIGGER_STRING_1,
    CONF_TRIGGER_STRING_2,
    CONF_DEVICE_ENTITIES,
)


def _norm(s: str | None) -> str:
    return (s or "").strip().casefold()


def _existing_names(entries: list[config_entries.ConfigEntry], exclude_entry_id: str | None = None) -> set[str]:
    names: set[str] = set()
    for e in entries:
        if exclude_entry_id and e.entry_id == exclude_entry_id:
            continue
        nm = e.options.get(CONF_NAME) or e.data.get(CONF_NAME) or e.title or ""
        names.add(_norm(nm))
    return names


def _build_user_schema() -> vol.Schema:
    entity_selector = {"entity": {"domain": ["sensor", "binary_sensor"]}}
    return vol.Schema(
        {
            vol.Required(CONF_NAME): str,
            vol.Required(CONF_SOLAR_ENTITY): selector({"entity": {"domain": "sensor"}}),
            vol.Required(CONF_DEVICE_ENTITY): selector({"entity": {"domain": "sensor"}}),
            vol.Required(CONF_STATUS_ENTITY): selector(entity_selector),
            vol.Required(CONF_STATUS_STRING): str,
            vol.Required(CONF_TRIGGER_ENTITY): selector(entity_selector),
            vol.Required(CONF_TRIGGER_STRING_1): str,
            vol.Optional(CONF_TRIGGER_STRING_2): str,
            vol.Required(CONF_SCAN_INTERVAL, default=0): selector(
                {"number": {"min": 0, "max": 86400, "step": 1, "mode": "box", "unit_of_measurement": "s"}}
            ),
        }
    )


class SolarDeltaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        schema = _build_user_schema()

        if user_input is not None:
            new_name = user_input.get(CONF_NAME)
            existing = _existing_names(self._async_current_entries())
            if _norm(new_name) in existing:
                return self.async_show_form(
                    step_id="user", data_schema=schema, errors={CONF_NAME: "name_in_use"}
                )
            title = new_name or "SolarDelta"
            return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarDeltaOptionsFlowHandler(config_entry)


class SolarDeltaOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow (name immutable)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = self._build_schema()

        entry_name = (
            self.config_entry.options.get(CONF_NAME)
            or self.config_entry.data.get(CONF_NAME)
            or self.config_entry.title
            or "SolarDelta"
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={"entry_name": entry_name},
        )

    def _build_schema(self) -> vol.Schema:
        get_opt = self.config_entry.options.get
        get_dat = self.config_entry.data.get

        cur_solar = get_opt(CONF_SOLAR_ENTITY) or get_dat(CONF_SOLAR_ENTITY)
        legacy_devices = get_opt(CONF_DEVICE_ENTITIES) or get_dat(CONF_DEVICE_ENTITIES) or []
        cur_device = (
            get_opt(CONF_DEVICE_ENTITY)
            or get_dat(CONF_DEVICE_ENTITY)
            or (legacy_devices[0] if legacy_devices else None)
        )

        cur_status_entity = get_opt(CONF_STATUS_ENTITY) or get_dat(CONF_STATUS_ENTITY)
        cur_status_string = get_opt(CONF_STATUS_STRING) or get_dat(CONF_STATUS_STRING) or ""
        cur_trigger_entity = get_opt(CONF_TRIGGER_ENTITY) or get_dat(CONF_TRIGGER_ENTITY)
        cur_trigger_str1 = get_opt(CONF_TRIGGER_STRING_1) or get_dat(CONF_TRIGGER_STRING_1) or ""
        cur_trigger_str2 = get_opt(CONF_TRIGGER_STRING_2) or get_dat(CONF_TRIGGER_STRING_2) or ""
        cur_scan = get_opt(CONF_SCAN_INTERVAL)
        if cur_scan is None:
            cur_scan = get_dat(CONF_SCAN_INTERVAL)
        if cur_scan is None:
            cur_scan = 0

        entity_selector = {"entity": {"domain": ["sensor", "binary_sensor"]}}

        schema_fields = {}

        if cur_solar is not None:
            schema_fields[vol.Required(CONF_SOLAR_ENTITY, default=cur_solar)] = selector(
                {"entity": {"domain": "sensor"}}
            )
        else:
            schema_fields[vol.Required(CONF_SOLAR_ENTITY)] = selector({"entity": {"domain": "sensor"}})

        if cur_device is not None:
            schema_fields[vol.Required(CONF_DEVICE_ENTITY, default=cur_device)] = selector(
                {"entity": {"domain": "sensor"}}
            )
        else:
            schema_fields[vol.Required(CONF_DEVICE_ENTITY)] = selector({"entity": {"domain": "sensor"}})

        if cur_status_entity is not None:
            schema_fields[vol.Required(CONF_STATUS_ENTITY, default=cur_status_entity)] = selector(entity_selector)
        else:
            schema_fields[vol.Required(CONF_STATUS_ENTITY)] = selector(entity_selector)

        schema_fields[vol.Required(CONF_STATUS_STRING, default=cur_status_string)] = str

        if cur_trigger_entity is not None:
            schema_fields[vol.Required(CONF_TRIGGER_ENTITY, default=cur_trigger_entity)] = selector(entity_selector)
        else:
            schema_fields[vol.Required(CONF_TRIGGER_ENTITY)] = selector(entity_selector)

        schema_fields[vol.Required(CONF_TRIGGER_STRING_1, default=cur_trigger_str1)] = str

        if cur_trigger_str2:
            schema_fields[vol.Optional(CONF_TRIGGER_STRING_2, default=cur_trigger_str2)] = str
        else:
            schema_fields[vol.Optional(CONF_TRIGGER_STRING_2)] = str

        schema_fields[vol.Required(CONF_SCAN_INTERVAL, default=cur_scan)] = selector(
            {"number": {"min": 0, "max": 86400, "step": 1, "mode": "box", "unit_of_measurement": "s"}}
        )

        return vol.Schema(schema_fields)
