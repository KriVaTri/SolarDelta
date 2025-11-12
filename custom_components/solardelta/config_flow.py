from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers.selector import selector

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_SOLAR_ENTITY,
    CONF_GRID_ENTITY,
    CONF_GRID_SEPARATE,
    CONF_GRID_IMPORT_ENTITY,
    CONF_GRID_EXPORT_ENTITY,
    CONF_DEVICE_ENTITY,
    CONF_STATUS_ENTITY,
    CONF_STATUS_STRING,
    CONF_RESET_ENTITY,
    CONF_RESET_STRING,
)


def _norm(s: str | None) -> str:
    return (s or "").strip().casefold()


def _existing_names(
    entries: list[config_entries.ConfigEntry], exclude_entry_id: str | None = None
) -> set[str]:
    names: set[str] = set()
    for e in entries:
        if exclude_entry_id and e.entry_id == exclude_entry_id:
            continue
        nm = e.options.get(CONF_NAME) or e.data.get(CONF_NAME) or e.title or ""
        names.add(_norm(nm))
    return names


class SolarDeltaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._step1: dict | None = None

    async def async_step_user(self, user_input=None):
        """Step 1: name + choose grid mode."""
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_GRID_SEPARATE, default=False): selector({"boolean": {}}),
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=schema)

        errors: dict[str, str] = {}

        # Unique name validation
        new_name = user_input.get(CONF_NAME)
        existing = _existing_names(self._async_current_entries())
        if _norm(new_name) in existing:
            errors[CONF_NAME] = "name_in_use"

        if errors:
            return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

        # Save step 1 choices and continue
        self._step1 = {
            CONF_NAME: new_name,
            CONF_GRID_SEPARATE: bool(user_input.get(CONF_GRID_SEPARATE, False)),
        }
        return await self.async_step_details()

    async def async_step_details(self, user_input=None):
        """Step 2: sensors and strings; grid fields depend on mode."""
        assert self._step1 is not None, "Step 1 must be completed first"
        separate = bool(self._step1.get(CONF_GRID_SEPARATE, False))

        schema = _build_details_schema(separate)

        if user_input is None:
            return self.async_show_form(step_id="details", data_schema=schema)

        # Validate according to selected grid mode
        errors: dict[str, str] = {}
        if separate:
            if not user_input.get(CONF_GRID_IMPORT_ENTITY):
                errors[CONF_GRID_IMPORT_ENTITY] = "required_if_separate"
            if not user_input.get(CONF_GRID_EXPORT_ENTITY):
                errors[CONF_GRID_EXPORT_ENTITY] = "required_if_separate"
        else:
            if not user_input.get(CONF_GRID_ENTITY):
                errors[CONF_GRID_ENTITY] = "required_if_not_separate"

        # Required common fields
        required_keys = [
            CONF_SOLAR_ENTITY,
            CONF_DEVICE_ENTITY,
            CONF_STATUS_ENTITY,
            CONF_STATUS_STRING,
            CONF_RESET_ENTITY,
            CONF_RESET_STRING,
        ]
        for k in required_keys:
            if not user_input.get(k):
                errors[k] = "required"

        if errors:
            return self.async_show_form(step_id="details", data_schema=schema, errors=errors)

        data = {**self._step1, **user_input}
        title = self._step1.get(CONF_NAME) or "SolarDelta"
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarDeltaOptionsFlowHandler(config_entry)


@callback
def _build_details_schema(separate: bool) -> vol.Schema:
    """Builds the step 2 schema for the initial config flow."""
    entity_selector_any = {"entity": {"domain": ["sensor", "binary_sensor"]}}

    fields: dict = {}

    # Always required
    fields[vol.Required(CONF_SOLAR_ENTITY)] = selector({"entity": {"domain": "sensor"}})

    # Show only the grid fields for the chosen mode
    if separate:
        fields[vol.Required(CONF_GRID_IMPORT_ENTITY)] = selector({"entity": {"domain": "sensor"}})
        fields[vol.Required(CONF_GRID_EXPORT_ENTITY)] = selector({"entity": {"domain": "sensor"}})
    else:
        fields[vol.Required(CONF_GRID_ENTITY)] = selector({"entity": {"domain": "sensor"}})

    # Remaining required inputs
    fields[vol.Required(CONF_DEVICE_ENTITY)] = selector({"entity": {"domain": "sensor"}})
    fields[vol.Required(CONF_STATUS_ENTITY)] = selector(entity_selector_any)
    fields[vol.Required(CONF_STATUS_STRING)] = str
    fields[vol.Required(CONF_RESET_ENTITY)] = selector(entity_selector_any)
    fields[vol.Required(CONF_RESET_STRING)] = str

    # Scan interval
    fields[vol.Required(CONF_SCAN_INTERVAL, default=0)] = selector(
        {
            "number": {
                "min": 0,
                "max": 86400,
                "step": 1,
                "mode": "box",
                "unit_of_measurement": "s",
            }
        }
    )

    return vol.Schema(fields)


# Options Flow (two steps: grid mode, then details)
try:
    OptionsFlowBase = config_entries.OptionsFlowWithConfigEntry  # type: ignore[attr-defined]
except AttributeError:
    OptionsFlowBase = config_entries.OptionsFlow


class SolarDeltaOptionsFlowHandler(OptionsFlowBase):
    """Options flow (name immutable)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        try:
            super().__init__(config_entry)  # type: ignore[misc]
        except TypeError:
            super().__init__()
            # Older HA versions require storing it manually
            self.config_entry = config_entry  # noqa: SLF001
        self._grid_separate: bool | None = None

    async def async_step_init(self, user_input=None):
        """Step 1: choose grid mode; show current mode and sensors."""
        if user_input is None:
            current_sep = self._get_current_separate()

            # Current configured sensors for info text
            get_opt = self.config_entry.options.get
            get_dat = self.config_entry.data.get
            cur_grid = get_opt(CONF_GRID_ENTITY) or get_dat(CONF_GRID_ENTITY)
            cur_import = get_opt(CONF_GRID_IMPORT_ENTITY) or get_dat(CONF_GRID_IMPORT_ENTITY)
            cur_export = get_opt(CONF_GRID_EXPORT_ENTITY) or get_dat(CONF_GRID_EXPORT_ENTITY)

            grid_mode = (
                "Separate grid import/export sensors" if current_sep else "Single net grid power sensor"
            )
            if current_sep:
                grid_detail = (
                    f"Import power sensor: {cur_import or '(not set)'}\n"
                    f"Export power sensor: {cur_export or '(not set)'}"
                )
            else:
                grid_detail = f"Grid power sensor: {cur_grid or '(not set)'}"

            schema = vol.Schema(
                {vol.Required(CONF_GRID_SEPARATE, default=current_sep): selector({"boolean": {}})}
            )
            entry_name = (
                self.config_entry.options.get(CONF_NAME)
                or self.config_entry.data.get(CONF_NAME)
                or self.config_entry.title
                or "SolarDelta"
            )
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
                description_placeholders={
                    "entry_name": entry_name,
                    "grid_mode": grid_mode,
                    "grid_detail": grid_detail,
                },
            )

        self._grid_separate = bool(user_input.get(CONF_GRID_SEPARATE, False))
        return await self.async_step_details()

    async def async_step_details(self, user_input=None):
        """Step 2: details; show only relevant grid fields."""
        separate = (
            self._grid_separate
            if self._grid_separate is not None
            else self._get_current_separate()
        )

        schema = self._build_schema(separate)

        entry_name = (
            self.config_entry.options.get(CONF_NAME)
            or self.config_entry.data.get(CONF_NAME)
            or self.config_entry.title
            or "SolarDelta"
        )

        if user_input is None:
            return self.async_show_form(
                step_id="details",
                data_schema=schema,
                description_placeholders={"entry_name": entry_name},
            )

        # Validate according to mode
        errors: dict[str, str] = {}
        if separate:
            if not user_input.get(CONF_GRID_IMPORT_ENTITY):
                errors[CONF_GRID_IMPORT_ENTITY] = "required_if_separate"
            if not user_input.get(CONF_GRID_EXPORT_ENTITY):
                errors[CONF_GRID_EXPORT_ENTITY] = "required_if_separate"
        else:
            if not user_input.get(CONF_GRID_ENTITY):
                errors[CONF_GRID_ENTITY] = "required_if_not_separate"

        # Required fields
        required_keys = [
            CONF_SOLAR_ENTITY,
            CONF_DEVICE_ENTITY,
            CONF_STATUS_ENTITY,
            CONF_STATUS_STRING,
            CONF_RESET_ENTITY,
            CONF_RESET_STRING,
        ]
        for k in required_keys:
            if not user_input.get(k):
                errors[k] = "required"

        if errors:
            return self.async_show_form(
                step_id="details",
                data_schema=schema,
                errors=errors,
                description_placeholders={"entry_name": entry_name},
            )

        # Merge with existing options so hidden values (from the other mode) are preserved
        result = dict(self.config_entry.options)
        result[CONF_GRID_SEPARATE] = separate
        for k, v in user_input.items():
            result[k] = v

        return self.async_create_entry(title="", data=result)

    def _get_current_separate(self) -> bool:
        get_opt = self.config_entry.options.get
        get_dat = self.config_entry.data.get
        val = get_opt(CONF_GRID_SEPARATE)
        if val is None:
            val = get_dat(CONF_GRID_SEPARATE)
        return bool(val or False)

    def _build_schema(self, separate: bool) -> vol.Schema:
        """Options details schema with defaults populated from current config/opts."""
        get_opt = self.config_entry.options.get
        get_dat = self.config_entry.data.get

        cur_solar = get_opt(CONF_SOLAR_ENTITY) or get_dat(CONF_SOLAR_ENTITY)

        cur_grid = get_opt(CONF_GRID_ENTITY) or get_dat(CONF_GRID_ENTITY)
        cur_import = get_opt(CONF_GRID_IMPORT_ENTITY) or get_dat(CONF_GRID_IMPORT_ENTITY)
        cur_export = get_opt(CONF_GRID_EXPORT_ENTITY) or get_dat(CONF_GRID_EXPORT_ENTITY)

        cur_device = get_opt(CONF_DEVICE_ENTITY) or get_dat(CONF_DEVICE_ENTITY)

        cur_status_entity = get_opt(CONF_STATUS_ENTITY) or get_dat(CONF_STATUS_ENTITY)
        cur_status_string = get_opt(CONF_STATUS_STRING) or get_dat(CONF_STATUS_STRING) or ""

        cur_reset_entity = get_opt(CONF_RESET_ENTITY) or get_dat(CONF_RESET_ENTITY)
        cur_reset_string = get_opt(CONF_RESET_STRING) or get_dat(CONF_RESET_STRING) or ""

        cur_scan = get_opt(CONF_SCAN_INTERVAL)
        if cur_scan is None:
            cur_scan = get_dat(CONF_SCAN_INTERVAL)
        if cur_scan is None:
            cur_scan = 0

        entity_selector_any = {"entity": {"domain": ["sensor", "binary_sensor"]}}

        fields: dict = {}

        # Solar
        if cur_solar is not None:
            fields[vol.Required(CONF_SOLAR_ENTITY, default=cur_solar)] = selector(
                {"entity": {"domain": "sensor"}}
            )
        else:
            fields[vol.Required(CONF_SOLAR_ENTITY)] = selector(
                {"entity": {"domain": "sensor"}}
            )

        # Grid (only the active mode’s fields)
        if separate:
            if cur_import is not None:
                fields[
                    vol.Required(CONF_GRID_IMPORT_ENTITY, default=cur_import)
                ] = selector({"entity": {"domain": "sensor"}})
            else:
                fields[vol.Required(CONF_GRID_IMPORT_ENTITY)] = selector(
                    {"entity": {"domain": "sensor"}}
                )

            if cur_export is not None:
                fields[
                    vol.Required(CONF_GRID_EXPORT_ENTITY, default=cur_export)
                ] = selector({"entity": {"domain": "sensor"}})
            else:
                fields[vol.Required(CONF_GRID_EXPORT_ENTITY)] = selector(
                    {"entity": {"domain": "sensor"}}
                )
        else:
            if cur_grid is not None:
                fields[vol.Required(CONF_GRID_ENTITY, default=cur_grid)] = selector(
                    {"entity": {"domain": "sensor"}}
                )
            else:
                fields[vol.Required(CONF_GRID_ENTITY)] = selector(
                    {"entity": {"domain": "sensor"}}
                )

        # Device
        if cur_device is not None:
            fields[vol.Required(CONF_DEVICE_ENTITY, default=cur_device)] = selector(
                {"entity": {"domain": "sensor"}}
            )
        else:
            fields[vol.Required(CONF_DEVICE_ENTITY)] = selector(
                {"entity": {"domain": "sensor"}}
            )

        # Status
        if cur_status_entity is not None:
            fields[
                vol.Required(CONF_STATUS_ENTITY, default=cur_status_entity)
            ] = selector(entity_selector_any)
        else:
            fields[vol.Required(CONF_STATUS_ENTITY)] = selector(entity_selector_any)

        fields[vol.Required(CONF_STATUS_STRING, default=cur_status_string)] = str

        # Reset
        if cur_reset_entity is not None:
            fields[
                vol.Required(CONF_RESET_ENTITY, default=cur_reset_entity)
            ] = selector(entity_selector_any)
        else:
            fields[vol.Required(CONF_RESET_ENTITY)] = selector(entity_selector_any)

        fields[vol.Required(CONF_RESET_STRING, default=cur_reset_string)] = str

        # Scan interval
        fields[vol.Required(CONF_SCAN_INTERVAL, default=cur_scan)] = selector(
            {
                "number": {
                    "min": 0,
                    "max": 86400,
                    "step": 1,
                    "mode": "box",
                    "unit_of_measurement": "s",
                }
            }
        )

        return vol.Schema(fields)
