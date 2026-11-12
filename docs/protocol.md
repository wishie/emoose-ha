# emoose X300 protocol notes

Reverse engineered from the station's own MQTT traffic. Confidence: **confirmed** = checked
against the unit's display or a deliberate test; **likely** = fits every observation but has
a gap; **guess/unknown** = see the end.

## Transport

* Plain MQTT 3.1.1 on TCP 1883. The station resolves `app.emoose.com` and connects with a
  built-in username/password, keepalive 120 s, subscribing to `$oc/devices/<id>/command/request`
  (plus firmware-upgrade topics for AC, BMS, DC main, DC aux and LCD).
* It publishes telemetry to `$oc/devices/<id>/report/request` about every 6 seconds (and
  immediately after a command) and acknowledges commands on `.../command/response`.
* Telemetry and acknowledgements are **ASCII-hex text**; commands are **raw binary**.

## Framing and checksum

`55 AA | length (2 bytes) | body... | CRC (2 bytes) | 33 CC`

The CRC is CRC-16/ARC (poly 0x8005 reflected, init 0), stored big-endian, over every byte
before it, including the `55 AA`. Telemetry reports are 122 bytes (length field `007A`).
Very occasionally the Wi-Fi module glues the text `AT+MQTTPUB=0` into a payload; such frames
fail the CRC and must be dropped.

## Commands (cloud to station)

`55 AA 00 0D <seq> 00 12 <target> <value> <crc16> 33 CC`

| Target | Meaning | Value |
|---|---|---|
| `0x07` | AC output | 1 on, 0 off |
| `0x06` | DC output | 1 on, 0 off |

The station answers `55 AA 00 0D <seq> <counter> 12 <target> 88 <crc16> 33 CC`
(`0x88` = accepted). Changing the screen standby setting in the app produces a 12-byte response in a different class,
`55 AA 00 0C <seq> <counter> 16 88 <crc16> 33 CC`, with no target byte; the command frame has not been
captured. A response with target `0x0A` was seen when Auto-Fan was toggled in the app, so
`0x0A` is almost certainly the Auto-Fan command; the command frame itself (and its on/off values)
has not been captured yet, so it is not implemented. Sequence bytes 0x20..0x2F were verified to be accepted.

## Report layout (byte offsets, big-endian)

| Offset | Field | Notes | Confidence |
|---|---|---|---|
| 4 | last command sequence | echo | likely |
| 5 | message counter | | likely |
| 7-19 | serial number (ASCII, 13 chars) | byte 6 is an extra `A` the display omits | confirmed |
| 32 | battery % | | confirmed |
| 33-34 | minutes to empty (`FFFF` = none) | smoothed estimate | confirmed |
| 35-36 | minutes to full (`FFFF` = none) | | confirmed |
| 37-38 | total input power, 0.1 W | reads 0 once the unit says 100% | confirmed |
| 39-40 | total output power, 0.1 W | | confirmed |
| 41-42 | AC input power, 0.1 W | | confirmed |
| 43-44 | DC / solar input power, 0.1 W | confirmed with a solar panel | confirmed |
| 45-46 | AC output power, 0.1 W | | confirmed |
| 47-48 | DC output power, 0.1 W | | confirmed |
| 51-52 / 53-54 | USB-C 1 / USB-C 2 power, 0.1 W | | confirmed |
| 55-56 / 57-58 | USB-A 1 / USB-A 2 power, 0.1 W | | confirmed |
| 63-68 | three temperatures, tenths of a kelvin | which sensor is which is unknown | likely |
| 73-74 | battery voltage, 10 mV | | likely |
| 75-76 | battery current, signed, 10 mA (+ = charging) | | likely |
| 77 | flags: `0x02` AC out, `0x04` DC out, `0x10` charging from AC, `0x20` charging from DC / solar, `0x40` charge complete | `0x80` and `0x01` always set; `0x40` seen once | confirmed / likely |
| 78 | flags: `0x01` sound on, `0x08` Auto-Fan setting on | `0x04` set, meaning unknown; `0x08` is the setting, not whether the fans spin | confirmed |
| 79 | flags: `0x01` USB-C 1, `0x02` USB-C 2, `0x10` USB-A 1, `0x20` USB-A 2, `0x40` ECO | flags lag a second or two after unplugging; `0x04`, `0x08`, `0x80` unknown | confirmed |
| 81 | screen standby setting: `0` never, `1` 30 seconds, `2` 1 minute, `3` 5 minutes, `4` 30 minutes | all five options in the app's menu checked | confirmed |
| 96-97 | device id (the number in the topic) | | confirmed |
| 99-101 | software version, shown as b101.b99.b100 | | confirmed |
| 104-106 | hardware version, shown as b106.b104.b105 | | confirmed |
| 110 | mirrors AC output on | | likely |
| 118-119 | CRC | | confirmed |

## Observations worth knowing

* The unit's "time left" is `battery % x 214.3 Wh / output watts` (214.3 Wh is 90% of the 238.08 Wh
  nameplate), using output power, so it is optimistic with AC on: the inverter alone draws about 7 W.
* USB and DC outputs are about 80% efficient; the AC inverter adds about 7 W of idle draw on top of the
  load; AC charging into the battery is about 95% efficient.
* At 100% the unit stops reporting input power even while current is still flowing; battery
  voltage x current is the real flow.

## Not found in the telemetry

Whether the fans are actually spinning, the touchscreen being on or off, the Wi-Fi and Bluetooth MAC addresses,
and any command other than the AC and DC output switches (the app may send others).
