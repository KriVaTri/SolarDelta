from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "solardelta"
PLATFORMS: list[Platform] = [Platform.SENSOR]

# Config keys
CONF_SOLAR_ENTITY = "solar_entity"
CONF_DEVICE_ENTITY = "device_entity"
CONF_DEVICE_ENTITIES = "device_entities"  # legacy compat (list)
CONF_NAME = "name"
CONF_STATUS_ENTITY = "status_entity"
CONF_STATUS_STRING = "status_string"
CONF_TRIGGER_ENTITY = "trigger_entity"
CONF_TRIGGER_STRING_1 = "trigger_string_1"
