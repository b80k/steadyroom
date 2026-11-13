"""Observation mode of SteadyRoom: decide everything, send nothing to the unit."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_OBSERVE_ONLY
from .entity import device_info
from .runtime import SteadyRoomConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SteadyRoomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the observation switch of this entry."""
    async_add_entities([ObserveOnlySwitch(entry)])


class ObserveOnlySwitch(SwitchEntity):
    """While on, SteadyRoom evaluates and shows what it would send, but sends nothing.

    The position lives in the entry options, written at once on every change,
    so it survives a crash; the restore cache is only written at shutdown.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "observe_only"
    _attr_should_poll = False

    def __init__(self, entry: SteadyRoomConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_observe_only"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        """Whether observation mode is active."""
        return self._entry.runtime_data.observe_only

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Stop sending to the unit."""
        self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send to the unit again; the climate entity re-sends everything at once."""
        self._set(False)

    def _set(self, observe_only: bool) -> None:
        # Options are updated without reload: there is no update listener, and
        # the options flow (which reloads) carries this value over unchanged.
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, CONF_OBSERVE_ONLY: observe_only}
        )
        self._entry.runtime_data.async_set_observe_only(observe_only)
        self.async_write_ha_state()
