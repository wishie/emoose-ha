"""Tests for the emoose X300 protocol module, using frames captured from a real unit."""

import dataclasses
import importlib.util
import pathlib
import sys

import pytest

# Load protocol.py directly so the tests do not need Home Assistant installed.
_PATH = pathlib.Path(__file__).parent.parent / "custom_components" / "emoose_x300" / "protocol.py"
_SPEC = importlib.util.spec_from_file_location("emoose_protocol", _PATH)
protocol = importlib.util.module_from_spec(_SPEC)
sys.modules["emoose_protocol"] = protocol
_SPEC.loader.exec_module(protocol)

from frames import COMMANDS, FRAMES


def report(name):
    parsed = protocol.parse_report(FRAMES[name])
    assert parsed is not None, f"{name} failed to parse"
    return parsed


def test_crc_check_value():
    # Standard CRC-16/ARC check value.
    assert protocol.crc16_arc(b"123456789") == 0xBB3D


@pytest.mark.parametrize("name", sorted(FRAMES))
def test_every_captured_frame_is_valid(name):
    assert protocol.parse_report(FRAMES[name]) is not None


@pytest.mark.parametrize("name", sorted(FRAMES))
def test_static_fields(name):
    r = report(name)
    assert r.serial == "G9US642400164"
    assert r.device_id == 3768
    assert r.software_version == "23.10.12"
    assert r.hardware_version == "10.21.11"


def test_idle():
    r = report("idle_95")
    assert r.battery_percent == 95
    assert r.minutes_to_empty is None
    assert r.minutes_to_full is None
    assert r.output_power == 0
    assert r.battery_voltage == pytest.approx(19.95)
    assert r.battery_current == pytest.approx(-0.04)
    assert (r.temperature_1, r.temperature_2, r.temperature_3) == (28.0, 25.0, 25.0)
    assert not any([r.ac_output_on, r.dc_output_on, r.charging, r.charge_complete, r.eco_on])
    assert r.sound_on
    assert r.time_to_empty_hm is None


def test_ac_output_on_idle():
    r = report("ac_on_idle")
    assert r.ac_output_on and not r.dc_output_on
    assert r.battery_current == pytest.approx(-0.38)
    assert r.battery_power == pytest.approx(-7.6)


def test_ac_load_2w():
    r = report("ac_2w")
    assert r.ac_output_on
    assert r.output_power == pytest.approx(2.0)
    assert r.ac_output_power == pytest.approx(2.0)
    assert r.dc_output_power == 0
    assert r.minutes_to_empty == 5970
    assert r.time_to_empty_hm == "99:30"
    assert r.battery_power == pytest.approx(-12.7)


def test_dc_load_8w():
    r = report("dc_8w")
    assert r.dc_output_on and not r.ac_output_on
    assert r.output_power == pytest.approx(8.0)
    assert r.dc_output_power == pytest.approx(8.0)
    assert r.ac_output_power == 0
    assert r.minutes_to_empty == 1879
    assert r.battery_percent == 93


@pytest.mark.parametrize(
    ("name", "power_attr", "watts", "active_attr"),
    [
        ("usbc1_8w", "usbc1_power", 8.0, "usbc1_active"),
        ("usbc2_3w", "usbc2_power", 3.0, "usbc2_active"),
        ("usba1_6w", "usba1_power", 6.0, "usba1_active"),
        ("usba2_4w_usba1_still_flagged", "usba2_power", 4.0, "usba2_active"),
    ],
)
def test_usb_ports(name, power_attr, watts, active_attr):
    r = report(name)
    assert getattr(r, power_attr) == pytest.approx(watts)
    assert getattr(r, active_attr)
    assert r.output_power == pytest.approx(watts)
    # No other port reports power.
    others = {"usbc1_power", "usbc2_power", "usba1_power", "usba2_power"} - {power_attr}
    assert all(getattr(r, other) == 0 for other in others)


def test_usba1_flag_lingers_after_unplug():
    # Captured just after USB-A 1 was unplugged: its flag was still set, only USB-A 2 had power.
    r = report("usba2_4w_usba1_still_flagged")
    assert r.usba1_active and r.usba2_active
    assert r.usba1_power == 0


def test_ac_charging_120w():
    r = report("ac_charge_120w")
    assert r.charging and not r.charge_complete
    assert r.battery_percent == 31
    assert r.input_power == pytest.approx(120.0)
    assert r.ac_input_power == pytest.approx(120.0)
    assert r.minutes_to_full == 74
    assert r.time_to_full_hm == "01:14"
    assert r.minutes_to_empty is None
    assert r.battery_voltage == pytest.approx(20.31)
    assert r.battery_current == pytest.approx(5.59)
    assert r.battery_power == pytest.approx(113.5)


def test_solar_charging_120w():
    r = report("solar_charge_120w")
    assert r.dc_charging and not r.ac_charging and r.charging
    assert not r.charge_complete
    assert r.battery_percent == 27
    assert r.input_power == pytest.approx(120.0)
    assert r.dc_input_power == pytest.approx(120.0)
    assert r.ac_input_power == 0
    assert r.minutes_to_full == 79
    assert r.battery_voltage == pytest.approx(20.27)
    assert r.battery_current == pytest.approx(5.68)
    assert r.battery_power == pytest.approx(115.1)


def test_ac_charging_uses_ac_flag_only():
    r = report("ac_charge_120w")
    assert r.ac_charging and not r.dc_charging and r.charging
    assert r.dc_input_power == 0


def test_auto_fan_setting_toggle():
    # Captured before and after turning Auto-Fan off in the app; only byte 78 bit 0x08 moved
    # (apart from the solar charging values, which were varying on their own).
    on = report("auto_fan_on_solar_charging")
    off = report("auto_fan_off_solar_charging")
    assert on.auto_fan_on and not off.auto_fan_on
    assert on.sound_on and off.sound_on  # sound untouched
    assert on.dc_charging and off.dc_charging
    # Frames without the setting changed all had Auto-Fan on.
    assert all(report(n).auto_fan_on for n in ("idle_95", "ac_charge_120w", "solar_charge_120w"))


@pytest.mark.parametrize(
    ("name", "code", "label"),
    [
        ("screen_never", 0, "Never"),
        ("screen_30s", 1, "30 seconds"),
        ("screen_1min", 2, "1 minute"),
        ("screen_30min", 4, "30 minutes"),
        ("idle_95", 3, "5 minutes"),  # every frame captured before the setting was changed
    ],
)
def test_screen_standby_codes(name, code, label):
    r = report(name)
    assert r.screen_standby_code == code
    assert r.screen_standby == label


def test_temperature_1_can_read_below_25():
    # Not clamped at 25.0 C: this frame reads 24.0 while temperatures 2 and 3 stay at 25.0.
    r = report("screen_30min")
    assert (r.temperature_1, r.temperature_2, r.temperature_3) == (24.0, 25.0, 25.0)


def test_unknown_screen_standby_code_is_shown_as_unknown():
    r = report("idle_95")
    assert dataclasses.replace(r, screen_standby_code=9).screen_standby == "Unknown (9)"


def test_eco_and_sound_toggles():
    assert report("eco_on").eco_on
    assert not report("eco_off").eco_on
    assert report("sound_on").sound_on
    assert not report("sound_off").sound_on


def test_charge_complete_cycle():
    done = report("charge_complete")
    assert done.charging and done.charge_complete
    assert done.battery_percent == 100
    assert done.minutes_to_full == 0
    assert done.battery_current == 0

    # Still at 100% but current flowing: charging flag, not "complete".
    flowing = report("charging_at_100")
    assert flowing.charging and not flowing.charge_complete
    assert flowing.battery_current == pytest.approx(5.63)
    # The unit reports 0 W input at 100% even while current flows; battery power is the real flow.
    assert flowing.input_power == 0
    assert flowing.battery_power == pytest.approx(115.9)

    unplugged = report("unplugged_at_100")
    assert not unplugged.charging and not unplugged.charge_complete
    assert unplugged.minutes_to_full is None


def test_accepts_bytes_whitespace_and_trailing_junk():
    text = FRAMES["idle_95"]
    assert protocol.parse_report(text.encode()) is not None
    assert protocol.parse_report("  " + text + "\n") is not None
    assert protocol.parse_report(text.lower()) is not None
    assert protocol.parse_report(text + "AT+MQTTPUB=0") is not None


def test_rejects_corrupt_frames():
    good = FRAMES["idle_95"]
    # The WiFi module once glued "AT+MQTTPUB=0" into the end of a payload.
    assert protocol.parse_report(good[:-12] + "AT+MQTTPUB=0") is None
    assert protocol.parse_report(good[:-10]) is None  # truncated
    assert protocol.parse_report("zz" * 122) is None  # not hex
    assert protocol.parse_report("") is None
    assert protocol.parse_report(b"\xff\xfe") is None
    flipped = good[:80] + ("0" if good[80] != "0" else "1") + good[81:]
    assert protocol.parse_report(flipped) is None  # bad checksum
    assert protocol.parse_report("00" + good[2:]) is None  # bad start marker


@pytest.mark.parametrize(("key", "expected"), sorted(COMMANDS.items()))
def test_build_command_matches_captured_commands(key, expected):
    seq, target, value = key
    assert protocol.build_command(seq, target, value).hex() == expected


def test_build_command_validation():
    with pytest.raises(ValueError):
        protocol.build_command(0x20, 0x99, 1)
    with pytest.raises(ValueError):
        protocol.build_command(0x20, protocol.TARGET_AC, 2)


def test_sequence_wraps_inside_verified_range():
    seq = protocol.COMMAND_SEQ_MIN
    seen = []
    for _ in range(protocol.COMMAND_SEQ_COUNT * 2):
        seen.append(seq)
        seq = protocol.next_sequence(seq)
    assert set(seen) == set(range(0x20, 0x30))
    assert protocol.next_sequence(0x2F) == 0x20


def test_format_hm():
    assert protocol.format_hm(None) is None
    assert protocol.format_hm(5) == "00:05"
    assert protocol.format_hm(1476) == "24:36"
    assert protocol.format_hm(6000) == "100:00"
