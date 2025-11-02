    coordinator = SolarDeltaCoordinator(
        hass=hass,
        solar_entity=solar_entity,
        device_entity=device_entity,
        status_entity=status_entity,
        status_string=status_string,
        trigger_entity=trigger_entity,
        trigger_string_1=trigger_string_1,
        scan_interval_seconds=int(scan_interval or 0),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "name": entry_name,
        "coordinator": coordinator,
        "trigger_entity": trigger_entity,  # ensure session sensor can monitor trigger
    }
