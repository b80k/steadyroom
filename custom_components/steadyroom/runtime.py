"""Shared state of one SteadyRoom entry: the tuning values and who listens to them."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, callback

from .const import EXTRA_DEFAULTS, KEY_DOOR_CLOSE_DELAY, KEY_DOOR_OPEN_DELAY, KEY_SENSOR_MAX_AGE, NUMBER_SPECS
from .logic import DEFAULT_PARAMETERS, Parameters

PARAMETER_KEYS = frozenset(f.name for f in fields(Parameters))

# Every control parameter and every extra tuning value needs a number entity, and every
# number entity needs a default. Fail at import, not at the first evaluation.
_SPEC_KEYS = frozenset(spec.key for spec in NUMBER_SPECS)
if _SPEC_KEYS != PARAMETER_KEYS | EXTRA_DEFAULTS.keys():
    raise RuntimeError(f"NUMBER_SPECS out of sync: {sorted(_SPEC_KEYS ^ (PARAMETER_KEYS | EXTRA_DEFAULTS.keys()))}")


def default_values() -> dict[str, float]:
    """Defaults of every tuning value: today's values from ``logic.Parameters``."""
    return {**asdict(DEFAULT_PARAMETERS), **EXTRA_DEFAULTS}


@dataclass
class SteadyRoomRuntime:
    """Tuning values and observation mode of one entry, written by the number and switch entities, read by the climate entity."""

    values: dict[str, float] = field(default_factory=default_values)
    # Observation mode (ISC-21): decide everything, send nothing to the unit.
    observe_only: bool = False
    _listeners: list[Callable[[], None]] = field(default_factory=list)

    def parameters(self) -> Parameters:
        """Build the logic parameters from the current values."""
        return Parameters(**{key: self.values[key] for key in PARAMETER_KEYS})

    @property
    def door_open_delay(self) -> timedelta:
        """How long a contact must stay open before the unit is switched off."""
        return timedelta(seconds=self.values[KEY_DOOR_OPEN_DELAY])

    @property
    def door_close_delay(self) -> timedelta:
        """How long all contacts must stay closed before the unit may start again."""
        return timedelta(seconds=self.values[KEY_DOOR_CLOSE_DELAY])

    @property
    def sensor_max_age(self) -> timedelta | None:
        """Oldest report a temperature sensor may have; None when the limit is off."""
        minutes = self.values[KEY_SENSOR_MAX_AGE]
        return timedelta(minutes=minutes) if minutes > 0 else None

    @callback
    def async_set_value(self, key: str, value: float) -> None:
        """Store a tuning value and tell every listener."""
        if key not in self.values:
            raise KeyError(f"unknown tuning value {key!r}")
        self.values[key] = value
        self._notify()

    @callback
    def async_set_observe_only(self, observe_only: bool) -> None:
        """Switch observation mode and tell every listener."""
        self.observe_only = observe_only
        self._notify()

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``listener`` after every change; returns the function that removes it."""
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            self._listeners.remove(listener)

        return remove


type SteadyRoomConfigEntry = ConfigEntry[SteadyRoomRuntime]
