"""Decoder and encoder for the emoose X300 MQTT protocol.

Pure Python with no Home Assistant imports, so it can be unit-tested on its own.

Frame layout (reverse engineered from captured traffic, see the README):

* Every frame starts with ``55 AA``, ends with ``33 CC``, and has a CRC-16/ARC checksum
  (big-endian) in the two bytes before the end marker, computed over everything before it.
* The station publishes a 122-byte *report* every few seconds as an ASCII-hex string.
* Commands are 13 raw bytes: ``55 AA 00 0D <seq> 00 12 <target> <value> <crc> 33 CC``.
"""

from __future__ import annotations

from dataclasses import dataclass

FRAME_START = b"\x55\xaa"
FRAME_END = b"\x33\xcc"
REPORT_LENGTH = 122
REPORT_HEX_LENGTH = REPORT_LENGTH * 2

TARGET_DC = 0x06
TARGET_AC = 0x07

# Sequence bytes 0x20..0x2F were verified to be accepted by the station.
COMMAND_SEQ_MIN = 0x20
COMMAND_SEQ_COUNT = 16

NONE_MINUTES = 0xFFFF


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
    """Build a raw command frame to switch an output on (1) or off (0)."""
    if target not in (TARGET_AC, TARGET_DC):
        raise ValueError(f"unknown command target {target!r}")
    if value not in (0, 1):
        raise ValueError(f"value must be 0 or 1, got {value!r}")
    body = bytes([0x55, 0xAA, 0x00, 0x0D, seq & 0xFF, 0x00, 0x12, target, value])
    return body + crc16_arc(body).to_bytes(2, "big") + FRAME_END


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
    sound_on: bool
    eco_on: bool
    usbc1_active: bool
    usbc2_active: bool
    usba1_active: bool
    usba2_active: bool

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
        sound_on=_bit(frame, 78, 0x01),
        eco_on=_bit(frame, 79, 0x40),
        usbc1_active=_bit(frame, 79, 0x01),
        usbc2_active=_bit(frame, 79, 0x02),
        usba1_active=_bit(frame, 79, 0x10),
        usba2_active=_bit(frame, 79, 0x20),
    )
