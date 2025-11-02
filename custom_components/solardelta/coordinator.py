class SolarDeltaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        solar_entity: str,
        device_entity: str,
        status_entity: Optional[str] = None,
        status_string: Optional[str] = None,
        trigger_entity: Optional[str] = None,
        trigger_string_1: Optional[str] = None,
        scan_interval_seconds: int = 0,
    ) -> None:
        super().__init__(hass, name="solardelta", update_interval=None)
        self.hass = hass
        self._solar_entity = solar_entity
        self._device_entity = device_entity
        self._status_entity = status_entity
        self._status_string = status_string
        self._trigger_entity = trigger_entity
        self._trigger_string_1 = trigger_string_1
        self._periodic = bool(scan_interval_seconds and scan_interval_seconds > 0)
        self._interval_seconds = int(scan_interval_seconds or 0)
        self._unsub: list[callable] = []

    @property
    def trigger_string(self) -> Optional[str]:
        """Raw configured trigger match string (may be None)."""
        return self._trigger_string_1
