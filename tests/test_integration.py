"""Integration tests: run the integration inside a real (test) Home Assistant core.

These need ``pytest-homeassistant-custom-component``; the pure protocol tests do not.
"""

from datetime import timedelta

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from frames import FRAMES
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
    async_fire_time_changed,
)

from custom_components.emoose_x300.const import CONF_TOPIC_PREFIX, DOMAIN
from custom_components.emoose_x300.protocol import TARGET_AC, TARGET_DC, build_command

PREFIX = "$oc/devices/3768"
REPORT_TOPIC = f"{PREFIX}/report/request"
COMMAND_TOPIC = f"{PREFIX}/command/request"


async def setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TOPIC_PREFIX: PREFIX}, unique_id=PREFIX)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def state(hass: HomeAssistant, entity_id: str) -> str:
    found = hass.states.get(entity_id)
    assert found is not None, f"{entity_id} does not exist"
    return found.state


async def test_entities_unavailable_until_first_report(hass, mqtt_mock):
    await setup_entry(hass)
    assert state(hass, "sensor.emoose_x300_battery") == "unavailable"
    assert state(hass, "switch.emoose_x300_ac_output") == "unavailable"


async def test_idle_report_populates_entities(hass, mqtt_mock):
    await setup_entry(hass)
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["idle_95"])
    await hass.async_block_till_done()

    assert state(hass, "sensor.emoose_x300_battery") == "95"
    assert state(hass, "sensor.emoose_x300_battery_voltage") == "19.95"
    assert state(hass, "sensor.emoose_x300_battery_current") == "-0.04"
    assert state(hass, "sensor.emoose_x300_temperature_1") == "28.0"
    assert state(hass, "sensor.emoose_x300_time_to_empty") == "unknown"
    assert state(hass, "sensor.emoose_x300_serial_number") == "G9US642400164"
    assert state(hass, "sensor.emoose_x300_software_version") == "23.10.12"
    assert state(hass, "sensor.emoose_x300_hardware_version") == "10.21.11"
    assert state(hass, "binary_sensor.emoose_x300_ac_output") == "off"
    assert state(hass, "binary_sensor.emoose_x300_sound") == "on"
    assert state(hass, "switch.emoose_x300_ac_output") == "off"


async def test_dc_load_report(hass, mqtt_mock):
    await setup_entry(hass)
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["dc_8w"])
    await hass.async_block_till_done()

    assert state(hass, "sensor.emoose_x300_output_power") == "8.0"
    assert state(hass, "sensor.emoose_x300_dc_output_power") == "8.0"
    assert state(hass, "sensor.emoose_x300_ac_output_power") == "0.0"
    assert state(hass, "sensor.emoose_x300_time_to_empty") == "1879"
    assert state(hass, "sensor.emoose_x300_time_to_empty_h_mm") == "31:19"
    assert state(hass, "binary_sensor.emoose_x300_dc_output") == "on"
    assert state(hass, "switch.emoose_x300_dc_output") == "on"
    assert state(hass, "switch.emoose_x300_ac_output") == "off"


async def test_charging_report(hass, mqtt_mock):
    await setup_entry(hass)
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["ac_charge_120w"])
    await hass.async_block_till_done()

    assert state(hass, "sensor.emoose_x300_input_power") == "120.0"
    assert state(hass, "sensor.emoose_x300_battery_power") == "113.5"
    assert state(hass, "sensor.emoose_x300_time_to_full") == "74"
    assert state(hass, "sensor.emoose_x300_time_to_full_h_mm") == "01:14"
    assert state(hass, "binary_sensor.emoose_x300_charging") == "on"
    assert state(hass, "binary_sensor.emoose_x300_charge_complete_likely") == "off"


async def test_solar_charging_report(hass, mqtt_mock):
    await setup_entry(hass)
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["solar_charge_120w"])
    await hass.async_block_till_done()

    assert state(hass, "sensor.emoose_x300_input_power") == "120.0"
    assert state(hass, "sensor.emoose_x300_dc_input_power") == "120.0"
    assert state(hass, "sensor.emoose_x300_ac_input_power") == "0.0"
    assert state(hass, "binary_sensor.emoose_x300_charging") == "on"


async def test_auto_fan_setting(hass, mqtt_mock):
    await setup_entry(hass)
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["auto_fan_on_solar_charging"])
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor.emoose_x300_auto_fan") == "on"
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["auto_fan_off_solar_charging"])
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor.emoose_x300_auto_fan") == "off"


async def test_invalid_payloads_are_ignored(hass, mqtt_mock):
    await setup_entry(hass)
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["idle_95"])
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, REPORT_TOPIC, "garbage")
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["idle_95"][:-12] + "AT+MQTTPUB=0")
    await hass.async_block_till_done()
    # Still showing the last good report.
    assert state(hass, "sensor.emoose_x300_battery") == "95"


async def test_entities_go_unavailable_when_station_is_silent(hass, mqtt_mock):
    await setup_entry(hass)
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["idle_95"])
    await hass.async_block_till_done()
    assert state(hass, "sensor.emoose_x300_battery") == "95"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=45))
    await hass.async_block_till_done()
    assert state(hass, "sensor.emoose_x300_battery") == "unavailable"

    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["idle_95"])
    await hass.async_block_till_done()
    assert state(hass, "sensor.emoose_x300_battery") == "95"


async def test_switches_publish_raw_command_frames(hass, mqtt_mock):
    await setup_entry(hass)
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["idle_95"])
    await hass.async_block_till_done()

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.emoose_x300_ac_output"}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.emoose_x300_dc_output"}, blocking=True
    )

    published = [call.args for call in mqtt_mock.async_publish.call_args_list]
    assert (COMMAND_TOPIC, build_command(0x20, TARGET_AC, 1), 0, False) in published
    assert (COMMAND_TOPIC, build_command(0x21, TARGET_DC, 0), 0, False) in published


async def test_unload_and_reload(hass, mqtt_mock):
    entry = await setup_entry(hass)
    async_fire_mqtt_message(hass, REPORT_TOPIC, FRAMES["idle_95"])
    await hass.async_block_till_done()
    hub = entry.runtime_data
    assert hub._cancel_expiry is not None  # availability timer is running

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    # Our own timer and subscription are released on unload.
    assert hub._cancel_expiry is None
    assert hub._unsubscribe is None
    assert state(hass, "sensor.emoose_x300_battery") == "unavailable"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_config_flow(hass, mqtt_mock):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOPIC_PREFIX: "emoose/#"}
    )
    assert bad["type"] is FlowResultType.FORM
    assert bad["errors"] == {"base": "invalid_prefix"}

    created = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOPIC_PREFIX: "emoose/x300/"}
    )
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["data"] == {CONF_TOPIC_PREFIX: "emoose/x300"}  # trailing slash stripped

    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    dup = await hass.config_entries.flow.async_configure(
        again["flow_id"], {CONF_TOPIC_PREFIX: "emoose/x300"}
    )
    assert dup["type"] is FlowResultType.ABORT
    assert dup["reason"] == "already_configured"
