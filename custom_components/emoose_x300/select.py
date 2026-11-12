"""AC timeout and AC output frequency selects for the emoose X300 integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EmooseConfigEntry
from .entity import EmooseEntity
from .hub import EmooseHub
from .protocol import AC_TIMEOUTS, TARGET_FREQUENCY

# Options in code order: Never, 1 hour, 2 hours, 8 hours, 12 hours.
AC_TIMEOUT_OPTIONS = [AC_TIMEOUTS[code] for code in sorted(AC_TIMEOUTS)]
_OPTION_TO_CODE = {label: code for code, label in AC_TIMEOUTS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EmooseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AC timeout select."""
    hub = entry.runtime_data
    async_add_entities(
        [EmooseAcTimeoutSelect(hub, entry.entry_id), EmooseAcFrequencySelect(hub, entry.entry_id)]
    )


class EmooseAcTimeoutSelect(EmooseEntity, SelectEntity):
    """Select for the AC timeout; state comes from the station's telemetry."""

    _attr_name = "AC timeout"
    _attr_icon = "mdi:timer-outline"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = AC_TIMEOUT_OPTIONS

    def __init__(self, hub: EmooseHub, entry_id: str) -> None:
        """Initialise the select."""
        # Distinct key from the sensor's "ac_timeout" key, so the
        # unique_id does not collide with sensor.emoose_x300_ac_timeout.
        super().__init__(hub, entry_id, "ac_timeout_select")

    @property
    def current_option(self) -> str | None:
        """Return the AC timeout from the latest report."""
        report = self._hub.report
        return None if report is None else report.ac_timeout

    async def async_select_option(self, option: str) -> None:
        """Set the AC timeout on the station."""
        await self._hub.async_send_ac_timeout(_OPTION_TO_CODE[option])

# AC output frequency: report byte 110, 1 = 50 Hz, 2 = 60 Hz, 0 while AC is off.
# Command value = index (0 = 50 Hz, 1 = 60 Hz), NOT the report code (see protocol.py).
AC_FREQUENCY_OPTIONS = ["50 Hz", "60 Hz"]
_FREQUENCY_OPTION_TO_CODE = {"50 Hz": 0, "60 Hz": 1}


class EmooseAcFrequencySelect(EmooseEntity, SelectEntity):
    """Select for the AC output frequency; state comes from the station's telemetry."""

    _attr_name = "AC output frequency"
    _attr_icon = "mdi:sine-wave"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = AC_FREQUENCY_OPTIONS

    def __init__(self, hub: EmooseHub, entry_id: str) -> None:
        """Initialise the select."""
        super().__init__(hub, entry_id, "ac_frequency_select")

    @property
    def available(self) -> bool:
        """Only available while the station is reporting and AC output is on."""
        report = self._hub.report
        return self._hub.available and report is not None and report.ac_output_on

    @property
    def current_option(self) -> str | None:
        """Return the AC frequency from the latest report, or None while AC is off."""
        report = self._hub.report
        if report is None or report.ac_frequency_hz is None:
            return None
        return f"{report.ac_frequency_hz} Hz"

    async def async_select_option(self, option: str) -> None:
        """Set the AC frequency on the station."""
        await self._hub.async_send_command(TARGET_FREQUENCY, _FREQUENCY_OPTION_TO_CODE[option])
