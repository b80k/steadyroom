"""Test helpers: a simulated air conditioner, sensors, and a record of every service call."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.steadyroom.const import (
    CONF_CONTACTS,
    CONF_CONTACTS_INVERTED,
    CONF_OBSERVE_ONLY,
    CONF_ROOM_SENSOR,
    CONF_UNDERLYING,
    DOMAIN,
    NUMBER_SPECS,
)

UNIT = "climate.unit"
ROOM = "sensor.room"
FALLBACK = "sensor.fallback"
DOOR = "binary_sensor.door"
WINDOW = "binary_sensor.window"
SCHEDULE = "schedule.plan"
ENTITY = "climate.wohnzimmer"
TITLE = "Wohnzimmer"

UNIT_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.SWING_MODE
    | ClimateEntityFeature.SWING_HORIZONTAL_MODE
    | ClimateEntityFeature.PRESET_MODE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


@dataclass(frozen=True)
class Call:
    """One service call seen on the bus."""

    domain: str
    service: str
    data: dict[str, Any]
    context_id: str = ""

    @property
    def entity_ids(self) -> list[str]:
        """Targets of the call, always as a list."""
        target = self.data.get("entity_id", [])
        return [target] if isinstance(target, str) else list(target)


class CallLog(list[Call]):
    """Every service call of a test, with filters for the ones SteadyRoom sends to the unit."""

    def to_unit(self) -> list[tuple[str, dict[str, Any]]]:
        """(service, data without entity_id) of every call to the simulated unit."""
        return [
            (call.service, {k: v for k, v in call.data.items() if k != "entity_id"})
            for call in self
            if call.domain == "climate" and call.entity_ids == [UNIT]
        ]

    def modes(self) -> list[str]:
        """hvac_mode of every set_hvac_mode call to the unit."""
        return [data["hvac_mode"] for service, data in self.to_unit() if service == "set_hvac_mode"]

    def setpoints(self) -> list[float]:
        """temperature of every set_temperature call to the unit."""
        return [data["temperature"] for service, data in self.to_unit() if service == "set_temperature"]


class UnitSim:
    """The simulated unit's reaction to commands: failures on demand, state feedback if wanted.

    Installed by the ``unit_sim`` fixture around the service registry, so
    SteadyRoom's real service calls hit it exactly as they would hit a unit.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.feedback = False
        self._failures: list[tuple[str, BaseException]] = []
        self.failed: list[tuple[str, dict[str, Any]]] = []

    def fail_next(self, service: str, error: BaseException | None = None) -> None:
        """The next call of ``service`` to the unit raises ``error``."""
        self._failures.append((service, error or HomeAssistantError(f"unit refused {service}")))

    def before(self, service: str, data: dict[str, Any]) -> None:
        """Raise a planned failure for this call, if any."""
        for index, (planned, error) in enumerate(self._failures):
            if planned == service:
                del self._failures[index]
                self.failed.append((service, data))
                raise error

    def after(self, service: str, data: dict[str, Any]) -> None:
        """Show the effect of a successful command on the unit's state."""
        if not self.feedback or (state := self.hass.states.get(UNIT)) is None:
            return
        attributes = dict(state.attributes)
        new_state = state.state
        if service == "set_hvac_mode":
            new_state = str(data["hvac_mode"])
        elif service == "set_temperature":
            attributes["temperature"] = data["temperature"]
        self.hass.states.async_set(UNIT, new_state, attributes)


def set_unit(
    hass: HomeAssistant,
    state: str = "off",
    *,
    current: float | None = 23.0,
    setpoint: float | None = 20.0,
    **attributes: Any,
) -> None:
    """Show the simulated unit in a state, with its own reading and setpoint."""
    base: dict[str, Any] = {
        "hvac_modes": ["off", "heat", "cool", "heat_cool", "dry", "fan_only"],
        "min_temp": 16,
        "max_temp": 30,
        "target_temp_step": 0.5,
        "fan_modes": ["auto", "low", "high"],
        "fan_mode": "auto",
        "swing_modes": ["auto", "up", "down"],
        "swing_mode": "auto",
        "swing_horizontal_modes": ["auto", "left", "right"],
        "swing_horizontal_mode": "auto",
        "preset_modes": ["none", "quiet", "powerful"],
        "preset_mode": "none",
        "supported_features": int(UNIT_FEATURES),
    }
    if current is not None:
        base["current_temperature"] = current
    if setpoint is not None:
        base["temperature"] = setpoint
    hass.states.async_set(UNIT, state, base | attributes)


def set_room(hass: HomeAssistant, value: float | str, entity_id: str = ROOM) -> None:
    """Show a room temperature."""
    hass.states.async_set(entity_id, str(value), {"device_class": "temperature", "unit_of_measurement": "°C"})


async def setup_entry(hass: HomeAssistant, *, enable_fine_tuning: bool = True, **options: Any) -> MockConfigEntry:
    """Create and set up a SteadyRoom entry over the simulated unit.

    Fine-tuning values are disabled by default in a real install; most tests drive
    them, so they are enabled here unless the test checks the real default.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TITLE,
        data={},
        options={
            CONF_UNDERLYING: UNIT,
            CONF_ROOM_SENSOR: ROOM,
            CONF_CONTACTS: [],
            CONF_CONTACTS_INVERTED: False,
            # Tests drive SteadyRoom in control; a new entry from the UI starts observing.
            CONF_OBSERVE_ONLY: False,
        }
        | options,
    )
    entry.add_to_hass(hass)
    if enable_fine_tuning:
        registry = er.async_get(hass)
        for spec in NUMBER_SPECS:
            if spec.advanced:
                registry.async_get_or_create(
                    "number", DOMAIN, f"{entry.entry_id}_{spec.key}", config_entry=entry, suggested_object_id=f"wohnzimmer_{spec.key}"
                )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    """Let time pass and run every timer that became due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def settle(hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls: CallLog) -> None:
    """Run past the start-up re-send and forget what it sent."""
    await tick(hass, freezer, 31)
    calls.clear()


async def call_entity(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a climate service on the SteadyRoom entity, as the card does."""
    await hass.services.async_call("climate", service, {"entity_id": ENTITY, **data}, blocking=True)
    await hass.async_block_till_done()


def number_entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    """Entity id of the number entity for one tuning value."""
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id is not None, key
    return entity_id


def observe_switch_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Entity id of the observation switch."""
    entity_id = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_observe_only")
    assert entity_id is not None
    return entity_id


def attrs(hass: HomeAssistant) -> dict[str, Any]:
    """Attributes of the SteadyRoom entity."""
    state = hass.states.get(ENTITY)
    assert state is not None
    return dict(state.attributes)

