from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "solardelta"
PLATFORMS: list[Platform] = [Platform.SENSOR]

# Config keys
CONF_NAME = "name"
CONF_SOLAR_ENTITY = "solar_entity"
CONF_GRID_ENTITY = "grid_entity"
CONF_DEVICE_ENTITY = "device_entity"
CONF_STATUS_ENTITY = "status_entity"
CONF_STATUS_STRING = "status_string"
CONF_RESET_ENTITY = "reset_entity"
CONF_RESET_STRING = "reset_string"
