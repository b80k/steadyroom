"""Tuning values of SteadyRoom as number entities."""

from __future__ import annotations

from dataclasses import asdict

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, EntityCategory
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.steadyroom.const import NUMBER_SPECS
from custom_components.steadyroom.logic import Parameters
from helpers import ENTITY, CallLog, call_entity, number_entity_id, set_room, set_unit, settle, setup_entry

EXPECTED_DEFAULTS = {**asdict(Parameters()), "door_open_delay": 60.0, "door_close_delay": 15.0, "sensor_max_age": 0.0}
EXPECTED_UNITS = {
    "heat_start": "K",
    "heat_stop": "K",
    "cool_start": "K",
    "cool_stop": "K",
    "auto_start": "K",
    "auto_stop": "K",
    "min_offset": "K",
    "knee": "K",
    "factor": None,
    "lock_minutes": "min",
    "min_setpoint": "°C",
    "max_setpoint": "°C",
    "door_open_delay": "s",
    "door_close_delay": "s",
    "sensor_max_age": "min",
}


async def _set(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call("number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True)
    await hass.async_block_till_done()


async def test_number_defaults_equal_logic_parameters(hass: HomeAssistant) -> None:
    """Every field of logic.Parameters plus door delays and sensor age, with today's values as defaults."""
    set_unit(hass, "off")
    set_room(hass, 21.0)
    entry = await setup_entry(hass)

    assert {spec.key for spec in NUMBER_SPECS} == EXPECTED_DEFAULTS.keys()
    registry = er.async_get(hass)
    for key, default in EXPECTED_DEFAULTS.items():
        entity_id = number_entity_id(hass, entry, key)
        state = hass.states.get(entity_id)
        assert state is not None, key
        assert float(state.state) == default, key
        assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == EXPECTED_UNITS[key], key
        assert state.attributes["mode"] == "box", key
        registry_entry = registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.entity_category is EntityCategory.CONFIG, key


async def test_number_change_reevaluates_at_once(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A wider heat start makes the unit start immediately, without reload or other trigger."""
    set_unit(hass, "off")
    set_room(hass, 20.85)
    entry = await setup_entry(hass)
    await call_entity(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    await settle(hass, freezer, calls)
    assert calls.to_unit() == []

    await _set(hass, number_entity_id(hass, entry, "heat_start"), 0.1)

    assert calls.modes() == ["heat"]
    state = hass.states.get(number_entity_id(hass, entry, "heat_start"))
    assert state is not None
    assert float(state.state) == 0.1


async def test_number_change_of_setpoint_limit_reaches_unit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A lower highest setpoint clamps the setpoint sent to the unit at once."""
    set_unit(hass, "heat", current=23.0, setpoint=24.5)
    set_room(hass, 20.0)
    entry = await setup_entry(hass)
    await call_entity(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    await settle(hass, freezer, calls)

    await _set(hass, number_entity_id(hass, entry, "max_setpoint"), 24.0)
    assert calls.setpoints() == [24.0]


async def test_number_restored_before_first_evaluation(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Restored tuning values are in place when the climate entity first decides."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("number.wohnzimmer_heat_start_below_target", "0.1"),
                {
                    "native_max_value": 5.0,
                    "native_min_value": 0.0,
                    "native_step": 0.05,
                    "native_unit_of_measurement": "K",
                    "native_value": 0.1,
                },
            ),
            (
                State(ENTITY, "heat"),
                {"hvac_mode": "heat", "target": 21.0, "last_direction": "off", "run_ended_at": None, "door_resume": None},
            ),
        ],
    )
    set_unit(hass, "off")
    set_room(hass, 20.85)
    entry = await setup_entry(hass)

    assert hass.states.get(number_entity_id(hass, entry, "heat_start")).state == "0.1"  # type: ignore[union-attr]
    assert calls.modes() == ["heat"]


async def test_number_restore_outside_range_keeps_default(hass: HomeAssistant) -> None:
    """A stored value outside the range is ignored."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("number.wohnzimmer_door_open_delay", "99999"),
                {
                    "native_max_value": 99999.0,
                    "native_min_value": 0.0,
                    "native_step": 1.0,
                    "native_unit_of_measurement": "s",
                    "native_value": 99999.0,
                },
            )
        ],
    )
    set_unit(hass, "off")
    set_room(hass, 21.0)
    entry = await setup_entry(hass)
    assert hass.states.get(number_entity_id(hass, entry, "door_open_delay")).state == "60.0"  # type: ignore[union-attr]


async def test_number_rejects_lowest_above_highest_setpoint(hass: HomeAssistant) -> None:
    """The lowest setpoint at the unit cannot be set above the highest one."""
    set_unit(hass, "off")
    set_room(hass, 21.0)
    entry = await setup_entry(hass)
    with pytest.raises(ServiceValidationError):
        await _set(hass, number_entity_id(hass, entry, "min_setpoint"), 31.0)
    assert hass.states.get(number_entity_id(hass, entry, "min_setpoint")).state == "16.0"  # type: ignore[union-attr]



async def test_number_fine_tuning_is_disabled_by_default(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """The device page shows the everyday settings; fine tuning folds into "+N disabled entities".

    Disabled values keep their defaults, so control is unchanged (live check 13.11.2026: heat/24.5).
    """
    set_unit(hass, "off", current=23.0, setpoint=20.0)
    set_room(hass, 19.98)
    entry = await setup_entry(hass, enable_fine_tuning=False)

    registry = er.async_get(hass)
    disabled = {
        key
        for key in EXPECTED_DEFAULTS
        if registry.async_get(number_entity_id(hass, entry, key)).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    }
    assert disabled == {"knee", "factor", "min_setpoint", "max_setpoint", "sensor_max_age"}
    assert all(hass.states.get(number_entity_id(hass, entry, key)) is None for key in disabled)

    await settle(hass, freezer, calls)
    await call_entity(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "heat"}), ("set_temperature", {"temperature": 24.5})]
