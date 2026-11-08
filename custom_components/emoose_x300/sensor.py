"""Sensors for the emoose X300 integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import EmooseConfigEntry
from .entity import EmooseEntity
from .hub import EmooseHub
from .protocol import Report


@dataclass(frozen=True, kw_only=True)
class EmooseSensorDescription(SensorEntityDescription):
    """Sensor description with a function that reads the value from a report."""

    value_fn: Callable[[Report], StateType]


def _power(key: str, name: str, attr: str) -> EmooseSensorDescription:
    return EmooseSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: getattr(r, attr),
    )


def _temperature(key: str, name: str, attr: str) -> EmooseSensorDescription:
    return EmooseSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: getattr(r, attr),
    )


def _duration(key: str, name: str, attr: str) -> EmooseSensorDescription:
    return EmooseSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: getattr(r, attr),
    )


def _text(key: str, name: str, attr: str, icon: str) -> EmooseSensorDescription:
    return EmooseSensorDescription(
        key=key,
        name=name,
        icon=icon,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda r: getattr(r, attr),
    )


SENSORS: tuple[EmooseSensorDescription, ...] = (
    EmooseSensorDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r.battery_percent,
    ),
    _duration("time_to_empty", "Time to empty", "minutes_to_empty"),
    EmooseSensorDescription(
        key="time_to_empty_hm",
        name="Time to empty (h:mm)",
        icon="mdi:timer-sand",
        value_fn=lambda r: r.time_to_empty_hm,
    ),
    _duration("time_to_full", "Time to full", "minutes_to_full"),
    EmooseSensorDescription(
        key="time_to_full_hm",
        name="Time to full (h:mm)",
        icon="mdi:timer-sand",
        value_fn=lambda r: r.time_to_full_hm,
    ),
    _power("input_power", "Input power", "input_power"),
    _power("ac_input_power", "AC input power", "ac_input_power"),
    _power("dc_input_power", "DC input power", "dc_input_power"),
    _power("output_power", "Output power", "output_power"),
    _power("ac_output_power", "AC output power", "ac_output_power"),
    _power("dc_output_power", "DC output power", "dc_output_power"),
    _power("usbc1_power", "USB-C 1 output power", "usbc1_power"),
    _power("usbc2_power", "USB-C 2 output power", "usbc2_power"),
    _power("usba1_power", "USB-A 1 output power", "usba1_power"),
    _power("usba2_power", "USB-A 2 output power", "usba2_power"),
    EmooseSensorDescription(
        key="battery_voltage",
        name="Battery voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r.battery_voltage,
    ),
    EmooseSensorDescription(
        key="battery_current",
        name="Battery current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r.battery_current,
    ),
    _power("battery_power", "Battery power", "battery_power"),
    _temperature("temperature_1", "Temperature 1", "temperature_1"),
    _temperature("temperature_2", "Temperature 2", "temperature_2"),
    _temperature("temperature_3", "Temperature 3", "temperature_3"),
    _text("serial", "Serial number", "serial", "mdi:identifier"),
    _text("software_version", "Software version", "software_version", "mdi:chip"),
    _text("hardware_version", "Hardware version", "hardware_version", "mdi:chip"),
    _text("screen_standby", "Screen standby", "screen_standby", "mdi:monitor"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EmooseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    hub = entry.runtime_data
    async_add_entities(
        EmooseSensor(hub, entry.entry_id, description) for description in SENSORS
    )


class EmooseSensor(EmooseEntity, SensorEntity):
    """A value read from the station's report."""

    entity_description: EmooseSensorDescription

    def __init__(
        self, hub: EmooseHub, entry_id: str, description: EmooseSensorDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(hub, entry_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the value from the latest report."""
        report = self._hub.report
        return None if report is None else self.entity_description.value_fn(report)
