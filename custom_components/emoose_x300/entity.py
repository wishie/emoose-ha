"""Base entity for the emoose X300 integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .hub import EmooseHub


class EmooseEntity(Entity):
    """An entity fed by the station's telemetry."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: EmooseHub, entry_id: str, key: str) -> None:
        """Initialise the entity."""
        self._hub = hub
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="emoose X300",
            manufacturer="emoose",
            model="X300",
        )

    @property
    def available(self) -> bool:
        """Entities are unavailable while the station is silent."""
        return self._hub.available

    async def async_added_to_hass(self) -> None:
        """Register for updates."""
        self.async_on_remove(self._hub.async_add_listener(self.async_write_ha_state))
