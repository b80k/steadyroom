"""Config and options flow of SteadyRoom."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.steadyroom.const import (
    CONF_CONTACTS,
    CONF_CONTACTS_INVERTED,
    CONF_FALLBACK_SENSOR,
    CONF_OBSERVE_ONLY,
    CONF_ROOM_SENSOR,
    CONF_SCHEDULE,
    CONF_UNDERLYING,
    DOMAIN,
)
from helpers import DOOR, ENTITY, FALLBACK, ROOM, SCHEDULE, UNIT, WINDOW, CallLog, set_room, set_unit, setup_entry

FULL_INPUT: dict[str, Any] = {
    CONF_NAME: "Wohnzimmer",
    CONF_UNDERLYING: UNIT,
    CONF_ROOM_SENSOR: ROOM,
    CONF_FALLBACK_SENSOR: FALLBACK,
    CONF_CONTACTS: [DOOR, WINDOW],
    CONF_CONTACTS_INVERTED: True,
    CONF_SCHEDULE: SCHEDULE,
}


def _states(hass: HomeAssistant) -> None:
    set_unit(hass, "off")
    set_room(hass, 21.0)
    set_room(hass, 21.0, FALLBACK)
    set_room(hass, 21.0, "sensor.other")
    hass.states.async_set("climate.other_unit", "off")


async def _user_flow(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def test_user_step_creates_entry(hass: HomeAssistant) -> None:
    """All fields filled: one entry, the choices stored as options, the device set up."""
    _states(hass)
    result = await _user_flow(hass, FULL_INPUT)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wohnzimmer"
    assert result["data"] == {}
    entry = result["result"]
    assert entry.options == {
        CONF_UNDERLYING: UNIT,
        CONF_ROOM_SENSOR: ROOM,
        CONF_FALLBACK_SENSOR: FALLBACK,
        CONF_CONTACTS: [DOOR, WINDOW],
        CONF_CONTACTS_INVERTED: True,
        CONF_SCHEDULE: SCHEDULE,
        CONF_OBSERVE_ONLY: True,
    }
    assert hass.states.get(ENTITY) is not None


async def test_user_step_only_required_fields(hass: HomeAssistant) -> None:
    """Unit and room sensor are enough; optional choices are left out, contacts are an empty list."""
    _states(hass)
    result = await _user_flow(hass, {CONF_NAME: "Büro", CONF_UNDERLYING: UNIT, CONF_ROOM_SENSOR: ROOM})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Büro"
    assert result["result"].options == {
        CONF_UNDERLYING: UNIT,
        CONF_ROOM_SENSOR: ROOM,
        CONF_CONTACTS: [],
        CONF_CONTACTS_INVERTED: False,
        CONF_OBSERVE_ONLY: True,
    }


async def test_user_step_new_device_starts_observing(hass: HomeAssistant, calls: CallLog) -> None:
    """A device added from the UI observes until the user turns "Observe only" off."""
    _states(hass)
    set_unit(hass, "heat", setpoint=24.0)
    result = await _user_flow(hass, {CONF_NAME: "Wohnzimmer", CONF_UNDERLYING: UNIT, CONF_ROOM_SENSOR: ROOM})
    await hass.async_block_till_done()
    entry = result["result"]

    switch = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_observe_only")
    assert switch is not None
    assert hass.states.get(switch).state == "on"  # type: ignore[union-attr]
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": ENTITY, "hvac_mode": "off"}, blocking=True
    )
    await hass.async_block_till_done()
    assert calls.to_unit() == []


async def test_user_step_duplicate_unit_aborts(hass: HomeAssistant) -> None:
    """A second device on the same unit is refused."""
    _states(hass)
    await setup_entry(hass)
    result = await _user_flow(hass, FULL_INPUT | {CONF_NAME: "Zweiter"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_step_rejects_steadyroom_as_unit(hass: HomeAssistant) -> None:
    """A SteadyRoom thermostat cannot be the unit of another one."""
    _states(hass)
    await setup_entry(hass)
    result = await _user_flow(hass, {CONF_NAME: "Schleife", CONF_UNDERLYING: ENTITY, CONF_ROOM_SENSOR: ROOM})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_UNDERLYING: "underlying_is_steadyroom"}


async def test_user_step_rejects_fallback_equal_to_room_sensor(hass: HomeAssistant) -> None:
    """The fallback must be another sensor."""
    _states(hass)
    result = await _user_flow(
        hass, {CONF_NAME: "X", CONF_UNDERLYING: UNIT, CONF_ROOM_SENSOR: ROOM, CONF_FALLBACK_SENSOR: ROOM}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_FALLBACK_SENSOR: "fallback_is_room_sensor"}


async def test_options_flow_changes_entities_and_reloads(hass: HomeAssistant) -> None:
    """New choices are stored and the device works with them right away."""
    _states(hass)
    entry = await setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_NAME: entry.title,
            CONF_UNDERLYING: UNIT,
            CONF_ROOM_SENSOR: "sensor.other",
            CONF_CONTACTS: [DOOR],
            CONF_CONTACTS_INVERTED: True,
            CONF_SCHEDULE: SCHEDULE,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_UNDERLYING: UNIT,
        CONF_ROOM_SENSOR: "sensor.other",
        CONF_CONTACTS: [DOOR],
        CONF_CONTACTS_INVERTED: True,
        CONF_SCHEDULE: SCHEDULE,
        CONF_OBSERVE_ONLY: False,
    }
    set_room(hass, 18.5, "sensor.other")
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.attributes["current_temperature"] == 18.5


async def test_options_flow_shows_current_choices(hass: HomeAssistant) -> None:
    """The form is prefilled with what is configured now."""
    _states(hass)
    entry = await setup_entry(hass, **{CONF_FALLBACK_SENSOR: FALLBACK, CONF_CONTACTS: [DOOR]})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }
    assert suggested[CONF_NAME] == entry.title
    assert suggested[CONF_FALLBACK_SENSOR] == FALLBACK
    assert suggested[CONF_CONTACTS] == [DOOR]


async def test_options_flow_clears_optional_choices(hass: HomeAssistant) -> None:
    """Leaving fallback, contacts and schedule empty removes them."""
    _states(hass)
    entry = await setup_entry(hass, **{CONF_FALLBACK_SENSOR: FALLBACK, CONF_CONTACTS: [DOOR], CONF_SCHEDULE: SCHEDULE})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NAME: entry.title, CONF_UNDERLYING: UNIT, CONF_ROOM_SENSOR: ROOM}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_UNDERLYING: UNIT,
        CONF_ROOM_SENSOR: ROOM,
        CONF_CONTACTS: [],
        CONF_CONTACTS_INVERTED: False,
        CONF_OBSERVE_ONLY: False,
    }


async def test_options_flow_renames_entry_and_device(hass: HomeAssistant) -> None:
    """A new name renames the entry and the device."""
    _states(hass)
    entry = await setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NAME: "Fernsehzimmer", CONF_UNDERLYING: UNIT, CONF_ROOM_SENSOR: ROOM}
    )
    await hass.async_block_till_done()

    assert entry.title == "Fernsehzimmer"
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [device.name for device in devices] == ["Fernsehzimmer"]


async def test_options_flow_rejects_unit_of_other_device(hass: HomeAssistant) -> None:
    """The options flow cannot move a device onto a unit another device controls."""
    _states(hass)
    await setup_entry(hass)
    other = await setup_entry(hass, **{CONF_UNDERLYING: "climate.other_unit"})

    result = await hass.config_entries.options.async_init(other.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NAME: other.title, CONF_UNDERLYING: UNIT, CONF_ROOM_SENSOR: ROOM}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_UNDERLYING: "underlying_in_use"}
    assert other.options[CONF_UNDERLYING] == "climate.other_unit"


async def test_options_flow_keeps_observation_mode(hass: HomeAssistant) -> None:
    """Changing entities does not touch the observation switch."""
    _states(hass)
    entry = await setup_entry(hass, **{CONF_OBSERVE_ONLY: True})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NAME: entry.title, CONF_UNDERLYING: UNIT, CONF_ROOM_SENSOR: "sensor.other"}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_OBSERVE_ONLY] is True
