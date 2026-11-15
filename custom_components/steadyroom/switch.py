"""The "Control the unit" switch: SteadyRoom only sends to the unit while it is on."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_OBSERVE_ONLY, DOMAIN
from .entity import device_info
from .runtime import SteadyRoomConfigEntry

PARALLEL_UPDATES = 0

# Unique id suffix of the switch up to 0.1.2, which meant the opposite ("Observe only").
_LEGACY_SUFFIX = "observe_only"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SteadyRoomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the control switch of this entry and drop the former observation switch."""
    registry = er.async_get(hass)
    if legacy := registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, f"{entry.entry_id}_{_LEGACY_SUFFIX}"):
        # Its position lives on in the entry options, so nothing is lost.
        registry.async_remove(legacy)
    async_add_entities([ControlSwitch(entry)])


class ControlSwitch(SwitchEntity):
    """While on, SteadyRoom controls the unit; while off, it decides and shows what it would send, but sends nothing.

    The position lives in the entry options (stored as ``observe_only``, the opposite),
    written at once on every change, so it survives a crash; the restore cache is only
    written at shutdown.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "control"
    _attr_should_poll = False

    def __init__(self, entry: SteadyRoomConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_control"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        """Whether SteadyRoom controls the unit."""
        return not self._entry.runtime_data.observe_only

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Control the unit; the climate entity sends mode and setpoint at once."""
        self._set(observe_only=False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop sending to the unit and only show what SteadyRoom would do."""
        self._set(observe_only=True)

    def _set(self, *, observe_only: bool) -> None:
        # Options are updated without reload: there is no update listener, and
        # the options flow (which reloads) carries this value over unchanged.
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, CONF_OBSERVE_ONLY: observe_only}
        )
        self._entry.runtime_data.async_set_observe_only(observe_only)
        self.async_write_ha_state()
