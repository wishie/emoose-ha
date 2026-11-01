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
from .protocol import TARGET_AC, TARGET_DC, Report

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
