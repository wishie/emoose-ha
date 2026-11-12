"""The emoose X300 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_TOPIC_PREFIX
from .hub import EmooseHub

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.SELECT]

type EmooseConfigEntry = ConfigEntry[EmooseHub]


async def async_setup_entry(hass: HomeAssistant, entry: EmooseConfigEntry) -> bool:
    """Set up emoose X300 from a config entry."""
    hub = EmooseHub(hass, entry.data[CONF_TOPIC_PREFIX])
    await hub.async_start()
    entry.runtime_data = hub
    entry.async_on_unload(hub.async_stop)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EmooseConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
