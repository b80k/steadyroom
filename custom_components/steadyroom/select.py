"""The near-target preset: which of the unit's own presets SteadyRoom uses close to the target."""

from __future__ import annotations

from homeassistant.components.climate import ATTR_PRESET_MODES
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_UNDERLYING, PRESET_OFF
from .entity import device_info
from .runtime import SteadyRoomConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SteadyRoomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the near-target preset select of this entry."""
    async_add_entities([NearTargetPresetSelect(entry)])


class NearTargetPresetSelect(SelectEntity, RestoreEntity):
    """"Off", or one of the unit's presets (such as quiet) that SteadyRoom sends once the room is near the target.

    The options follow the unit: they are "off" plus whatever presets the unit reports.
    A chosen preset the unit does not report right now (unit offline) stays chosen.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "near_target_preset"
    _attr_should_poll = False

    def __init__(self, entry: SteadyRoomConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_near_target_preset"
        self._attr_device_info = device_info(entry)
        self._written_options: list[str] = []

    def _unit_presets(self) -> list[str]:
        unit = self.hass.states.get(self._entry.options[CONF_UNDERLYING])
        presets = unit.attributes.get(ATTR_PRESET_MODES) if unit is not None else None
        return [str(preset) for preset in presets or [] if preset != PRESET_OFF]

    @property
    def options(self) -> list[str]:
        """Off, then the unit's presets."""
        options = [PRESET_OFF, *self._unit_presets()]
        chosen = self._entry.runtime_data.near_preset
        if chosen is not None and chosen not in options:
            options.append(chosen)
        return options

    @property
    def current_option(self) -> str:
        """The chosen preset, or off."""
        return self._entry.runtime_data.near_preset or PRESET_OFF

    async def async_added_to_hass(self) -> None:
        """Restore the last choice and follow the unit's list of presets."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (PRESET_OFF, "unknown", "unavailable", ""):
            self._entry.runtime_data.async_set_near_preset(last.state)

        @callback
        def _unit_changed(event: Event[EventStateChangedData]) -> None:
            # The unit reports often; only a changed list of presets needs a new state.
            if self.options != self._written_options:
                self._write()

        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._entry.options[CONF_UNDERLYING]], _unit_changed)
        )

    async def async_select_option(self, option: str) -> None:
        """Choose the preset; the climate entity uses it from its next evaluation."""
        self._entry.runtime_data.async_set_near_preset(None if option == PRESET_OFF else option)
        self._write()

    @callback
    def _write(self) -> None:
        self._written_options = self.options
        self.async_write_ha_state()
