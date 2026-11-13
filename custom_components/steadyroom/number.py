"""Tuning values of SteadyRoom as configuration entities on the device page."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, NUMBER_SPECS, NumberSpec, NumberUnit
from .entity import device_info
from .runtime import SteadyRoomConfigEntry, SteadyRoomRuntime

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SteadyRoomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one number entity per tuning value."""
    temperature_unit = hass.config.units.temperature_unit
    async_add_entities(SteadyRoomNumber(entry, spec, temperature_unit) for spec in NUMBER_SPECS)


def _unit(spec: NumberSpec, temperature_unit: str) -> str | None:
    match spec.unit:
        case NumberUnit.KELVIN:
            return "K"
        case NumberUnit.MINUTES:
            return UnitOfTime.MINUTES
        case NumberUnit.SECONDS:
            return UnitOfTime.SECONDS
        case NumberUnit.TEMPERATURE:
            return temperature_unit
        case NumberUnit.NONE:
            return None


class SteadyRoomNumber(RestoreNumber):
    """One tuning value; restored across restarts, applied without reload."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_should_poll = False

    def __init__(self, entry: SteadyRoomConfigEntry, spec: NumberSpec, temperature_unit: str) -> None:
        self._runtime: SteadyRoomRuntime = entry.runtime_data
        self._key = spec.key
        self._attr_unique_id = f"{entry.entry_id}_{spec.key}"
        self._attr_translation_key = spec.key
        self._attr_device_info = device_info(entry)
        self._attr_native_min_value = spec.minimum
        self._attr_native_max_value = spec.maximum
        self._attr_native_step = spec.step
        self._attr_native_unit_of_measurement = _unit(spec, temperature_unit)
        self._attr_entity_registry_enabled_default = not spec.advanced

    @property
    def native_value(self) -> float:
        """The value in use right now."""
        return self._runtime.values[self._key]

    async def async_added_to_hass(self) -> None:
        """Restore the last value; a value outside the range falls back to the default."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is None or last.native_value is None:
            return
        restored = float(last.native_value)
        if self.native_min_value <= restored <= self.native_max_value:
            self._runtime.async_set_value(self._key, restored)

    async def async_set_native_value(self, value: float) -> None:
        """Apply a new value; the climate entity re-evaluates at once."""
        values = self._runtime.values
        low = value if self._key == "min_setpoint" else values["min_setpoint"]
        high = value if self._key == "max_setpoint" else values["max_setpoint"]
        if low > high:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="setpoint_range",
                translation_placeholders={"low": str(low), "high": str(high)},
            )
        self._runtime.async_set_value(self._key, float(value))
        self.async_write_ha_state()
