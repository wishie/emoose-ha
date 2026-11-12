"""Output switches for the emoose X300 integration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EmooseConfigEntry
from .entity import EmooseEntity
from .hub import EmooseHub
from .protocol import TARGET_AC, TARGET_DC, TARGET_TURBO, Report

# key, name, command target, state function
SWITCHES: tuple[tuple[str, str, int, Callable[[Report], bool]], ...] = (
    ("ac_output_switch", "AC output", TARGET_AC, lambda r: r.ac_output_on),
    ("dc_output_switch", "DC output", TARGET_DC, lambda r: r.dc_output_on),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EmooseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the output switches."""
    hub = entry.runtime_data
    async_add_entities(
        EmooseOutputSwitch(hub, entry.entry_id, key, name, target, state_fn)
        for key, name, target, state_fn in SWITCHES
    )
    # Turbo Boost: same command class as AC/DC (0x12), target 0x09.
    # The app refuses to toggle it unless the AC output is on, so the
    # switch is unavailable while AC is off (see EmooseTurboSwitch).
    async_add_entities([EmooseTurboSwitch(hub, entry.entry_id)])


class EmooseOutputSwitch(EmooseEntity, SwitchEntity):
    """Switch for the AC or DC output; state comes from the station's telemetry."""

    def __init__(
        self,
        hub: EmooseHub,
        entry_id: str,
        key: str,
        name: str,
        target: int,
        state_fn: Callable[[Report], bool],
    ) -> None:
        """Initialise the switch."""
        super().__init__(hub, entry_id, key)
        self._attr_name = name
        self._target = target
        self._state_fn = state_fn

    @property
    def is_on(self) -> bool | None:
        """Return the output state from the latest report."""
        report = self._hub.report
        return None if report is None else self._state_fn(report)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the output on."""
        await self._hub.async_send_command(self._target, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the output off."""
        await self._hub.async_send_command(self._target, 0)

class EmooseTurboSwitch(EmooseEntity, SwitchEntity):
    """Turbo Boost switch; state comes from byte 78 bit 0x02 of the report."""

    _attr_name = "Turbo Boost"
    _attr_icon = "mdi:rocket-launch"

    def __init__(self, hub: EmooseHub, entry_id: str) -> None:
        """Initialise the switch."""
        super().__init__(hub, entry_id, "turbo_boost_switch")

    @property
    def available(self) -> bool:
        """Only available while the station is reporting and AC output is on."""
        report = self._hub.report
        return self._hub.available and report is not None and report.ac_output_on

    @property
    def is_on(self) -> bool | None:
        """Return Turbo Boost state from the latest report."""
        report = self._hub.report
        return None if report is None else report.turbo_boost_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn Turbo Boost on."""
        await self._hub.async_send_command(TARGET_TURBO, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn Turbo Boost off."""
        await self._hub.async_send_command(TARGET_TURBO, 0)
