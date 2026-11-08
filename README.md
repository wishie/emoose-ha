# emoose X300 for Home Assistant

An **unofficial** Home Assistant integration for the emoose X300 portable power station.
It reads the unit's live telemetry over MQTT and lets you switch the AC and DC outputs.
Not affiliated with or endorsed by emoose. The protocol was reverse engineered from the
unit's own network traffic; use it at your own risk.

## What you get

| Entities | Notes |
|---|---|
| Battery %, battery voltage, current and power | power is negative while discharging |
| Time to empty / to full (minutes and `h:mm`) | the unit's own estimates |
| Input power, AC input power, DC / solar input power | |
| Output power: total, AC, DC, USB-C 1, USB-C 2, USB-A 1, USB-A 2 | |
| Three temperatures | which sensor is which is unknown |
| AC output / DC output (sensors **and switches**) | the switches send the same commands as the app |
| Charging, **Charge complete (likely)** | the second is seen once and not yet confirmed |
| USB port active flags, Sound, ECO mode | the flags can lag a second or two behind a plug or unplug |
| Serial number, software and hardware version | diagnostic |

Details and confidence levels are in [docs/protocol.md](docs/protocol.md).

Not available because the unit does not report them: fan state, touchscreen on/off, MAC
addresses. Not yet decoded: any app command beyond the AC and DC output toggles. Solar / DC charging
was confirmed with a panel; 12 V car-charger input has not been tried.

## How it works, and the catch

The station only talks to the vendor's cloud MQTT broker (it looks up `app.emoose.com`).
For this integration to see its data, that traffic has to reach an MQTT broker you can
subscribe to from Home Assistant. There are two ways:

**Option A: DNS redirect.** Point `app.emoose.com` at your own broker (a local DNS record
on your router, Pi-hole, AdGuard, UniFi and so on). The station then connects to you. Use
[docs/mosquitto-redirect.conf](docs/mosquitto-redirect.conf). The topic prefix is
`$oc/devices/<your device id>`. Downsides: the emoose app and the unit's firmware updates stop
working while the redirect is active. **The author has not tested this path.**

**Option B: bridge to the cloud (the path the author used).** Your local Mosquitto mirrors
your station's topics from the vendor's broker, using the login your own station sends.
Use [docs/mosquitto-bridge.conf](docs/mosquitto-bridge.conf); the topic prefix is then
`emoose`. The app keeps working. You must capture your own station's CONNECT packet to get its
login; do not share it, and only subscribe to your own device's topics. The vendor can change
or block this at any time.

You also need Home Assistant's **MQTT integration** connected to that broker. Home Assistant
OS users can use the Mosquitto add-on; on Container installs run Mosquitto as its own container.

## Install

1. In HACS, open the menu, choose **Custom repositories**, add this repository's URL with
   type **Integration**, then install **emoose X300** and restart Home Assistant.
   (Or copy `custom_components/emoose_x300` into your `config/custom_components` folder.)
2. Go to **Settings, Devices & services, Add integration**, choose **emoose X300**, and enter
   the topic prefix: `$oc/devices/<id>` for Option A, or `emoose` for the bridge template.
   Your device id is the number in the station's topic names (it appears in every report).
3. Within a few seconds of the first report, the entities fill in. They show unavailable if
   the station is silent for 30 seconds.

## Notes and limits

* **Tested** against Home Assistant core 2025.1.4 and 2026.2.3 test environments, with 64
  automated tests that replay real captured frames. The decoding itself is based on a real unit;
  this packaged integration has **not yet been run against a live station**, so expect rough edges.
* The switches publish raw command frames. If a switch does nothing, check that
  `<prefix>/command/request` reaches the station (bridge direction, broker logs).
* Only the X300 has been seen. Other emoose models may use different layouts.
* The fan and touchscreen states are not reported by the unit.

## Development

```
pip install pytest                                       # protocol tests only
pip install pytest-homeassistant-custom-component        # plus the integration tests
pytest
```

`custom_components/emoose_x300/protocol.py` has no Home Assistant imports. Captured frames are
in `tests/frames.py`; if you have a different emoose model, frames from it (with what the unit
was doing) are the most useful contribution.

## Privacy

Telemetry includes the unit's serial number. Do not post raw captures or your station's MQTT
login publicly.
