"""Push-based state holder fed by the station's MQTT telemetry."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_call_later

from .const import AVAILABILITY_TIMEOUT, COMMAND_SUFFIX, REPORT_SUFFIX
from .protocol import (
    COMMAND_SEQ_MIN,
    Report,
    AC_TIMEOUT_SEQ_MIN,
    build_ac_timeout_command,
    build_command,
    next_ac_timeout_sequence,
    next_sequence,
    parse_report,
)

_LOGGER = logging.getLogger(__name__)


class EmooseHub:
    """Subscribes to the station's report topic and publishes its commands."""

    def __init__(self, hass: HomeAssistant, topic_prefix: str) -> None:
        """Initialise the hub."""
        self.hass = hass
        self.topic_prefix = topic_prefix.rstrip("/")
        self.report: Report | None = None
        self._available = False
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribe: CALLBACK_TYPE | None = None
        self._cancel_expiry: CALLBACK_TYPE | None = None
        self._seq = COMMAND_SEQ_MIN
        self._ac_timeout_seq = AC_TIMEOUT_SEQ_MIN

    @property
    def report_topic(self) -> str:
        """Topic the station publishes its telemetry on."""
        return f"{self.topic_prefix}/{REPORT_SUFFIX}"

    @property
    def command_topic(self) -> str:
        """Topic the station listens on for commands."""
        return f"{self.topic_prefix}/{COMMAND_SUFFIX}"

    @property
    def available(self) -> bool:
        """Whether a valid report arrived recently."""
        return self._available and self.report is not None

    async def async_start(self) -> None:
        """Subscribe to the telemetry topic."""
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            raise ConfigEntryNotReady("The MQTT integration is not available")
        self._unsubscribe = await mqtt.async_subscribe(
            self.hass, self.report_topic, self._handle_message, qos=0, encoding="utf-8"
        )

    @callback
    def async_stop(self) -> None:
        """Unsubscribe and cancel timers."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self._cancel_expiry is not None:
            self._cancel_expiry()
            self._cancel_expiry = None

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Register a callback for new data; returns a function that removes it."""
        self._listeners.append(update_callback)

        @callback
        def remove() -> None:
            self._listeners.remove(update_callback)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def _handle_message(self, msg: ReceiveMessage) -> None:
        report = parse_report(msg.payload)
        if report is None:
            _LOGGER.debug("Ignoring invalid payload on %s", msg.topic)
            return
        self.report = report
        self._available = True
        if self._cancel_expiry is not None:
            self._cancel_expiry()
        self._cancel_expiry = async_call_later(
            self.hass, AVAILABILITY_TIMEOUT, self._handle_expired
        )
        self._notify()

    @callback
    def _handle_expired(self, _now: datetime) -> None:
        self._cancel_expiry = None
        self._available = False
        self._notify()

    async def async_send_ac_timeout(self, value: int) -> None:
        """Set the AC timeout (byte 82 code, see protocol.AC_TIMEOUTS).

        Uses its own sequence counter in the 0x40.. range the app uses.
        The shared 0x20.. counter is acked (0x88) but ignored for this
        command class, so it must not be reused here.
        """
        seq = self._ac_timeout_seq
        self._ac_timeout_seq = next_ac_timeout_sequence(seq)
        await mqtt.async_publish(
            self.hass,
            self.command_topic,
            build_ac_timeout_command(seq, value),
            qos=0,
            retain=False,
        )

    async def async_send_command(self, target: int, value: int) -> None:
        """Switch an output on (1) or off (0)."""
        seq = self._seq
        self._seq = next_sequence(seq)
        await mqtt.async_publish(
            self.hass, self.command_topic, build_command(seq, target, value), qos=0, retain=False
        )
