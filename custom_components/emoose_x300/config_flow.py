"""Config flow for the emoose X300 integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX, DOMAIN


class EmooseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup form."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the MQTT topic prefix the station publishes under."""
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            return self.async_abort(reason="mqtt_required")

        errors: dict[str, str] = {}
        if user_input is not None:
            prefix = user_input[CONF_TOPIC_PREFIX].strip().rstrip("/")
            if not prefix or "+" in prefix or "#" in prefix:
                errors["base"] = "invalid_prefix"
            else:
                await self.async_set_unique_id(prefix)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="emoose X300", data={CONF_TOPIC_PREFIX: prefix}
                )

        schema = vol.Schema(
            {vol.Required(CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str}
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
