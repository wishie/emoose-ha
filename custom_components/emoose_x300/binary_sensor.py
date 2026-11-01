"""Binary sensors for the emoose X300 integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EmooseConfigEntry
from .entity import EmooseEntity
from .hub import EmooseHub
from .protocol import Report


@dataclass(frozen=True, kw_only=True)
class EmooseBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description with a function that reads a flag from a report."""

    value_fn: Callable[[Report], bool]


BINARY_SENSORS: tuple[EmooseBinarySensorDescription, ...] = (
    EmooseBinarySensorDescription(
        key="ac_output",
        name="AC output",
        value_fn=lambda r: r.ac_output_on,
    ),
    EmooseBinarySensorDescription(
        key="dc_output",
        name="DC output",
        value_fn=lambda r: r.dc_output_on,
    ),
    EmooseBinarySensorDescription(
        key="charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda r: r.charging,
    ),
    # Likely, not confirmed: seen once, with the charger connected and no current flowing.
    EmooseBinarySensorDescription(
        key="charge_complete",
        name="Charge complete (likely)",
        value_fn=lambda r: r.charge_complete,
    ),
    EmooseBinarySensorDescription(
        key="usbc1_active",
        name="USB-C 1 active",
        value_fn=lambda r: r.usbc1_active,
    ),
    EmooseBinarySensorDescription(
        key="usbc2_active",
        name="USB-C 2 active",
        value_fn=lambda r: r.usbc2_active,
    ),
    EmooseBinarySensorDescription(
        key="usba1_active",
        name="USB-A 1 active",
        value_fn=lambda r: r.usba1_active,
    ),
    EmooseBinarySensorDescription(
        key="usba2_active",
        name="USB-A 2 active",
        value_fn=lambda r: r.usba2_active,
    ),
    EmooseBinarySensorDescription(
        key="sound",
        name="Sound",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda r: r.sound_on,
    ),
    EmooseBinarySensorDescription(
        key="eco_mode",
        name="ECO mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda r: r.eco_on,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EmooseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    hub = entry.runtime_data
    async_add_entities(
        EmooseBinarySensor(hub, entry.entry_id, description)
        for description in BINARY_SENSORS
    )


class EmooseBinarySensor(EmooseEntity, BinarySensorEntity):
    """A flag read from the station's report."""

    entity_description: EmooseBinarySensorDescription

    def __init__(
        self,
        hub: EmooseHub,
        entry_id: str,
        description: EmooseBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(hub, entry_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the flag from the latest report."""
        report = self._hub.report
        return None if report is None else self.entity_description.value_fn(report)
