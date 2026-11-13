"""Device shared by all entities of one SteadyRoom entry."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """One device per config entry; the climate entity and all tuning values belong to it."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="SteadyRoom",
        model="Room thermostat",
    )
