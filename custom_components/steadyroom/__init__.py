"""SteadyRoom: a room thermostat on top of an air conditioner whose own sensor sits in the wrong place."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import CONF_OBSERVE_ONLY, DEFAULT_OBSERVE_ONLY, PLATFORMS
from .runtime import SteadyRoomConfigEntry, SteadyRoomRuntime


async def async_setup_entry(hass: HomeAssistant, entry: SteadyRoomConfigEntry) -> bool:
    """Set up one SteadyRoom device from a config entry."""
    entry.runtime_data = SteadyRoomRuntime(
        observe_only=bool(entry.options.get(CONF_OBSERVE_ONLY, DEFAULT_OBSERVE_ONLY))
    )
    # One platform after the other: the number entities restore the tuning
    # values, and the climate entity must not evaluate with defaults first.
    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, [platform])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SteadyRoomConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
