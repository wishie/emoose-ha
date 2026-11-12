"""AC timeout select for the emoose X300 integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EmooseConfigEntry
from .entity import EmooseEntity
from .hub import EmooseHub
from .protocol import AC_TIMEOUTS

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
    async_add_entities([EmooseAcTimeoutSelect(hub, entry.entry_id)])


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
