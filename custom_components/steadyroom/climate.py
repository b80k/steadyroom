"""SteadyRoom climate entity: decides from the room sensor, steers the underlying unit."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import logging
import math
from typing import Any, Self

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_SWING_HORIZONTAL_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    PRECISION_TENTHS,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Context, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity_registry import EventEntityRegistryUpdatedData
from homeassistant.helpers.event import (
    async_call_later,
    async_track_entity_registry_updated_event,
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from . import logic
from .const import (
    CONF_CONTACTS,
    CONF_CONTACTS_INVERTED,
    CONF_FALLBACK_SENSOR,
    CONF_ROOM_SENSOR,
    CONF_SCHEDULE,
    CONF_UNDERLYING,
    DEFAULT_STEP,
    DEFAULT_TARGET,
    MAX_TARGET,
    MIN_TARGET,
    RECONNECT_SETTLE,
    SERVICE_TIMEOUT_SECONDS,
    Reason,
)
from .entity import device_info
from .logic import Direction, Mode
from .runtime import SteadyRoomConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

HVAC_TO_MODE: dict[HVACMode, Mode] = {
    HVACMode.OFF: Mode.OFF,
    HVACMode.HEAT: Mode.HEAT,
    HVACMode.COOL: Mode.COOL,
    HVACMode.HEAT_COOL: Mode.AUTO,
}
RUNNING = (Direction.HEAT, Direction.COOL)
_UNIT_ACTION_BY_STATE: dict[str, HVACAction] = {
    HVACMode.HEAT: HVACAction.HEATING,
    HVACMode.COOL: HVACAction.COOLING,
    HVACMode.DRY: HVACAction.DRYING,
    HVACMode.FAN_ONLY: HVACAction.FAN,
}
# Before the first contact event every contact counts as closed since long ago.
_LONG_AGO = dt_util.utc_from_timestamp(0)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SteadyRoomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the one climate entity of this entry."""
    async_add_entities([SteadyRoomClimate(entry, hass.config.units.temperature_unit)])


def _number(value: Any) -> float | None:
    """A finite float, or None for anything else (missing, text, nan)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _available(state: State | None) -> bool:
    return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


def _unit_direction(state: State | None) -> Direction | None:
    """What the unit does: heat, cool, off; None while it is unavailable."""
    if not _available(state):
        return None
    assert state is not None
    if state.state == HVACMode.HEAT:
        return Direction.HEAT
    if state.state == HVACMode.COOL:
        return Direction.COOL
    return Direction.OFF


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None or parsed.tzinfo is None:
        return None
    return dt_util.as_utc(parsed)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _reported(state: State) -> datetime:
    """When the sensor last reported, even an unchanged value."""
    return getattr(state, "last_reported", None) or state.last_updated


def _renamed(options: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    """Entry options with one entity id replaced wherever it is used."""
    renamed: dict[str, Any] = {}
    for key, value in options.items():
        if isinstance(value, list):
            renamed[key] = [new if item == old else item for item in value]
        else:
            renamed[key] = new if value == old else value
    return renamed


# Unit features SteadyRoom mirrors 1:1: the user's own choices, never SteadyRoom's decisions.
_PASSTHROUGH_FEATURES = (
    ClimateEntityFeature.FAN_MODE,
    ClimateEntityFeature.SWING_MODE,
    ClimateEntityFeature.SWING_HORIZONTAL_MODE,
    ClimateEntityFeature.PRESET_MODE,
)


@dataclass
class StoredState(ExtraStoredData):
    """What survives a restart: mode, target, last run and the direction a door interrupted."""

    hvac_mode: str
    target: float
    last_direction: str
    run_ended_at: str | None
    door_resume: str | None
    # False until the user chose a mode; until then nothing is sent to the unit.
    mode_set: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise for the restore cache."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self | None:
        """Parse the restore cache; None when anything does not fit."""
        try:
            mode = HVACMode(data["hvac_mode"])
            target = _number(data["target"])
            last_direction = Direction(data["last_direction"])
            door_resume = data["door_resume"]
            if door_resume is not None:
                door_resume = Direction(door_resume)
        except (KeyError, ValueError):
            return None
        if mode not in HVAC_TO_MODE or target is None:
            return None
        return cls(
            hvac_mode=mode.value,
            target=min(MAX_TARGET, max(MIN_TARGET, target)),
            last_direction=last_direction.value,
            run_ended_at=_iso(_parse_time(data.get("run_ended_at"))),
            door_resume=door_resume.value if door_resume is not None else None,
            # Data without the flag is taken as chosen unless it says off, the old default.
            mode_set=bool(data.get("mode_set", mode is not HVACMode.OFF)),
        )


@dataclass
class Diagnostics:
    """Values of the last evaluation, shown as state attributes."""

    distance: float | None = None
    offset: float | None = None
    sent_setpoint: float | None = None
    # What SteadyRoom wants the unit at; in observation mode the only trace of the decision.
    would_hvac_mode: str | None = None
    would_setpoint: float | None = None
    locked_direction: Direction = Direction.OFF
    lock_until: datetime | None = None
    reason: Reason | None = None


class SteadyRoomClimate(ClimateEntity, RestoreEntity):
    """One room thermostat on top of an air conditioner."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "steadyroom"
    _attr_should_poll = False
    _attr_hvac_modes = list(HVAC_TO_MODE)
    _attr_min_temp = MIN_TARGET
    _attr_max_temp = MAX_TARGET
    _attr_precision = PRECISION_TENTHS

    def __init__(self, entry: SteadyRoomConfigEntry, temperature_unit: str) -> None:
        options = entry.options
        self._entry = entry
        self._runtime = entry.runtime_data
        self._underlying: str = options[CONF_UNDERLYING]
        self._sensors: tuple[str, ...] = tuple(
            entity_id for entity_id in (options[CONF_ROOM_SENSOR], options.get(CONF_FALLBACK_SENSOR)) if entity_id
        )
        self._contacts: tuple[str, ...] = tuple(options.get(CONF_CONTACTS) or ())
        self._contacts_inverted = bool(options.get(CONF_CONTACTS_INVERTED, False))
        self._schedule: str | None = options.get(CONF_SCHEDULE)

        self._attr_unique_id = entry.entry_id
        self._attr_device_info = device_info(entry)
        self._attr_temperature_unit = temperature_unit
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = DEFAULT_TARGET

        # Last run of the unit; drives the Auto lock.
        self._last_direction = Direction.OFF
        self._run_ended_at: datetime | None = None
        self._seen_direction: Direction | None = None
        # Direction a door switched off; resumed once all contacts are closed long enough.
        self._door_resume: Direction | None = None
        self._open_since: datetime | None = None
        self._closed_since: datetime | None = _LONG_AGO

        self._diagnostics = Diagnostics()
        self._lock = asyncio.Lock()
        self._evaluation_queued = False
        self._force_pending = False
        self._removed = False
        self._observing = False
        self._mode_set = False
        # Commands go out only after Home Assistant has started ...
        self._started = False
        # ... and not while a returning unit settles.
        self._settle_until: datetime | None = None
        # The unit's entity was removed or renamed: never command that id again.
        self._unit_gone = False
        # Last definite answer of the schedule; inside until it says otherwise.
        self._schedule_inside = True
        self._reconnect_unsub: CALLBACK_TYPE | None = None
        self._retry_unsub: CALLBACK_TYPE | None = None
        self._wakeup_unsub: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------------ lifecycle

    async def async_added_to_hass(self) -> None:
        """Restore, start listening, evaluate once Home Assistant has started."""
        await super().async_added_to_hass()
        await self._async_restore()
        self._observe_unit(self.hass.states.get(self._underlying), may_end_run=True)
        self._init_contacts()
        self._refresh_schedule()

        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._underlying], self._async_underlying_changed)
        )
        inputs = [*self._sensors, *([self._schedule] if self._schedule else [])]
        self.async_on_remove(async_track_state_change_event(self.hass, inputs, self._async_input_changed))
        if self._contacts:
            self.async_on_remove(
                async_track_state_change_event(self.hass, list(self._contacts), self._async_contact_changed)
            )
        tracked = [self._underlying, *self._sensors, *self._contacts, *([self._schedule] if self._schedule else [])]
        self.async_on_remove(
            async_track_entity_registry_updated_event(self.hass, tracked, self._async_registry_updated)
        )
        self._observing = self._runtime.observe_only
        self.async_on_remove(self._runtime.async_add_listener(self._async_runtime_changed))
        self.async_on_remove(self._cancel_timers)
        self.async_on_remove(async_at_started(self.hass, self._async_started))

    async def async_will_remove_from_hass(self) -> None:
        """Stop queued evaluations from touching a removed entity."""
        self._removed = True
        await super().async_will_remove_from_hass()

    async def _async_restore(self) -> None:
        extra = await self.async_get_last_extra_data()
        stored = StoredState.from_dict(extra.as_dict()) if extra is not None else None
        if stored is None:
            return
        self._attr_hvac_mode = HVACMode(stored.hvac_mode)
        self._attr_target_temperature = stored.target
        self._last_direction = Direction(stored.last_direction)
        self._run_ended_at = _parse_time(stored.run_ended_at)
        self._door_resume = Direction(stored.door_resume) if stored.door_resume else None
        self._mode_set = stored.mode_set
        # A run that had not ended before the restart is assumed to be still on;
        # if the unit now reports off, that is the end of the run.
        if self._run_ended_at is None and self._last_direction in RUNNING:
            self._seen_direction = self._last_direction

    @property
    def extra_restore_state_data(self) -> StoredState:
        """State that has to survive a restart."""
        return StoredState(
            hvac_mode=self.hvac_mode.value if self.hvac_mode else HVACMode.OFF.value,
            target=self.target_temperature if self.target_temperature is not None else DEFAULT_TARGET,
            last_direction=self._last_direction.value,
            run_ended_at=_iso(self._run_ended_at),
            door_resume=self._door_resume.value if self._door_resume else None,
            mode_set=self._mode_set,
        )

    @callback
    def _async_started(self, _hass: HomeAssistant) -> None:
        self._started = True
        self._request_evaluation()
        self._schedule_forced_evaluation()

    @callback
    def _cancel_timers(self) -> None:
        for unsub in (self._reconnect_unsub, self._retry_unsub, self._wakeup_unsub):
            if unsub is not None:
                unsub()
        self._reconnect_unsub = None
        self._retry_unsub = None
        self._wakeup_unsub = None

    # ------------------------------------------------------------------ inputs

    @callback
    def _observe_unit(self, state: State | None, *, may_end_run: bool) -> None:
        """Track the unit's runs: when a heat or cool run ends, the Auto lock starts.

        A step out of unavailable never ends a run: what the unit did meanwhile is unknown.
        """
        direction = _unit_direction(state)
        if direction is None:
            return
        previous = self._seen_direction
        self._seen_direction = direction
        if direction in RUNNING:
            self._last_direction = direction
            self._run_ended_at = None
        elif previous in RUNNING and may_end_run:
            assert previous is not None
            self._last_direction = previous
            self._run_ended_at = dt_util.utcnow()

    def _contact_open(self, state: State | None) -> bool:
        """Open per the inversion flag; unavailable or unknown contacts count as closed."""
        if state is None:
            return False
        return state.state == (STATE_OFF if self._contacts_inverted else STATE_ON)

    @callback
    def _init_contacts(self) -> None:
        """Contacts open at start count from their last change; closed ones count as closed long ago.

        After a restart every state carries the restart time as its last change,
        so a closed contact gives no evidence of a recent opening.
        """
        open_states = [
            state
            for entity_id in self._contacts
            if (state := self.hass.states.get(entity_id)) is not None and self._contact_open(state)
        ]
        if open_states:
            self._open_since = min(state.last_changed for state in open_states)
            self._closed_since = None
        else:
            self._open_since = None
            self._closed_since = _LONG_AGO

    @callback
    def _async_underlying_changed(self, event: Event[EventStateChangedData]) -> None:
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        if not _available(new_state):
            self._seen_direction = None
            self._settle_until = None
            if self._reconnect_unsub is not None:
                self._reconnect_unsub()
                self._reconnect_unsub = None
        elif not _available(old_state):
            # Back from unavailable: note what it does, send nothing until it has settled.
            self._observe_unit(new_state, may_end_run=False)
            self._settle_until = dt_util.utcnow() + RECONNECT_SETTLE
            self._schedule_forced_evaluation()
        else:
            self._observe_unit(new_state, may_end_run=True)
        self._request_evaluation()

    @callback
    def _async_registry_updated(self, event: Event[EventEntityRegistryUpdatedData]) -> None:
        """Follow renames of the chosen entities; a removed or renamed unit is never commanded."""
        data = event.data
        if data["action"] == "remove":
            if data["entity_id"] == self._underlying:
                self._unit_gone = True
            self._request_evaluation()
            return
        if data["action"] != "update" or "old_entity_id" not in data:
            return
        old, new = data["old_entity_id"], data["entity_id"]
        if old == new:
            return
        if old == self._underlying:
            # Until the reload points at the new id, the old one may already belong to someone else.
            self._unit_gone = True
        self.hass.config_entries.async_update_entry(self._entry, options=_renamed(dict(self._entry.options), old, new))
        self.hass.config_entries.async_schedule_reload(self._entry.entry_id)
        self._request_evaluation()

    @callback
    def _async_runtime_changed(self) -> None:
        """A tuning value or the observation mode changed; leaving observation re-sends everything."""
        leaving_observation = self._observing and not self._runtime.observe_only
        self._observing = self._runtime.observe_only
        self._request_evaluation(force=leaving_observation)

    @callback
    def _async_input_changed(self, _event: Event[EventStateChangedData]) -> None:
        self._refresh_schedule()
        self._request_evaluation()

    @callback
    def _refresh_schedule(self) -> None:
        """Take the schedule's answer when it gives one; unavailable or missing keeps the last answer."""
        if self._schedule is None:
            return
        state = self.hass.states.get(self._schedule)
        if state is not None and state.state in (STATE_ON, STATE_OFF):
            self._schedule_inside = state.state == STATE_ON

    @callback
    def _async_contact_changed(self, _event: Event[EventStateChangedData]) -> None:
        now = dt_util.utcnow()
        any_open = any(self._contact_open(self.hass.states.get(entity_id)) for entity_id in self._contacts)
        if any_open and self._open_since is None:
            self._open_since = now
            self._closed_since = None
        elif not any_open and self._closed_since is None:
            self._closed_since = now
            self._open_since = None
        self._request_evaluation()

    # ------------------------------------------------------------------ timers

    @callback
    def _schedule_forced_evaluation(self) -> None:
        """Re-send mode and setpoint after the settle time, even if they look equal."""
        if self._reconnect_unsub is not None:
            self._reconnect_unsub()
        self._reconnect_unsub = async_call_later(self.hass, RECONNECT_SETTLE, self._async_forced_evaluation)

    @callback
    def _async_forced_evaluation(self, _now: datetime) -> None:
        self._reconnect_unsub = None
        self._settle_until = None
        self._request_evaluation(force=True)

    @callback
    def _schedule_retry(self) -> None:
        """A command failed: decide and send again after the settle time."""
        if self._retry_unsub is not None:
            self._retry_unsub()
        self._retry_unsub = async_call_later(self.hass, RECONNECT_SETTLE, self._async_retry)

    @callback
    def _async_retry(self, _now: datetime) -> None:
        self._retry_unsub = None
        self._request_evaluation()

    @callback
    def _schedule_wakeup(self, now: datetime) -> None:
        """One timer for the next moment the decision can change without an outside event."""
        if self._wakeup_unsub is not None:
            self._wakeup_unsub()
            self._wakeup_unsub = None
        candidates = [self._diagnostics.lock_until]
        if self._open_since is not None:
            candidates.append(self._open_since + self._runtime.door_open_delay)
        if self._closed_since is not None:
            candidates.append(self._closed_since + self._runtime.door_close_delay)
        if (max_age := self._runtime.sensor_max_age) is not None:
            for entity_id in self._sensors:
                if (state := self.hass.states.get(entity_id)) is not None:
                    candidates.append(_reported(state) + max_age)
        future = [moment for moment in candidates if moment is not None and moment > now]
        if future:
            self._wakeup_unsub = async_track_point_in_utc_time(self.hass, self._async_wakeup, min(future))

    @callback
    def _async_wakeup(self, _now: datetime) -> None:
        self._wakeup_unsub = None
        self._request_evaluation()

    # ------------------------------------------------------------------ evaluation

    @callback
    def _request_evaluation(self, force: bool = False) -> None:
        """Queue one evaluation; requests arriving before it starts are merged into it."""
        self._force_pending |= force
        if self._evaluation_queued or self._removed:
            return
        self._evaluation_queued = True
        self._entry.async_create_task(self.hass, self._async_run_evaluation(), "steadyroom evaluation", eager_start=False)

    async def _async_run_evaluation(self) -> None:
        async with self._lock:
            self._evaluation_queued = False
            if self._removed:
                return
            force = self._force_pending
            self._force_pending = False
            now = dt_util.utcnow()
            reached = False
            try:
                reached = await self._async_evaluate(now, force)
            except Exception:
                # A bug must not end the control loop: the next trigger evaluates again.
                _LOGGER.exception("%s: evaluation failed", self.entity_id)
            finally:
                # A forced re-send that could not happen (or crashed) stays due for the next evaluation.
                if force and not reached:
                    self._force_pending = True
                self._schedule_wakeup(now)
                self.async_write_ha_state()

    def _room_temperature(self, now: datetime | None = None) -> float | None:
        """Room sensor, else fallback; a reading older than the maximum sensor age counts as missing."""
        now = now or dt_util.utcnow()
        max_age = self._runtime.sensor_max_age
        for entity_id in self._sensors:
            state = self.hass.states.get(entity_id)
            if state is None or not _available(state) or (value := _number(state.state)) is None:
                continue
            if max_age is not None and now - _reported(state) >= max_age:
                continue
            return value
        return None

    @staticmethod
    def _step(unit: State | None) -> float:
        step = _number(unit.attributes.get(ATTR_TARGET_TEMP_STEP)) if unit is not None else None
        return step if step is not None and step > 0 else DEFAULT_STEP

    def _update_lock(self, now: datetime, params: logic.Parameters) -> Direction:
        minutes = None if self._run_ended_at is None else (now - self._run_ended_at) / timedelta(minutes=1)
        locked = logic.locked_direction(self._last_direction, minutes, params)
        self._diagnostics.locked_direction = locked
        self._diagnostics.lock_until = (
            self._run_ended_at + timedelta(minutes=params.lock_minutes)
            if locked is not Direction.OFF and self._run_ended_at is not None
            else None
        )
        return locked

    async def _async_evaluate(self, now: datetime, force: bool) -> bool:
        """Decide and command the unit. Returns False when nothing could be sent."""
        diagnostics = self._diagnostics
        params = self._runtime.parameters()
        locked = self._update_lock(now, params)

        target = float(self.target_temperature if self.target_temperature is not None else DEFAULT_TARGET)
        room = self._room_temperature(now)
        diagnostics.distance = round(target - room, 2) if room is not None else None
        if not self._mode_set:
            # A new device must not touch a unit something else may be running.
            self._undecided(Reason.NOT_CONFIGURED)
            return False
        unit = self.hass.states.get(self._underlying)
        if self._unit_gone or not _available(unit):
            self._undecided(Reason.UNIT_UNAVAILABLE)
            return False
        assert unit is not None

        mode = HVAC_TO_MODE[HVACMode(self.hvac_mode or HVACMode.OFF)]
        step = self._step(unit)

        running = _unit_direction(unit) or Direction.OFF
        door_open_long = self._open_since is not None and now - self._open_since >= self._runtime.door_open_delay
        closed_long = self._closed_since is not None and now - self._closed_since >= self._runtime.door_close_delay
        resuming = closed_long and self._door_resume is not None
        if resuming:
            assert self._door_resume is not None
            running = self._door_resume

        if mode is Mode.OFF:
            desired, reason = Direction.OFF, Reason.OFF_MODE
        elif self._schedule is not None and not self._schedule_inside:
            desired, reason = Direction.OFF, Reason.OUTSIDE_SCHEDULE
        elif door_open_long:
            if running in RUNNING and self._door_resume is None:
                self._door_resume = running
            desired, reason = Direction.OFF, Reason.DOOR_OPEN
        elif room is None:
            # Only the band decision needs the room; the off decisions above never wait for it.
            self._undecided(Reason.SENSOR_MISSING)
            return False
        else:
            desired = logic.decide(mode, room, target, running, params, locked=locked, may_start=closed_long)
            reason = self._reason(desired, mode, room, target, running, params, closed_long)

        unit_temperature = _number(unit.attributes.get(ATTR_CURRENT_TEMPERATURE))
        if desired in RUNNING and unit_temperature is None:
            # Without the unit's own reading there is no setpoint to give it; off needs none.
            self._undecided(Reason.UNIT_UNAVAILABLE)
            return False

        diagnostics.reason = reason
        done = await self._async_command(now, unit, desired, room, target, unit_temperature, step, params, force)
        if done and resuming:
            self._door_resume = None
        return done

    def _undecided(self, reason: Reason) -> None:
        """No decision could be made: say why, and that nothing is wanted from the unit."""
        diagnostics = self._diagnostics
        diagnostics.reason = reason
        diagnostics.offset = None
        diagnostics.would_hvac_mode = None
        diagnostics.would_setpoint = None

    @staticmethod
    def _reason(
        desired: Direction,
        mode: Mode,
        room: float,
        target: float,
        running: Direction,
        params: logic.Parameters,
        may_start: bool,
    ) -> Reason:
        """Why the decision came out as it did; asks the logic what it would do without lock or door."""
        if desired is Direction.HEAT:
            return Reason.HEATING
        if desired is Direction.COOL:
            return Reason.COOLING
        if logic.decide(mode, room, target, running, params) is Direction.OFF:
            return Reason.IN_BAND
        # Something holds back a start the band asks for: the lock if the door
        # alone would allow it, else the door (possibly together with the lock).
        if logic.decide(mode, room, target, running, params, may_start=may_start) is not Direction.OFF:
            return Reason.LOCKED
        return Reason.DOOR_OPEN

    async def _async_command(
        self,
        now: datetime,
        unit: State,
        desired: Direction,
        room: float | None,
        target: float,
        unit_temperature: float | None,
        step: float,
        params: logic.Parameters,
        force: bool,
    ) -> bool:
        """Bring the unit to the decision; only ever addresses the underlying entity.

        In observation mode the decision only lands in the would_* attributes.
        Before Home Assistant has started and while a returning unit settles,
        nothing is sent and False tells the caller the decision is still due.
        A failed command schedules a retry.
        """
        diagnostics = self._diagnostics
        observing = self._runtime.observe_only
        if desired is Direction.OFF:
            diagnostics.offset = None
            diagnostics.would_hvac_mode = HVACMode.OFF.value
            diagnostics.would_setpoint = None
            if observing:
                return True
            if not self._may_send(now):
                return False
            if force or unit.state != HVACMode.OFF:
                if not await self._async_call(SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.OFF}, Context()):
                    self._schedule_retry()
                    return False
            diagnostics.sent_setpoint = None
            return True

        assert room is not None and unit_temperature is not None
        setpoint = logic.setpoint(desired, room, target, unit_temperature, step, params)
        assert setpoint is not None
        distance = target - room if desired is Direction.HEAT else room - target
        bias = logic.offset(distance, step, params)
        diagnostics.offset = bias if desired is Direction.HEAT else -bias
        hvac_mode = HVACMode(desired.value)
        diagnostics.would_hvac_mode = hvac_mode.value
        diagnostics.would_setpoint = setpoint
        if observing:
            return True
        if not self._may_send(now):
            return False

        # A fresh context per evaluation: these commands are SteadyRoom's, not the last user's.
        context = Context()
        ok = True
        if force or unit.state != hvac_mode:
            ok = await self._async_call(SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: hvac_mode}, context)
        current = _number(unit.attributes.get(ATTR_TEMPERATURE))
        if force or logic.should_send(current, setpoint, step):
            if await self._async_call(SERVICE_SET_TEMPERATURE, {ATTR_TEMPERATURE: setpoint}, context):
                diagnostics.sent_setpoint = setpoint
            else:
                ok = False
        if not ok:
            self._schedule_retry()
        return ok

    def _may_send(self, now: datetime) -> bool:
        """Commands wait for the start of Home Assistant and for a returning unit to settle."""
        return self._started and (self._settle_until is None or now >= self._settle_until)

    async def _async_call(self, service: str, data: dict[str, Any], context: Context) -> bool:
        """Call a climate service on the underlying unit; any failure is logged and reported as False."""
        try:
            await self._async_call_unit(service, data, context)
        except Exception as err:  # noqa: BLE001 - a foreign integration's failure must not stop the control loop
            _LOGGER.warning("%s: %s on %s failed: %r", self.entity_id, service, self._underlying, err)
            return False
        return True

    async def _async_call_unit(self, service: str, data: dict[str, Any], context: Context | None) -> None:
        if self._unit_gone:
            raise HomeAssistantError(f"{self._underlying} was removed or renamed; reconfigure SteadyRoom")
        async with asyncio.timeout(SERVICE_TIMEOUT_SECONDS):
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                service,
                {ATTR_ENTITY_ID: self._underlying, **data},
                blocking=True,
                context=context,
            )

    # ------------------------------------------------------------------ user actions

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Change the mode; the running direction is kept, the logic decides from there."""
        self._attr_hvac_mode = HVACMode(hvac_mode)
        self._mode_set = True
        self.async_write_ha_state()
        self._request_evaluation()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Change the target (and optionally the mode)."""
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            self._attr_hvac_mode = HVACMode(hvac_mode)
            self._mode_set = True
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = float(temperature)
        self.async_write_ha_state()
        self._request_evaluation()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Pass the fan mode through to the unit.

        Also in observation mode: it is an explicit user action, not a decision of SteadyRoom.
        """
        await self._async_call_unit(SERVICE_SET_FAN_MODE, {ATTR_FAN_MODE: fan_mode}, self._context)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Pass the swing mode through to the unit (also in observation mode, like the fan mode)."""
        await self._async_call_unit(SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: swing_mode}, self._context)

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """Pass the horizontal swing mode through to the unit (also in observation mode)."""
        await self._async_call_unit(
            SERVICE_SET_SWING_HORIZONTAL_MODE, {ATTR_SWING_HORIZONTAL_MODE: swing_horizontal_mode}, self._context
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Pass the unit's own preset through, such as quiet or powerful (also in observation mode)."""
        await self._async_call_unit(SERVICE_SET_PRESET_MODE, {ATTR_PRESET_MODE: preset_mode}, self._context)

    # ------------------------------------------------------------------ state

    def _unit_state(self) -> State | None:
        return self.hass.states.get(self._underlying)

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Target, on/off; fan, swing and presets only when the unit has them."""
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        )
        unit = self._unit_state()
        unit_features = int(_number(unit.attributes.get(ATTR_SUPPORTED_FEATURES)) or 0) if unit is not None else 0
        for feature in _PASSTHROUGH_FEATURES:
            if unit_features & feature:
                features |= feature
        return features

    @property
    def current_temperature(self) -> float | None:
        """Room sensor, else fallback sensor."""
        return self._room_temperature()

    @property
    def target_temperature_step(self) -> float:
        """The unit's step, so the card offers what the unit can do."""
        return self._step(self._unit_state())

    @property
    def hvac_action(self) -> HVACAction | None:
        """Off in mode off, idle while the unit rests, else what the unit reports."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        unit = self._unit_state()
        if not _available(unit):
            return None
        assert unit is not None
        if unit.state == HVACMode.OFF:
            return HVACAction.IDLE
        try:
            return HVACAction(unit.attributes.get(ATTR_HVAC_ACTION))
        except ValueError:
            return _UNIT_ACTION_BY_STATE.get(unit.state, HVACAction.IDLE)

    @property
    def fan_mode(self) -> str | None:
        """Fan mode of the unit."""
        unit = self._unit_state()
        return unit.attributes.get(ATTR_FAN_MODE) if unit is not None else None

    @property
    def fan_modes(self) -> list[str] | None:
        """Fan modes the unit offers."""
        unit = self._unit_state()
        return unit.attributes.get(ATTR_FAN_MODES) if unit is not None else None

    @property
    def swing_mode(self) -> str | None:
        """Swing mode of the unit."""
        unit = self._unit_state()
        return unit.attributes.get(ATTR_SWING_MODE) if unit is not None else None

    @property
    def swing_modes(self) -> list[str] | None:
        """Swing modes the unit offers."""
        unit = self._unit_state()
        return unit.attributes.get(ATTR_SWING_MODES) if unit is not None else None

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Horizontal swing mode of the unit."""
        unit = self._unit_state()
        return unit.attributes.get(ATTR_SWING_HORIZONTAL_MODE) if unit is not None else None

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        """Horizontal swing modes the unit offers."""
        unit = self._unit_state()
        return unit.attributes.get(ATTR_SWING_HORIZONTAL_MODES) if unit is not None else None

    @property
    def preset_mode(self) -> str | None:
        """Preset of the unit."""
        unit = self._unit_state()
        return unit.attributes.get(ATTR_PRESET_MODE) if unit is not None else None

    @property
    def preset_modes(self) -> list[str] | None:
        """Presets the unit offers."""
        unit = self._unit_state()
        return unit.attributes.get(ATTR_PRESET_MODES) if unit is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Why the unit runs or rests, and the numbers behind it."""
        diagnostics = self._diagnostics
        return {
            "distance": diagnostics.distance,
            "offset": diagnostics.offset,
            "sent_setpoint": diagnostics.sent_setpoint,
            "would_hvac_mode": diagnostics.would_hvac_mode,
            "would_setpoint": diagnostics.would_setpoint,
            "observe_only": self._runtime.observe_only,
            "last_direction": self._last_direction.value,
            "run_ended_at": _iso(self._run_ended_at),
            "locked_direction": diagnostics.locked_direction.value,
            "lock_until": _iso(diagnostics.lock_until),
            "reason": diagnostics.reason.value if diagnostics.reason is not None else None,
        }
