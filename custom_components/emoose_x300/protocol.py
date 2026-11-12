"""Decoder and encoder for the emoose X300 MQTT protocol.

Pure Python with no Home Assistant imports, so it can be unit-tested on its own.

Frame layout (reverse engineered from captured traffic, see the README):

* Every frame starts with ``55 AA``, ends with ``33 CC``, and has a CRC-16/ARC checksum
  (big-endian) in the two bytes before the end marker, computed over everything before it.
* The station publishes a 122-byte *report* every few seconds as an ASCII-hex string.
* Commands are 13 raw bytes: ``55 AA 00 0D <seq> 00 12 <target> <value> <crc> 33 CC``.
* Frequency command (confirmed in HA): same 13-byte form as AC/DC/Turbo,
  target 0x02, value = index (0 = 50 Hz, 1 = 60 Hz), NOT the report code
  (report byte 110 is 1 = 50 Hz, 2 = 60 Hz). Proved: HA sent value 1 with
  seq 0x60 while on 60 Hz -> no change (value 1 = current); HA sent value 0
  with seq 0x61 -> byte 110 went 2 -> 1 (60 -> 50 Hz). The earlier HA
  failure (value 2, seq 0x20) was the invalid value, not the seq range.
* The AC timeout command is 12 raw bytes:
  ``55 AA 00 0C <seq> 00 18 <value> <crc> 33 CC`` (see ``build_ac_timeout_command``).
  The app sends this with seq bytes in the 0x40.. range (captured 0x45..0x49, 0x54);
  a seq in the 0x20..0x2F range is acked (0x88) but ignored by the station.
"""

from __future__ import annotations

from dataclasses import dataclass

FRAME_START = b"\x55\xaa"
FRAME_END = b"\x33\xcc"
REPORT_LENGTH = 122
REPORT_HEX_LENGTH = REPORT_LENGTH * 2

TARGET_DC = 0x06
TARGET_AC = 0x07
TARGET_TURBO = 0x09  # Turbo Boost; only toggleable while the AC output is on
TARGET_FREQUENCY = 0x02  # AC output frequency: value 0 = 50 Hz, 1 = 60 Hz (confirmed)

# Sequence bytes 0x20..0x2F were verified to be accepted by the station.
COMMAND_SEQ_MIN = 0x20
COMMAND_SEQ_COUNT = 16

# AC timeout commands use a separate seq range. The app uses 0x40.. (captured
# 0x45..0x49, 0x54); HA sending 0x20..0x2F got a 0x88 ack but no change.
AC_TIMEOUT_SEQ_MIN = 0x40
AC_TIMEOUT_SEQ_COUNT = 16

NONE_MINUTES = 0xFFFF

# AC output frequency, byte 110 (0 while the AC output is off).
AC_FREQUENCIES_HZ = {1: 50, 2: 60}

# AC timeout setting, byte 82 (confirmed by changing it in the app).
# Codes confirmed from captured frames, byte 82 stepping 2 -> 0 -> 1 -> 2 -> 3 -> 4:
# 0 = Never, 1 = 1 hour, 2 = 2 hours, 3 = 8 hours, 4 = 12 hours.
# The command value is the same code (NOT hours): the app sends value 0x03 for 8h,
# proved by its CRC 0x3985 for seq 0x54. Verified in HA: seq 0x42 / value 2
# changed byte 82 from 3 to 2 (report byte 4 echoed seq 0x42).
AC_TIMEOUTS = {0: "Never", 1: "1 hour", 2: "2 hours", 3: "8 hours", 4: "12 hours"}

# Screen standby setting, byte 81 of the report (confirmed by changing it in the app).
SCREEN_STANDBY = {0: "Never", 1: "30 seconds", 2: "1 minute", 3: "5 minutes", 4: "30 minutes"}


def crc16_arc(data: bytes) -> int:
    """CRC-16/ARC (poly 0x8005 reflected, init 0)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def next_sequence(seq: int) -> int:
    """Next command sequence byte, wrapping inside the verified range."""
    return COMMAND_SEQ_MIN + ((seq - COMMAND_SEQ_MIN + 1) % COMMAND_SEQ_COUNT)


def build_command(seq: int, target: int, value: int) -> bytes:
    """Build a raw command frame to switch an output / Turbo Boost on (1) or off (0)."""
    if target not in (TARGET_AC, TARGET_DC, TARGET_TURBO, TARGET_FREQUENCY):
        raise ValueError(f"unknown command target {target!r}")
    if target == TARGET_FREQUENCY:
        if value not in (0, 1):
            raise ValueError(f"frequency value must be 0 (50 Hz) or 1 (60 Hz), got {value!r}")
    elif value not in (0, 1):
        raise ValueError(f"value must be 0 or 1, got {value!r}")
    body = bytes([0x55, 0xAA, 0x00, 0x0D, seq & 0xFF, 0x00, 0x12, target, value])
    return body + crc16_arc(body).to_bytes(2, "big") + FRAME_END


def build_ac_timeout_command(seq: int, value: int) -> bytes:
    """Build a raw command frame to set the AC timeout (byte 82).

    Verified against captured frames: seq 0x47, value 2 (2 hours)
    gives CRC-16/ARC 0x7D40; seq 0x54, value 3 (8 hours) gives 0x3985.
    """
    if value not in AC_TIMEOUTS:
        raise ValueError(f"unknown AC timeout code {value!r}")
    body = bytes([0x55, 0xAA, 0x00, 0x0C, seq & 0xFF, 0x00, 0x18, value])
    frame = body + crc16_arc(body).to_bytes(2, "big") + FRAME_END
    return frame


def next_ac_timeout_sequence(seq: int) -> int:
    """Next AC timeout sequence byte, wrapping inside its verified range."""
    return AC_TIMEOUT_SEQ_MIN + (
        (seq - AC_TIMEOUT_SEQ_MIN + 1) % AC_TIMEOUT_SEQ_COUNT
    )


def format_hm(minutes: int | None) -> str | None:
    """Format minutes as HH:MM the way the unit's own display does."""
    if minutes is None:
        return None
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True, slots=True)
class Report:
    """One decoded telemetry report."""

    serial: str
    device_id: int
    software_version: str
    hardware_version: str

    battery_percent: int
    minutes_to_empty: int | None
    minutes_to_full: int | None

    input_power: float
    ac_input_power: float
    dc_input_power: float  # solar / 12 V charging input
    output_power: float
    ac_output_power: float
    dc_output_power: float
    usbc1_power: float
    usbc2_power: float
    usba1_power: float
    usba2_power: float

    battery_voltage: float
    battery_current: float  # positive = charging, negative = discharging

    temperature_1: float
    temperature_2: float
    temperature_3: float

    ac_output_on: bool
    dc_output_on: bool
    ac_charging: bool
    dc_charging: bool  # charging from DC / solar
    charge_complete: bool  # likely, not confirmed (see README)
    screen_standby_code: int  # byte 81; see SCREEN_STANDBY
    ac_timeout_code: int  # byte 82; see AC_TIMEOUTS
    ac_frequency_code: int  # byte 110: 0 AC off, 1 = 50 Hz, 2 = 60 Hz
    sound_on: bool
    auto_fan_on: bool  # the Auto-Fan setting, not whether the fans are spinning
    eco_on: bool
    turbo_boost_on: bool  # byte 78, bit 0x02; only toggleable while AC output is on
    usbc1_active: bool
    usbc2_active: bool
    usba1_active: bool
    usba2_active: bool

    @property
    def ac_frequency_hz(self) -> int | None:
        """AC output frequency in Hz, or None while the AC output is off (or the code is unknown)."""
        return AC_FREQUENCIES_HZ.get(self.ac_frequency_code)

    @property
    def ac_timeout(self) -> str:
        """The AC timeout setting as text; unknown codes are shown as "Unknown (n)"."""
        return AC_TIMEOUTS.get(self.ac_timeout_code, f"Unknown ({self.ac_timeout_code})")

    @property
    def screen_standby(self) -> str:
        """The screen standby setting as text; unknown codes are shown as "Unknown (n)"."""
        return SCREEN_STANDBY.get(
            self.screen_standby_code, f"Unknown ({self.screen_standby_code})"
        )

    @property
    def charging(self) -> bool:
        """True while charging from AC or from DC / solar."""
        return self.ac_charging or self.dc_charging

    @property
    def battery_power(self) -> float:
        """Battery voltage x current in watts; negative while discharging."""
        return round(self.battery_voltage * self.battery_current, 1)

    @property
    def time_to_empty_hm(self) -> str | None:
        """Time to empty as HH:MM."""
        return format_hm(self.minutes_to_empty)

    @property
    def time_to_full_hm(self) -> str | None:
        """Time to full as HH:MM."""
        return format_hm(self.minutes_to_full)


def _u16(frame: bytes, offset: int) -> int:
    return int.from_bytes(frame[offset : offset + 2], "big")


def _s16(frame: bytes, offset: int) -> int:
    return int.from_bytes(frame[offset : offset + 2], "big", signed=True)


def _minutes(frame: bytes, offset: int) -> int | None:
    value = _u16(frame, offset)
    return None if value == NONE_MINUTES else value


def _watts(frame: bytes, offset: int) -> float:
    return _u16(frame, offset) / 10


def _celsius(frame: bytes, offset: int) -> float:
    # The unit reports tenths of a kelvin. Degrees C x 10 is raw - 2731.5; rounding half up
    # to a tenth gives raw - 2731, which avoids floating point noise.
    return (_u16(frame, offset) - 2731) / 10


def _bit(frame: bytes, offset: int, mask: int) -> bool:
    return bool(frame[offset] & mask)


def _version(frame: bytes, offset: int) -> str:
    # Shown on the unit's screen as byte[offset+2].byte[offset].byte[offset+1].
    return f"{frame[offset + 2]}.{frame[offset]}.{frame[offset + 1]}"


def parse_report(payload: str | bytes | bytearray) -> Report | None:
    """Decode a telemetry payload, or return None if it is not a valid report."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            text = bytes(payload).decode("ascii")
        except UnicodeDecodeError:
            return None
    else:
        text = payload
    text = text.strip()
    if len(text) < REPORT_HEX_LENGTH:
        return None
    try:
        frame = bytes.fromhex(text[:REPORT_HEX_LENGTH])
    except ValueError:
        return None
    if (
        frame[:2] != FRAME_START
        or frame[-2:] != FRAME_END
        or _u16(frame, 2) != REPORT_LENGTH
        or crc16_arc(frame[:-4]) != _u16(frame, 118)
    ):
        return None

    try:
        serial = frame[7:20].decode("ascii")
    except UnicodeDecodeError:
        serial = frame[7:20].hex()

    return Report(
        serial=serial,
        device_id=_u16(frame, 96),
        software_version=_version(frame, 99),
        hardware_version=_version(frame, 104),
        battery_percent=frame[32],
        minutes_to_empty=_minutes(frame, 33),
        minutes_to_full=_minutes(frame, 35),
        input_power=_watts(frame, 37),
        ac_input_power=_watts(frame, 41),
        dc_input_power=_watts(frame, 43),
        output_power=_watts(frame, 39),
        ac_output_power=_watts(frame, 45),
        dc_output_power=_watts(frame, 47),
        usbc1_power=_watts(frame, 51),
        usbc2_power=_watts(frame, 53),
        usba1_power=_watts(frame, 55),
        usba2_power=_watts(frame, 57),
        battery_voltage=_u16(frame, 73) / 100,
        battery_current=_s16(frame, 75) / 100,
        temperature_1=_celsius(frame, 63),
        temperature_2=_celsius(frame, 65),
        temperature_3=_celsius(frame, 67),
        ac_output_on=_bit(frame, 77, 0x02),
        dc_output_on=_bit(frame, 77, 0x04),
        ac_charging=_bit(frame, 77, 0x10),
        dc_charging=_bit(frame, 77, 0x20),
        charge_complete=_bit(frame, 77, 0x40),
        screen_standby_code=frame[81],
        ac_timeout_code=frame[82],
        ac_frequency_code=frame[110],
        sound_on=_bit(frame, 78, 0x01),
        auto_fan_on=_bit(frame, 78, 0x08),
        eco_on=_bit(frame, 79, 0x40),
        turbo_boost_on=_bit(frame, 78, 0x02),
        usbc1_active=_bit(frame, 79, 0x01),
        usbc2_active=_bit(frame, 79, 0x02),
        usba1_active=_bit(frame, 79, 0x10),
        usba2_active=_bit(frame, 79, 0x20),
    )
