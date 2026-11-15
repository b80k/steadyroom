"""The SteadyRoom climate entity against a simulated air conditioner.

Test names carry the ISA check words (modes, passthrough, sperre,
sendeschwelle, tuer, zeitplan, wiederkehr, fuehler, diagnose, restore,
beobachten, nur_unterlage) so ``pytest -k <word>`` runs exactly the check of one criterion.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_restore_state_shutdown_restart,
    mock_restore_cache_with_extra_data,
)

from homeassistant.components.climate import ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.components.climate.const import DATA_COMPONENT as CLIMATE_COMPONENT
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, STATE_UNAVAILABLE, EntityCategory
from homeassistant.core import Context, CoreState, HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.steadyroom.const import (
    CONF_CONTACTS,
    CONF_CONTACTS_INVERTED,
    CONF_FALLBACK_SENSOR,
    CONF_OBSERVE_ONLY,
    CONF_ROOM_SENSOR,
    CONF_SCHEDULE,
    CONF_UNDERLYING,
    DOMAIN,
    NUMBER_SPECS,
)
from helpers import (
    DOOR,
    ENTITY,
    FALLBACK,
    LEGACY_OBSERVE_SWITCH,
    ROOM,
    SCHEDULE,
    UNIT,
    WINDOW,
    CallLog,
    UnitSim,
    attrs,
    call_entity,
    number_entity_id,
    control_switch_id,
    set_room,
    set_unit,
    settle,
    setup_entry,
    tick,
)

TARGET = 21.0


async def start(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calls: CallLog,
    *,
    mode: str = "heat",
    room: float | str = 21.0,
    unit: str = "off",
    current: float = 23.0,
    setpoint: float = 20.0,
    **options: Any,
) -> MockConfigEntry:
    """Unit and room in a state, entry set up, mode and target set, start-up re-send done."""
    set_unit(hass, unit, current=current, setpoint=setpoint)
    set_room(hass, room)
    entry = await setup_entry(hass, **options)
    await call_entity(hass, "set_temperature", temperature=TARGET, hvac_mode=mode)
    await settle(hass, freezer, calls)
    return entry


def restored_climate(
    mode: str = "heat",
    *,
    target: float = TARGET,
    last_direction: str = "off",
    run_ended_at: str | None = None,
    door_resume: str | None = None,
) -> tuple[State, dict[str, Any]]:
    """Restore-cache item for the SteadyRoom entity."""
    return (
        State(ENTITY, mode, {"temperature": target}),
        {
            "hvac_mode": mode,
            "target": target,
            "last_direction": last_direction,
            "run_ended_at": run_ended_at,
            "door_resume": door_resume,
            "mode_set": True,
        },
    )


# ---------------------------------------------------------------- end to end


async def test_live_check_13_11_2026_heat_setpoint_24_5(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Heat, target 21.0, room 19.98, unit reads 23 → unit gets heat and 24.5 (live check 13.11.2026)."""
    set_unit(hass, "off", current=23.0, setpoint=20.0)
    set_room(hass, 19.98)
    await setup_entry(hass)
    await settle(hass, freezer, calls)

    await call_entity(hass, "set_temperature", temperature=21.0, hvac_mode="heat")

    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "heat"}), ("set_temperature", {"temperature": 24.5})]
    assert attrs(hass)["reason"] == "heating"


# ---------------------------------------------------------------- not configured


async def test_modes_new_device_never_touches_a_running_unit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Until a mode is chosen, a new device sends nothing, not even off, and says so."""
    set_unit(hass, "heat", setpoint=24.0)
    set_room(hass, 22.0)
    await setup_entry(hass)
    await tick(hass, freezer, 31)
    set_room(hass, 23.0)
    await call_entity(hass, "set_temperature", temperature=20.0)
    await tick(hass, freezer, 31)

    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "not_configured"

    await call_entity(hass, "set_hvac_mode", hvac_mode="off")
    assert calls.modes() == ["off"]


async def test_restore_mode_never_chosen_stays_not_configured(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A device restarted before anyone chose a mode still keeps its hands off the unit."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY, "off"),
                {
                    "hvac_mode": "off",
                    "target": 21.0,
                    "last_direction": "off",
                    "run_ended_at": None,
                    "door_resume": None,
                    "mode_set": False,
                },
            )
        ],
    )
    set_unit(hass, "heat", setpoint=24.0)
    set_room(hass, 22.0)
    await setup_entry(hass)
    await tick(hass, freezer, 31)
    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "not_configured"


# ---------------------------------------------------------------- ISC-2 modes


async def test_modes_entity_offers_off_heat_cool_heat_cool(hass: HomeAssistant, calls: CallLog) -> None:
    """One climate entity with the four modes, room temperature as current, own target."""
    set_unit(hass, "off", target_temp_step=1.0)
    set_room(hass, 20.4)
    await setup_entry(hass)

    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == HVACMode.OFF
    assert state.attributes["hvac_modes"] == ["off", "heat", "cool", "heat_cool"]
    assert state.attributes["current_temperature"] == 20.4
    assert state.attributes["temperature"] == 21.0
    assert state.attributes["target_temp_step"] == 1.0
    assert state.attributes["min_temp"] == 7.0
    assert state.attributes["max_temp"] == 35.0
    assert len([s for s in hass.states.async_all("climate") if s.entity_id != UNIT]) == 1


async def test_modes_default_step_is_half_degree(hass: HomeAssistant) -> None:
    """Without a step on the unit the target moves in 0.5 steps."""
    set_unit(hass, "off", target_temp_step=None)
    set_room(hass, 20.4)
    await setup_entry(hass)
    assert attrs(hass)["target_temp_step"] == 0.5


async def test_modes_heat_cool_is_auto(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """heat_cool runs the Auto band: 0.4 K below target starts Heat mode, not Auto."""
    await start(hass, freezer, calls, mode="heat_cool", room=20.6)
    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "in_band"

    await call_entity(hass, "set_hvac_mode", hvac_mode="heat")
    assert calls.modes() == ["heat"]

    calls.clear()
    set_unit(hass, "off")
    await call_entity(hass, "set_hvac_mode", hvac_mode="heat_cool")
    set_room(hass, 20.49)
    await hass.async_block_till_done()
    assert calls.modes() == ["heat"]


async def test_modes_off_switches_unit_off(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """Mode off sends off to a running unit and reports off_mode."""
    await start(hass, freezer, calls, mode="heat", room=20.0, unit="heat", setpoint=24.5)
    await call_entity(hass, "set_hvac_mode", hvac_mode="off")
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "off"})]
    assert attrs(hass)["reason"] == "off_mode"


@pytest.mark.parametrize("other_mode", ["dry", "fan_only"])
async def test_modes_off_also_ends_dry_and_fan_only(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog, other_mode: str
) -> None:
    """Mode off keeps the unit off, also when something else put it in dry or fan only."""
    await start(hass, freezer, calls, mode="off", room=21.0)
    set_unit(hass, other_mode)
    await hass.async_block_till_done()
    assert calls.modes() == ["off"]


async def test_modes_mode_change_keeps_running_direction(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Heat → heat_cool while heating in band: the run continues (no reset of the direction)."""
    await start(hass, freezer, calls, mode="heat", room=21.1, unit="heat", current=23.0, setpoint=23.5)
    assert calls.to_unit() == []
    await call_entity(hass, "set_hvac_mode", hvac_mode="heat_cool")
    assert calls.modes() == []
    assert attrs(hass)["reason"] == "heating"


async def test_modes_hvac_action(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """Off in mode off, idle while the unit rests, else what the unit does."""
    await start(hass, freezer, calls, mode="off", room=21.0)
    assert attrs(hass)["hvac_action"] == HVACAction.OFF

    await call_entity(hass, "set_hvac_mode", hvac_mode="heat")
    assert attrs(hass)["hvac_action"] == HVACAction.IDLE

    set_unit(hass, "heat", hvac_action="heating")
    await hass.async_block_till_done()
    assert attrs(hass)["hvac_action"] == HVACAction.HEATING

    set_unit(hass, "heat", hvac_action="idle")
    await hass.async_block_till_done()
    assert attrs(hass)["hvac_action"] == HVACAction.IDLE

    set_unit(hass, "cool")
    await hass.async_block_till_done()
    assert attrs(hass)["hvac_action"] == HVACAction.COOLING

    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert attrs(hass).get("hvac_action") is None


async def test_modes_one_device_holds_all_entities(hass: HomeAssistant) -> None:
    """One device per entry with the climate entity, every tuning value and the observation switch."""
    set_unit(hass, "off")
    set_room(hass, 21.0)
    entry = await setup_entry(hass)

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert {e.device_id for e in entities} == {devices[0].id}
    assert sorted(e.domain for e in entities) == ["climate"] + ["number"] * len(NUMBER_SPECS) + ["switch"]


# ---------------------------------------------------------------- ISC-3 passthrough


async def test_passthrough_fan_and_swing(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """Fan and swing mirror the unit and are set on the unit."""
    await start(hass, freezer, calls, mode="off")
    state = attrs(hass)
    assert state["fan_modes"] == ["auto", "low", "high"]
    assert state["fan_mode"] == "auto"
    assert state["swing_modes"] == ["auto", "up", "down"]
    assert state["swing_mode"] == "auto"
    assert state["supported_features"] & ClimateEntityFeature.FAN_MODE
    assert state["supported_features"] & ClimateEntityFeature.SWING_MODE

    await call_entity(hass, "set_fan_mode", fan_mode="high")
    await call_entity(hass, "set_swing_mode", swing_mode="up")
    assert calls.to_unit() == [("set_fan_mode", {"fan_mode": "high"}), ("set_swing_mode", {"swing_mode": "up"})]

    set_unit(hass, "off", fan_mode="high", swing_mode="up")
    await hass.async_block_till_done()
    assert attrs(hass)["fan_mode"] == "high"
    assert attrs(hass)["swing_mode"] == "up"


async def test_passthrough_preset_and_horizontal_swing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """The unit's own presets (such as quiet) and its horizontal swing mirror the unit and are set on it."""
    await start(hass, freezer, calls, mode="off")
    state = attrs(hass)
    assert state["preset_modes"] == ["none", "quiet", "powerful"]
    assert state["preset_mode"] == "none"
    assert state["swing_horizontal_modes"] == ["auto", "left", "right"]
    assert state["swing_horizontal_mode"] == "auto"
    assert state["supported_features"] & ClimateEntityFeature.PRESET_MODE
    assert state["supported_features"] & ClimateEntityFeature.SWING_HORIZONTAL_MODE

    await call_entity(hass, "set_preset_mode", preset_mode="quiet")
    await call_entity(hass, "set_swing_horizontal_mode", swing_horizontal_mode="left")
    assert calls.to_unit() == [
        ("set_preset_mode", {"preset_mode": "quiet"}),
        ("set_swing_horizontal_mode", {"swing_horizontal_mode": "left"}),
    ]

    set_unit(hass, "off", preset_mode="quiet", swing_horizontal_mode="left")
    await hass.async_block_till_done()
    assert attrs(hass)["preset_mode"] == "quiet"
    assert attrs(hass)["swing_horizontal_mode"] == "left"


async def test_preset_survives_steadyroom_running_the_unit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """SteadyRoom's own commands never touch the preset: it only sends mode and setpoint."""
    await start(hass, freezer, calls, mode="off", room=20.0)
    set_unit(hass, "off", preset_mode="quiet")
    await call_entity(hass, "set_hvac_mode", hvac_mode="heat")
    await tick(hass, freezer, 5)
    sent = calls.to_unit()
    assert sent, "SteadyRoom should start the unit"
    assert {service for service, _ in sent} <= {"set_hvac_mode", "set_temperature", "turn_on"}
    assert all("preset_mode" not in data for _, data in sent)
    assert attrs(hass)["preset_mode"] == "quiet"


async def test_passthrough_only_what_the_unit_supports(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A unit without fan and swing gives an entity without them."""
    await start(hass, freezer, calls, mode="off")
    set_unit(hass, "off", supported_features=int(ClimateEntityFeature.TARGET_TEMPERATURE))
    await hass.async_block_till_done()

    features = attrs(hass)["supported_features"]
    assert not features & ClimateEntityFeature.FAN_MODE
    assert not features & ClimateEntityFeature.SWING_MODE
    assert not features & ClimateEntityFeature.SWING_HORIZONTAL_MODE
    assert not features & ClimateEntityFeature.PRESET_MODE
    assert "preset_modes" not in attrs(hass)
    with pytest.raises(HomeAssistantError):
        await call_entity(hass, "set_fan_mode", fan_mode="high")
    with pytest.raises(HomeAssistantError):
        await call_entity(hass, "set_preset_mode", preset_mode="quiet")
    assert calls.to_unit() == []


# ---------------------------------------------------------------- ISC-8 sperre


async def _heat_run_ended_in_auto(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """Auto, a heat run reaches target + 0.2, SteadyRoom switches off, the unit reports off."""
    await start(hass, freezer, calls, mode="heat_cool", room=21.1, unit="heat", setpoint=23.5)
    set_room(hass, 21.2)
    await hass.async_block_till_done()
    assert calls.modes() == ["off"]
    set_unit(hass, "off")
    await hass.async_block_till_done()
    calls.clear()


async def test_sperre_blocks_opposite_start_in_auto(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """After a heat run, Auto does not start cooling during the lock and says why."""
    await _heat_run_ended_in_auto(hass, freezer, calls)
    ended = dt_util.utcnow()

    set_room(hass, 21.6)
    await hass.async_block_till_done()

    assert calls.to_unit() == []
    state = attrs(hass)
    assert state["reason"] == "locked"
    assert state["locked_direction"] == "cool"
    assert state["last_direction"] == "heat"
    assert dt_util.parse_datetime(state["run_ended_at"]) == ended
    assert dt_util.parse_datetime(state["lock_until"]) == ended + timedelta(minutes=15)


async def test_sperre_expires_and_reevaluates_without_trigger(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """When the lock runs out, SteadyRoom decides again on its own and starts cooling."""
    await _heat_run_ended_in_auto(hass, freezer, calls)
    set_room(hass, 21.6)
    await hass.async_block_till_done()

    await tick(hass, freezer, 15 * 60 - 1)
    assert calls.to_unit() == []

    await tick(hass, freezer, 1)
    assert calls.modes() == ["cool"]
    assert attrs(hass)["reason"] == "cooling"
    assert attrs(hass)["locked_direction"] == "off"


async def test_sperre_follows_lock_minutes_number(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A shorter lock time takes effect at once."""
    await _heat_run_ended_in_auto(hass, freezer, calls)
    set_room(hass, 21.6)
    await hass.async_block_till_done()
    await tick(hass, freezer, 5 * 60)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_entity_id(hass, entry, "lock_minutes"), "value": 5}, blocking=True
    )
    await hass.async_block_till_done()
    assert calls.modes() == ["cool"]


async def test_sperre_only_in_auto(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """Mode cool starts right away even after a heat run."""
    await _heat_run_ended_in_auto(hass, freezer, calls)
    set_room(hass, 21.6)
    await hass.async_block_till_done()
    await call_entity(hass, "set_hvac_mode", hvac_mode="cool")
    assert calls.modes() == ["cool"]


async def test_sperre_survives_restart(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """A run that ended five minutes before the restart still locks cooling for ten minutes."""
    ended = dt_util.utcnow() - timedelta(minutes=5)
    mock_restore_cache_with_extra_data(
        hass, [restored_climate("heat_cool", last_direction="heat", run_ended_at=ended.isoformat())]
    )
    set_unit(hass, "off")
    set_room(hass, 21.6)
    await setup_entry(hass)
    await settle(hass, freezer, calls)

    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "locked"
    assert dt_util.parse_datetime(attrs(hass)["lock_until"]) == ended + timedelta(minutes=15)

    await tick(hass, freezer, 10 * 60 - 31)
    assert calls.modes() == ["cool"]


# ---------------------------------------------------------------- ISC-10 sendeschwelle


async def test_sendeschwelle_half_step(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """A setpoint goes to the unit only when it differs by at least half a step."""
    # Heating, room 20.0 (distance 1.0 → offset 1.5), unit reads 23.0 → wanted 24.5.
    await start(hass, freezer, calls, mode="heat", room=20.0, unit="heat", current=23.0, setpoint=24.5)
    assert calls.to_unit() == []

    set_unit(hass, "heat", current=23.0, setpoint=24.3)
    await hass.async_block_till_done()
    assert calls.setpoints() == []

    set_unit(hass, "heat", current=23.0, setpoint=24.0)
    await hass.async_block_till_done()
    assert calls.setpoints() == [24.5]

    calls.clear()
    set_unit(hass, "heat", current=23.5, setpoint=24.5)
    await hass.async_block_till_done()
    assert calls.setpoints() == [25.0]
    assert calls.modes() == []


# ---------------------------------------------------------------- ISC-11 tuer


async def test_tuer_open_60s_switches_off(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """A door open for 60 s switches a running unit off; 59 s do not."""
    hass.states.async_set(DOOR, "off")
    await start(hass, freezer, calls, mode="heat", room=20.0, unit="heat", setpoint=24.5, **{CONF_CONTACTS: [DOOR]})

    hass.states.async_set(DOOR, "on")
    await hass.async_block_till_done()
    await tick(hass, freezer, 59)
    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "heating"

    await tick(hass, freezer, 1)
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "off"})]
    assert attrs(hass)["reason"] == "door_open"


async def test_tuer_open_while_off_prevents_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """An open door keeps a stopped unit from starting, even before the delay."""
    hass.states.async_set(DOOR, "off")
    await start(hass, freezer, calls, mode="heat", room=21.0, **{CONF_CONTACTS: [DOOR, WINDOW]})
    hass.states.async_set(WINDOW, "on")
    await hass.async_block_till_done()

    set_room(hass, 20.0)
    await hass.async_block_till_done()
    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "door_open"


async def test_tuer_close_15s_resumes_previous_direction(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """After 15 s closed, the unit resumes heating although the room alone would not start it."""
    hass.states.async_set(DOOR, "off")
    await start(hass, freezer, calls, mode="heat", room=20.9, unit="heat", setpoint=24.0, **{CONF_CONTACTS: [DOOR]})

    hass.states.async_set(DOOR, "on")
    await hass.async_block_till_done()
    await tick(hass, freezer, 60)
    assert calls.modes() == ["off"]
    set_unit(hass, "off", setpoint=24.0)
    await hass.async_block_till_done()
    calls.clear()

    hass.states.async_set(DOOR, "off")
    await hass.async_block_till_done()
    await tick(hass, freezer, 14)
    assert calls.to_unit() == []

    await tick(hass, freezer, 1)
    # 20.9 is inside the heat band: only a resumed run explains the start.
    assert calls.modes() == ["heat"]
    assert attrs(hass)["reason"] == "heating"


async def test_tuer_close_resume_is_used_once(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """After the resumed run ends in band, the next in-band evaluation does not start it again."""
    hass.states.async_set(DOOR, "off")
    await start(hass, freezer, calls, mode="heat", room=20.9, unit="heat", setpoint=24.0, **{CONF_CONTACTS: [DOOR]})
    hass.states.async_set(DOOR, "on")
    await hass.async_block_till_done()
    await tick(hass, freezer, 60)
    set_unit(hass, "off")
    hass.states.async_set(DOOR, "off")
    await hass.async_block_till_done()
    await tick(hass, freezer, 15)
    set_unit(hass, "heat", setpoint=24.0)
    await hass.async_block_till_done()
    set_room(hass, 21.2)
    await hass.async_block_till_done()
    set_unit(hass, "off")
    set_room(hass, 20.9)
    await hass.async_block_till_done()
    calls.clear()

    set_room(hass, 20.85)
    await hass.async_block_till_done()
    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "in_band"


async def test_tuer_inverted_contacts(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """With inverted contacts, on means closed and off means open."""
    hass.states.async_set(DOOR, "on")
    await start(
        hass,
        freezer,
        calls,
        mode="heat",
        room=20.0,
        unit="heat",
        setpoint=24.5,
        **{CONF_CONTACTS: [DOOR], CONF_CONTACTS_INVERTED: True},
    )
    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "heating"

    hass.states.async_set(DOOR, "off")
    await hass.async_block_till_done()
    await tick(hass, freezer, 60)
    assert calls.modes() == ["off"]
    assert attrs(hass)["reason"] == "door_open"


async def test_tuer_unavailable_contact_counts_as_closed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A contact without a reading does not block the unit."""
    hass.states.async_set(DOOR, STATE_UNAVAILABLE)
    await start(hass, freezer, calls, mode="heat", room=21.0, **{CONF_CONTACTS: [DOOR]})
    set_room(hass, 20.0)
    await hass.async_block_till_done()
    assert calls.modes() == ["heat"]


async def test_tuer_delays_follow_numbers(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """A shorter door-open delay takes effect without reload."""
    hass.states.async_set(DOOR, "off")
    entry = await start(
        hass, freezer, calls, mode="heat", room=20.0, unit="heat", setpoint=24.5, **{CONF_CONTACTS: [DOOR]}
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_entity_id(hass, entry, "door_open_delay"), "value": 10}, blocking=True
    )
    hass.states.async_set(DOOR, "on")
    await hass.async_block_till_done()
    await tick(hass, freezer, 10)
    assert calls.modes() == ["off"]


# ---------------------------------------------------------------- ISC-12 zeitplan


async def test_zeitplan_off_keeps_unit_off(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """Outside the schedule the unit is switched off and does not start."""
    hass.states.async_set(SCHEDULE, "on")
    await start(hass, freezer, calls, mode="heat", room=20.0, unit="heat", setpoint=24.5, **{CONF_SCHEDULE: SCHEDULE})
    assert calls.to_unit() == []

    hass.states.async_set(SCHEDULE, "off")
    await hass.async_block_till_done()
    assert calls.modes() == ["off"]
    assert attrs(hass)["reason"] == "outside_schedule"

    set_unit(hass, "off")
    set_room(hass, 19.0)
    await hass.async_block_till_done()
    assert calls.modes() == ["off"]


async def test_zeitplan_on_allows_start(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """When the schedule turns on, the unit starts."""
    hass.states.async_set(SCHEDULE, "off")
    await start(hass, freezer, calls, mode="heat", room=20.0, **{CONF_SCHEDULE: SCHEDULE})
    assert calls.to_unit() == []

    hass.states.async_set(SCHEDULE, "on")
    await hass.async_block_till_done()
    assert calls.modes() == ["heat"]


async def test_zeitplan_disappearing_keeps_running_unit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A schedule that turns unavailable or vanishes is no end of the schedule: nothing is sent."""
    hass.states.async_set(SCHEDULE, "on")
    await start(hass, freezer, calls, mode="heat", room=20.0, unit="heat", setpoint=24.5, **{CONF_SCHEDULE: SCHEDULE})

    hass.states.async_set(SCHEDULE, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    hass.states.async_set(SCHEDULE, "unknown")
    await hass.async_block_till_done()
    hass.states.async_remove(SCHEDULE)
    await hass.async_block_till_done()

    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "heating"


async def test_zeitplan_keeps_last_answer_outside(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """After a definite off, an unavailable schedule keeps the unit off and says why."""
    hass.states.async_set(SCHEDULE, "off")
    await start(hass, freezer, calls, mode="heat", room=20.0, **{CONF_SCHEDULE: SCHEDULE})
    hass.states.async_set(SCHEDULE, STATE_UNAVAILABLE)
    set_room(hass, 19.0)
    await hass.async_block_till_done()
    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "outside_schedule"


async def test_zeitplan_cold_start_without_schedule_state_sends_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """While Home Assistant starts and the schedule has no state yet, a running unit is left alone."""
    mock_restore_cache_with_extra_data(hass, [restored_climate("heat")])
    hass.set_state(CoreState.not_running)
    set_unit(hass, "heat", setpoint=24.5)
    set_room(hass, 20.0)
    await setup_entry(hass, **{CONF_SCHEDULE: SCHEDULE})
    set_room(hass, 20.1)
    set_unit(hass, "heat", setpoint=23.0)
    await hass.async_block_till_done()
    await tick(hass, freezer, 31)
    assert calls.to_unit() == []


# ---------------------------------------------------------------- ISC-13 wiederkehr


async def test_wiederkehr_resends_after_30s(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """A unit back from unavailable gets mode and setpoint again after 30 s, even if they look right."""
    await start(hass, freezer, calls, mode="heat", room=20.0, unit="heat", current=23.0, setpoint=24.5)

    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert attrs(hass)["reason"] == "unit_unavailable"

    set_unit(hass, "heat", current=23.0, setpoint=24.5)
    await hass.async_block_till_done()
    await tick(hass, freezer, 29)
    assert calls.to_unit() == []

    await tick(hass, freezer, 1)
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "heat"}), ("set_temperature", {"temperature": 24.5})]


async def test_wiederkehr_resends_off(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """The incident: a reconnecting unit that claims off gets off again (it may still be heating)."""
    await start(hass, freezer, calls, mode="off", room=20.0)

    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    set_unit(hass, "off", current=27.5, setpoint=27.5)
    await hass.async_block_till_done()
    assert calls.to_unit() == []

    await tick(hass, freezer, 30)
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "off"})]


async def test_wiederkehr_unknown_counts_as_unavailable(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Returning from unknown is a return as well."""
    await start(hass, freezer, calls, mode="off", room=20.0)
    hass.states.async_set(UNIT, "unknown")
    await hass.async_block_till_done()
    set_unit(hass, "off")
    await hass.async_block_till_done()
    await tick(hass, freezer, 30)
    assert calls.modes() == ["off"]


async def test_wiederkehr_unit_gone_again_cancels_resend(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A unit that drops again before the settle time gets nothing; the re-send comes after its next return."""
    await start(hass, freezer, calls, mode="off", room=20.0)
    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    set_unit(hass, "off")
    await hass.async_block_till_done()
    await tick(hass, freezer, 10)
    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    await tick(hass, freezer, 30)
    assert calls.to_unit() == []

    set_unit(hass, "off")
    await hass.async_block_till_done()
    await tick(hass, freezer, 30)
    assert calls.modes() == ["off"]


async def test_wiederkehr_startup_evaluation(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """While Home Assistant starts nothing is sent; once started it evaluates, and re-sends after 30 s."""
    mock_restore_cache_with_extra_data(hass, [restored_climate("heat")])
    hass.set_state(CoreState.not_running)
    set_unit(hass, "off")
    set_room(hass, 20.0)
    await setup_entry(hass)
    # Before "started" the evaluation runs only on input changes, not for the start.
    calls.clear()

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert calls.modes() == ["heat"]

    calls.clear()
    set_unit(hass, "heat", setpoint=24.5)
    await hass.async_block_till_done()
    assert calls.to_unit() == []
    await tick(hass, freezer, 30)
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "heat"}), ("set_temperature", {"temperature": 24.5})]


async def test_wiederkehr_force_waits_for_room_sensor(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A heat re-send that falls into a sensor gap is made as soon as the sensor is back."""
    await start(hass, freezer, calls, mode="heat", room=20.0, unit="heat", setpoint=24.5)
    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    set_unit(hass, "heat", setpoint=24.5)
    set_room(hass, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    await tick(hass, freezer, 30)
    assert calls.to_unit() == []

    set_room(hass, 20.0)
    await hass.async_block_till_done()
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "heat"}), ("set_temperature", {"temperature": 24.5})]


# ---------------------------------------------------------------- ISC-14 fuehler


async def test_fuehler_fallback_sensor(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """Without the room sensor the fallback decides and shows as current temperature."""
    set_room(hass, 19.98, FALLBACK)
    await start(hass, freezer, calls, mode="heat", room=STATE_UNAVAILABLE, **{CONF_FALLBACK_SENSOR: FALLBACK})
    assert attrs(hass)["current_temperature"] == pytest.approx(19.98, abs=0.05)
    # Heating started from the fallback (sent before settle); the room sensor takes over when back.
    set_room(hass, "not a number")
    set_unit(hass, "heat", setpoint=24.5)
    await hass.async_block_till_done()
    assert attrs(hass)["reason"] == "heating"

    set_room(hass, 21.2)
    await hass.async_block_till_done()
    assert calls.modes() == ["off"]


async def test_fuehler_both_missing_sends_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Both sensors missing: no command at all, reason sensor_missing, even on mode and target changes."""
    set_room(hass, STATE_UNAVAILABLE, FALLBACK)
    await start(
        hass,
        freezer,
        calls,
        mode="heat",
        room=STATE_UNAVAILABLE,
        unit="heat",
        setpoint=24.5,
        **{CONF_FALLBACK_SENSOR: FALLBACK},
    )
    assert attrs(hass)["reason"] == "sensor_missing"
    assert attrs(hass)["current_temperature"] is None

    await call_entity(hass, "set_hvac_mode", hvac_mode="cool")
    await call_entity(hass, "set_temperature", temperature=25.0)
    await tick(hass, freezer, 60)
    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "sensor_missing"
    assert attrs(hass)["distance"] is None


async def test_fuehler_missing_mode_off_still_switches_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Mode off needs no room temperature: a heating unit gets off although both sensors are gone."""
    set_room(hass, STATE_UNAVAILABLE, FALLBACK)
    await start(
        hass,
        freezer,
        calls,
        mode="heat",
        room=STATE_UNAVAILABLE,
        unit="heat",
        setpoint=24.5,
        **{CONF_FALLBACK_SENSOR: FALLBACK},
    )
    assert calls.to_unit() == []

    await call_entity(hass, "set_hvac_mode", hvac_mode="off")
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "off"})]
    assert attrs(hass)["reason"] == "off_mode"


async def test_fuehler_missing_door_open_long_switches_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A door open for 60 s switches the unit off even while the room sensor is missing."""
    hass.states.async_set(DOOR, "off")
    await start(
        hass, freezer, calls, mode="heat", room=STATE_UNAVAILABLE, unit="heat", setpoint=24.5, **{CONF_CONTACTS: [DOOR]}
    )
    assert attrs(hass)["reason"] == "sensor_missing"

    hass.states.async_set(DOOR, "on")
    await hass.async_block_till_done()
    await tick(hass, freezer, 60)
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "off"})]
    assert attrs(hass)["reason"] == "door_open"


async def test_fuehler_missing_outside_schedule_switches_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """The end of the schedule switches the unit off even while the room sensor is missing."""
    hass.states.async_set(SCHEDULE, "on")
    await start(
        hass, freezer, calls, mode="heat", room=STATE_UNAVAILABLE, unit="heat", setpoint=24.5, **{CONF_SCHEDULE: SCHEDULE}
    )
    hass.states.async_set(SCHEDULE, "off")
    await hass.async_block_till_done()
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "off"})]
    assert attrs(hass)["reason"] == "outside_schedule"


async def test_fuehler_missing_unit_reading_blocks_only_heat_and_cool(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Without the unit's own reading no heat starts, but off still goes out."""
    await start(hass, freezer, calls, mode="heat", room=21.0, unit="heat", setpoint=24.5)
    set_unit(hass, "heat", current=None, setpoint=24.5)
    set_room(hass, 20.0)
    await hass.async_block_till_done()
    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "unit_unavailable"

    await call_entity(hass, "set_hvac_mode", hvac_mode="off")
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "off"})]


# ---------------------------------------------------------------- ISC-15 diagnose


async def test_diagnose_heating_values(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """Distance, offset, sent setpoint, last direction and lock appear as attributes."""
    await start(hass, freezer, calls, mode="heat", room=21.0)
    set_room(hass, 19.98)
    await hass.async_block_till_done()
    set_unit(hass, "heat", setpoint=24.5)
    await hass.async_block_till_done()

    state = attrs(hass)
    assert state["distance"] == 1.02
    assert state["offset"] == 1.5
    assert state["sent_setpoint"] == 24.5
    assert state["last_direction"] == "heat"
    assert state["run_ended_at"] is None
    assert state["locked_direction"] == "off"
    assert state["lock_until"] is None
    assert state["reason"] == "heating"


async def test_diagnose_cooling_offset_is_negative(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Cooling shows a negative distance and offset; the unit gets its reading minus the offset."""
    await start(hass, freezer, calls, mode="cool", room=21.0, current=25.0)
    set_room(hass, 22.0)
    await hass.async_block_till_done()

    state = attrs(hass)
    assert state["distance"] == -1.0
    assert state["offset"] == -1.5
    assert state["sent_setpoint"] == 23.5
    assert calls.setpoints() == [23.5]


@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        ("not_configured", "not_configured"),
        ("off", "off_mode"),
        ("in_band", "in_band"),
        ("heating", "heating"),
        ("cooling", "cooling"),
        ("door", "door_open"),
        ("schedule", "outside_schedule"),
        ("locked", "locked"),
        ("locked_and_door", "door_open"),
        ("sensor", "sensor_missing"),
        ("unit", "unit_unavailable"),
        ("unit_reading", "unit_unavailable"),
    ],
)
async def test_diagnose_every_reason_is_visible(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog, scenario: str, reason: str
) -> None:
    """Each reason the unit runs or rests shows up in the reason attribute."""
    hass.states.async_set(DOOR, "on" if scenario in ("door", "locked_and_door") else "off")
    hass.states.async_set(SCHEDULE, "off" if scenario == "schedule" else "on")
    if scenario.startswith("locked"):
        mock_restore_cache_with_extra_data(
            hass,
            [restored_climate("heat_cool", last_direction="heat", run_ended_at=dt_util.utcnow().isoformat())],
        )
    mode = {"off": "off", "cooling": "cool", "locked": "heat_cool", "locked_and_door": "heat_cool"}.get(scenario, "heat")
    room = {
        "in_band": 21.0,
        "cooling": 22.0,
        "locked": 22.0,
        "locked_and_door": 22.0,
        "sensor": STATE_UNAVAILABLE,
    }.get(scenario, 20.0)
    set_unit(hass, "off", current=None if scenario == "unit_reading" else 23.0)
    if scenario == "unit":
        hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    set_room(hass, room)
    await setup_entry(hass, **{CONF_CONTACTS: [DOOR], CONF_SCHEDULE: SCHEDULE})
    if not scenario.startswith("locked") and scenario != "not_configured":
        await call_entity(hass, "set_temperature", temperature=TARGET, hvac_mode=mode)

    assert attrs(hass)["reason"] == reason


# ---------------------------------------------------------------- ISC-16 restore


async def test_restore_mode_target_direction(hass: HomeAssistant) -> None:
    """Mode, target, last direction and end of the last run come back after a restart."""
    ended = (dt_util.utcnow() - timedelta(hours=1)).isoformat()
    mock_restore_cache_with_extra_data(
        hass, [restored_climate("cool", target=23.5, last_direction="cool", run_ended_at=ended)]
    )
    set_unit(hass, "off")
    set_room(hass, 23.5)
    await setup_entry(hass)

    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == "cool"
    assert state.attributes["temperature"] == 23.5
    assert state.attributes["last_direction"] == "cool"
    assert dt_util.parse_datetime(state.attributes["run_ended_at"]) == dt_util.parse_datetime(ended)


async def test_restore_door_resume(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """A run a door interrupted before the restart resumes once the contacts are closed long enough."""
    mock_restore_cache_with_extra_data(hass, [restored_climate("heat", door_resume="heat")])
    hass.states.async_set(DOOR, "off")
    set_unit(hass, "off")
    set_room(hass, 20.9)
    await setup_entry(hass, **{CONF_CONTACTS: [DOOR]})
    await tick(hass, freezer, 15)
    assert calls.modes()[:1] == ["heat"]


async def test_restore_round_trip(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """What the entity stores at shutdown is what it restores at the next start."""
    entry = await start(hass, freezer, calls, mode="heat_cool", room=21.1, unit="heat", setpoint=23.5)
    await call_entity(hass, "set_temperature", temperature=22.0)
    set_unit(hass, "off")
    await hass.async_block_till_done()
    ended = dt_util.utcnow()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await async_mock_restore_state_shutdown_restart(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == "heat_cool"
    assert state.attributes["temperature"] == 22.0
    assert state.attributes["last_direction"] == "heat"
    assert dt_util.parse_datetime(state.attributes["run_ended_at"]) == ended


async def test_restore_unfinished_run_ends_when_unit_is_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A run still on at shutdown ends when the unit reports off after the restart: the lock starts then."""
    mock_restore_cache_with_extra_data(hass, [restored_climate("heat_cool", last_direction="heat")])
    set_unit(hass, "off")
    set_room(hass, 21.0)
    await setup_entry(hass)
    assert attrs(hass)["locked_direction"] == "cool"
    assert dt_util.parse_datetime(attrs(hass)["run_ended_at"]) == dt_util.utcnow()


async def test_restore_ignores_broken_data(hass: HomeAssistant) -> None:
    """Unreadable stored data falls back to off and 21 °C."""
    mock_restore_cache_with_extra_data(hass, [(State(ENTITY, "heat"), {"hvac_mode": "boost", "target": "warm"})])
    set_unit(hass, "off")
    set_room(hass, 21.0)
    await setup_entry(hass)
    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == "off"
    assert state.attributes["temperature"] == 21.0


# ---------------------------------------------------------------- ISC-21 beobachten


async def _observe(hass: HomeAssistant, entry: MockConfigEntry, on: bool) -> None:
    """Start (on) or end (off) a test run: switch "Control the unit" the opposite way."""
    await hass.services.async_call(
        "switch", "turn_off" if on else "turn_on", {"entity_id": control_switch_id(hass, entry)}, blocking=True
    )
    await hass.async_block_till_done()


async def test_beobachten_switch_follows_entry_option(hass: HomeAssistant) -> None:
    """The control switch is a configuration entity showing the entry's option (controlling here)."""
    set_unit(hass, "off")
    set_room(hass, 21.0)
    entry = await setup_entry(hass)
    switch = control_switch_id(hass, entry)
    state = hass.states.get(switch)
    assert state is not None
    assert state.state == "on"
    registry_entry = er.async_get(hass).async_get(switch)
    assert registry_entry is not None
    assert registry_entry.entity_category is EntityCategory.CONFIG
    assert attrs(hass)["controls_unit"] is True


async def test_beobachten_sends_nothing_across_heat_cool_off_door_reconnect(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """With observation on, no decision of SteadyRoom reaches the unit, while the would_* trace follows."""
    hass.states.async_set(DOOR, "off")
    set_unit(hass, "off")
    set_room(hass, 21.0)
    entry = await setup_entry(hass, **{CONF_CONTACTS: [DOOR]})
    await _observe(hass, entry, True)
    await settle(hass, freezer, calls)
    calls.clear()

    trace: list[tuple[str | None, float | None]] = []

    def note() -> None:
        state = attrs(hass)
        trace.append((state["would_hvac_mode"], state["would_setpoint"]))

    await call_entity(hass, "set_temperature", temperature=TARGET, hvac_mode="heat")
    set_room(hass, 19.98)
    await hass.async_block_till_done()
    note()
    set_unit(hass, "heat", setpoint=21.0)  # the old automation drives the unit
    await hass.async_block_till_done()
    await call_entity(hass, "set_hvac_mode", hvac_mode="cool")
    set_room(hass, 22.0)
    await hass.async_block_till_done()
    note()
    hass.states.async_set(DOOR, "on")
    await hass.async_block_till_done()
    await tick(hass, freezer, 60)
    note()
    hass.states.async_set(DOOR, "off")
    await hass.async_block_till_done()
    await tick(hass, freezer, 15)
    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    set_unit(hass, "heat", setpoint=21.0)
    await hass.async_block_till_done()
    await tick(hass, freezer, 30)
    await call_entity(hass, "set_hvac_mode", hvac_mode="off")
    note()

    assert calls.to_unit() == []
    assert trace == [("heat", 24.5), ("cool", 21.5), ("off", None), ("off", None)]
    assert attrs(hass)["controls_unit"] is False
    assert attrs(hass)["reason"] == "off_mode"


async def test_beobachten_lock_follows_the_real_unit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """The lock starts when the real unit ends its run, whoever switched it off."""
    set_unit(hass, "heat", setpoint=23.5)
    set_room(hass, 21.1)
    entry = await setup_entry(hass)
    await _observe(hass, entry, True)
    calls.clear()
    await call_entity(hass, "set_temperature", temperature=TARGET, hvac_mode="heat_cool")
    set_unit(hass, "off")
    set_room(hass, 21.6)
    await hass.async_block_till_done()

    state = attrs(hass)
    assert state["last_direction"] == "heat"
    assert state["locked_direction"] == "cool"
    assert state["reason"] == "locked"
    assert state["would_hvac_mode"] == "off"
    assert calls.to_unit() == []


async def test_beobachten_switching_off_sends_everything(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Leaving observation re-sends mode and setpoint at once, even if the unit already shows them."""
    set_unit(hass, "heat", current=23.0, setpoint=24.5)
    set_room(hass, 19.98)
    entry = await setup_entry(hass)
    await _observe(hass, entry, True)
    await call_entity(hass, "set_temperature", temperature=TARGET, hvac_mode="heat")
    await settle(hass, freezer, calls)

    await _observe(hass, entry, False)
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "heat"}), ("set_temperature", {"temperature": 24.5})]
    assert attrs(hass)["controls_unit"] is True
    assert attrs(hass)["sent_setpoint"] == 24.5


async def test_beobachten_survives_a_crash(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """After a crash (no restore cache written) the device keeps observing: the flag lives in the entry."""
    mock_restore_cache_with_extra_data(hass, [restored_climate("heat")])
    set_unit(hass, "off")
    set_room(hass, 19.0)
    entry = await setup_entry(hass, **{CONF_OBSERVE_ONLY: True})
    await tick(hass, freezer, 31)

    assert hass.states.get(control_switch_id(hass, entry)).state == "off"  # type: ignore[union-attr]
    assert calls.to_unit() == []
    assert attrs(hass)["would_hvac_mode"] == "heat"


async def test_beobachten_replaces_the_former_observe_switch(hass: HomeAssistant) -> None:
    """Updating from 0.1.2 removes the "Observe only" switch and keeps its meaning, inverted."""
    set_unit(hass, "off")
    set_room(hass, 21.0)
    entry = await setup_entry(hass, legacy_observe_switch=True, **{CONF_OBSERVE_ONLY: True})

    assert er.async_get(hass).async_get(LEGACY_OBSERVE_SWITCH) is None
    assert hass.states.get(LEGACY_OBSERVE_SWITCH) is None
    assert hass.states.get(control_switch_id(hass, entry)).state == "off"  # type: ignore[union-attr]
    assert attrs(hass)["controls_unit"] is False


async def test_beobachten_switch_writes_the_entry(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Every toggle lands in the entry options at once, without a reload."""
    set_unit(hass, "off")
    set_room(hass, 21.0)
    entry = await setup_entry(hass)
    entity_before = hass.data[CLIMATE_COMPONENT].get_entity(ENTITY)
    await _observe(hass, entry, True)
    assert entry.options[CONF_OBSERVE_ONLY] is True
    await _observe(hass, entry, False)
    assert entry.options[CONF_OBSERVE_ONLY] is False
    # Same entity object: the entry was not reloaded.
    assert hass.data[CLIMATE_COMPONENT].get_entity(ENTITY) is entity_before


async def test_beobachten_fan_and_swing_still_pass_through(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Fan and swing are explicit user actions, not decisions: they reach the unit while observing."""
    set_unit(hass, "off")
    set_room(hass, 21.0)
    entry = await setup_entry(hass)
    await _observe(hass, entry, True)
    await call_entity(hass, "set_fan_mode", fan_mode="low")
    await call_entity(hass, "set_preset_mode", preset_mode="quiet")
    assert calls.to_unit() == [("set_fan_mode", {"fan_mode": "low"}), ("set_preset_mode", {"preset_mode": "quiet"})]


# ---------------------------------------------------------------- audit round: failures, staleness, renames


async def test_tuer_resume_kept_until_command_succeeds(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog, unit_sim: UnitSim
) -> None:
    """If the resume command fails, the interrupted direction is not forgotten: the retry resumes it."""
    unit_sim.feedback = True
    hass.states.async_set(DOOR, "off")
    await start(hass, freezer, calls, mode="heat", room=20.9, unit="heat", setpoint=24.0, **{CONF_CONTACTS: [DOOR]})
    hass.states.async_set(DOOR, "on")
    await hass.async_block_till_done()
    await tick(hass, freezer, 60)
    assert calls.modes() == ["off"]
    calls.clear()

    unit_sim.fail_next("set_hvac_mode")
    hass.states.async_set(DOOR, "off")
    await hass.async_block_till_done()
    await tick(hass, freezer, 15)
    assert unit_sim.failed == [("set_hvac_mode", {"hvac_mode": "heat"})]
    assert calls.to_unit() == []

    await tick(hass, freezer, 30)
    # 20.9 is inside the band: only the kept resume explains the start.
    assert calls.modes() == ["heat"]


async def test_wiederkehr_any_exception_is_caught_and_retried(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog, unit_sim: UnitSim
) -> None:
    """A unit integration raising anything (not only HomeAssistantError) is logged; 30 s later SteadyRoom tries again."""
    await start(hass, freezer, calls, mode="heat", room=21.0)
    unit_sim.fail_next("set_hvac_mode", RuntimeError("cloud exploded"))
    set_room(hass, 20.0)
    await hass.async_block_till_done()
    assert unit_sim.failed == [("set_hvac_mode", {"hvac_mode": "heat"})]
    assert calls.to_unit() == [("set_temperature", {"temperature": 24.5})]
    calls.clear()

    await tick(hass, freezer, 30)
    assert calls.modes() == ["heat"]


async def test_wiederkehr_force_survives_a_crashing_evaluation(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calls: CallLog,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the forced evaluation itself crashes, the next evaluation is still forced."""
    await start(hass, freezer, calls, mode="heat", room=20.0, unit="heat", setpoint=24.5)
    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    set_unit(hass, "heat", setpoint=24.5)
    await hass.async_block_till_done()

    from custom_components.steadyroom import climate as climate_module

    real_setpoint = climate_module.logic.setpoint
    crashes = []

    def crash_once(*args: Any, **kwargs: Any) -> float | None:
        if not crashes:
            crashes.append(True)
            raise ZeroDivisionError("simulated bug")
        return real_setpoint(*args, **kwargs)

    monkeypatch.setattr(climate_module.logic, "setpoint", crash_once)
    await tick(hass, freezer, 30)
    assert crashes == [True]
    assert calls.to_unit() == []

    set_room(hass, 20.05)
    await hass.async_block_till_done()
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "heat"}), ("set_temperature", {"temperature": 24.5})]
    assert "evaluation failed" in caplog.text


async def test_sendeschwelle_failed_setpoint_retries_and_is_not_reported_as_sent(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog, unit_sim: UnitSim
) -> None:
    """sent_setpoint only shows a setpoint the unit accepted; a failed one is retried after 30 s."""
    await start(hass, freezer, calls, mode="heat", room=21.0)
    assert attrs(hass)["sent_setpoint"] is None
    unit_sim.fail_next("set_temperature")
    set_room(hass, 20.0)
    await hass.async_block_till_done()
    assert unit_sim.failed == [("set_temperature", {"temperature": 24.5})]
    assert attrs(hass)["sent_setpoint"] is None
    assert attrs(hass)["would_setpoint"] == 24.5

    await tick(hass, freezer, 30)
    assert calls.setpoints() == [24.5]
    assert attrs(hass)["sent_setpoint"] == 24.5


async def test_fuehler_max_age_makes_stale_sensor_missing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """With a maximum age, a room sensor that stops reporting falls back, then counts as missing, on its own."""
    set_room(hass, 21.5, FALLBACK)
    entry = await start(hass, freezer, calls, mode="heat", room=20.0, **{CONF_FALLBACK_SENSOR: FALLBACK})
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_entity_id(hass, entry, "sensor_max_age"), "value": 10}, blocking=True
    )
    await hass.async_block_till_done()
    assert attrs(hass)["current_temperature"] == 20.0

    await tick(hass, freezer, 9 * 60)
    set_room(hass, 21.5, FALLBACK)  # the fallback keeps reporting the same value
    await hass.async_block_till_done()
    await tick(hass, freezer, 60)
    assert attrs(hass)["current_temperature"] == 21.5
    assert attrs(hass)["distance"] == -0.5

    await tick(hass, freezer, 9 * 60)
    assert attrs(hass)["reason"] == "sensor_missing"
    assert attrs(hass).get("current_temperature") is None


async def test_fuehler_max_age_off_by_default(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Without a maximum age an old reading stays valid."""
    await start(hass, freezer, calls, mode="heat", room=20.0)
    await tick(hass, freezer, 24 * 3600)
    assert attrs(hass)["current_temperature"] == 20.0
    assert attrs(hass)["reason"] == "heating"


async def test_nur_unterlage_follows_a_renamed_unit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A renamed unit is followed to its new id; the old id, reused by another entity, gets nothing."""
    registry = er.async_get(hass)
    registry.async_get_or_create("climate", "simulated", "unit-1", suggested_object_id="unit")
    entry = await start(hass, freezer, calls, mode="heat", room=21.0)

    registry.async_update_entity(UNIT, new_entity_id="climate.unit_new")
    await hass.async_block_till_done()
    assert entry.options[CONF_UNDERLYING] == "climate.unit_new"

    hass.states.async_set("climate.unit_new", "off", {"current_temperature": 23.0, "temperature": 20.0})
    set_unit(hass, "off")  # another climate entity now uses the old id
    await hass.async_block_till_done()
    calls.clear()
    set_room(hass, 20.0)
    await hass.async_block_till_done()
    await tick(hass, freezer, 31)

    targets = {tuple(call.entity_ids) for call in calls if call.domain == "climate" and ENTITY not in call.entity_ids}
    assert targets == {("climate.unit_new",)}


async def test_nur_unterlage_renamed_sensor_is_followed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Renaming the room sensor rewrites the entry and keeps the room temperature coming."""
    registry = er.async_get(hass)
    registry.async_get_or_create("sensor", "simulated", "room-1", suggested_object_id="room")
    entry = await start(hass, freezer, calls, mode="heat", room=21.0)
    registry.async_update_entity(ROOM, new_entity_id="sensor.room_centre")
    await hass.async_block_till_done()
    assert entry.options[CONF_ROOM_SENSOR] == "sensor.room_centre"
    set_room(hass, 18.5, "sensor.room_centre")
    await hass.async_block_till_done()
    assert attrs(hass)["current_temperature"] == 18.5


async def test_nur_unterlage_removed_unit_is_never_commanded(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """After the unit's entity is removed, a new entity with the same id is not commanded."""
    registry = er.async_get(hass)
    registry.async_get_or_create("climate", "simulated", "unit-1", suggested_object_id="unit")
    await start(hass, freezer, calls, mode="heat", room=21.0)

    registry.async_remove(UNIT)
    await hass.async_block_till_done()
    set_unit(hass, "off")
    set_room(hass, 19.0)
    await hass.async_block_till_done()
    await tick(hass, freezer, 31)

    assert calls.to_unit() == []
    assert attrs(hass)["reason"] == "unit_unavailable"
    with pytest.raises(HomeAssistantError):
        await call_entity(hass, "set_fan_mode", fan_mode="low")


async def test_wiederkehr_sends_nothing_before_settling(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """A returning unit that disagrees gets no command before the 30 s settle; then it gets one."""
    await start(hass, freezer, calls, mode="off", room=20.0)
    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    set_unit(hass, "heat", setpoint=27.5)
    await hass.async_block_till_done()
    set_room(hass, 20.1)
    await hass.async_block_till_done()
    await tick(hass, freezer, 29)
    assert calls.to_unit() == []

    await tick(hass, freezer, 1)
    assert calls.to_unit() == [("set_hvac_mode", {"hvac_mode": "off"})]


async def test_wiederkehr_unavailable_is_no_run_end(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """heat → unavailable → off does not start the lock: the run's end was not observed."""
    await start(hass, freezer, calls, mode="heat_cool", room=21.0, unit="heat", setpoint=23.5)
    hass.states.async_set(UNIT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    set_unit(hass, "off")
    await hass.async_block_till_done()

    state = attrs(hass)
    assert state["run_ended_at"] is None
    assert state["locked_direction"] == "off"


async def test_nur_unterlage_commands_carry_their_own_context(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Automatic commands get a fresh context per evaluation; fan and swing keep the user's."""
    await start(hass, freezer, calls, mode="heat", room=21.0)
    user = Context()
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": ENTITY, "temperature": 22.0}, blocking=True, context=user
    )
    await hass.async_block_till_done()
    first = [call for call in calls if call.entity_ids == [UNIT]]
    assert [call.service for call in first] == ["set_hvac_mode", "set_temperature"]
    assert {call.context_id for call in first} != {user.id}
    assert len({call.context_id for call in first}) == 1

    set_room(hass, 19.0)
    set_unit(hass, "heat", setpoint=20.0)
    await hass.async_block_till_done()
    second = [call for call in calls if call.entity_ids == [UNIT]][len(first) :]
    assert second
    assert second[0].context_id != first[0].context_id

    fan_user = Context()
    await hass.services.async_call(
        "climate", "set_fan_mode", {"entity_id": ENTITY, "fan_mode": "low"}, blocking=True, context=fan_user
    )
    fan = [call for call in calls if call.entity_ids == [UNIT] and call.service == "set_fan_mode"]
    assert [call.context_id for call in fan] == [fan_user.id]


# ---------------------------------------------------------------- ISC-24 nur_unterlage


async def test_nur_unterlage_no_call_targets_anything_else(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog
) -> None:
    """Across heat, cool, door, schedule, reconnect and passthrough, SteadyRoom only ever calls the unit."""
    hass.states.async_set(DOOR, "off")
    hass.states.async_set(SCHEDULE, "on")
    set_room(hass, 20.0, FALLBACK)
    entry = await start(
        hass,
        freezer,
        calls,
        mode="heat",
        room=20.0,
        **{CONF_CONTACTS: [DOOR], CONF_SCHEDULE: SCHEDULE, CONF_FALLBACK_SENSOR: FALLBACK},
    )
    steps = [
        lambda: set_room(hass, 22.5),
        lambda: hass.states.async_set(DOOR, "on"),
        lambda: hass.states.async_set(DOOR, "off"),
        lambda: hass.states.async_set(SCHEDULE, "off"),
        lambda: hass.states.async_set(SCHEDULE, "on"),
        lambda: hass.states.async_set(UNIT, STATE_UNAVAILABLE),
        lambda: set_unit(hass, "heat"),
        lambda: set_room(hass, STATE_UNAVAILABLE),
        lambda: set_room(hass, 19.0),
    ]
    switch = control_switch_id(hass, entry)
    for step in steps:
        step()
        await hass.async_block_till_done()
        await tick(hass, freezer, 61)
    await call_entity(hass, "set_hvac_mode", hvac_mode="cool")
    await call_entity(hass, "set_fan_mode", fan_mode="low")
    await call_entity(hass, "set_swing_mode", swing_mode="down")
    await call_entity(hass, "set_hvac_mode", hvac_mode="heat_cool")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_entity_id(hass, entry, "heat_start"), "value": 0.5}, blocking=True
    )
    await tick(hass, freezer, 61)
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    await call_entity(hass, "set_hvac_mode", hvac_mode="cool")
    await tick(hass, freezer, 61)
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await tick(hass, freezer, 61)

    own_entities = {ENTITY, switch} | {number_entity_id(hass, entry, spec.key) for spec in NUMBER_SPECS}
    from_steadyroom = [call for call in calls if not set(call.entity_ids) <= own_entities]
    assert from_steadyroom, "the scenario must make SteadyRoom send commands"
    assert all(call.domain == "climate" and call.entity_ids == [UNIT] for call in from_steadyroom), from_steadyroom
    for entity_id in (ROOM, FALLBACK, DOOR, SCHEDULE):
        assert all(entity_id not in call.entity_ids for call in calls)
