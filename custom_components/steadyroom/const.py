"""Constants of the SteadyRoom integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "steadyroom"

# Number, switch and select before climate: the climate entity reads the restored
# tuning values, the control switch and the near-target preset on its first evaluation.
PLATFORMS: Final = (Platform.NUMBER, Platform.SWITCH, Platform.SELECT, Platform.CLIMATE)

CONF_UNDERLYING: Final = "underlying"
CONF_ROOM_SENSOR: Final = "room_sensor"
CONF_FALLBACK_SENSOR: Final = "fallback_sensor"
CONF_CONTACTS: Final = "contacts"
CONF_CONTACTS_INVERTED: Final = "contacts_inverted"
CONF_SCHEDULE: Final = "schedule"
# Stored in the entry options so it survives a crash; a new entry starts observing.
CONF_OBSERVE_ONLY: Final = "observe_only"
DEFAULT_OBSERVE_ONLY: Final = True

DEFAULT_NAME: Final = "SteadyRoom"
DEFAULT_TARGET: Final = 21.0
DEFAULT_STEP: Final = 0.5
MIN_TARGET: Final = 7.0
MAX_TARGET: Final = 35.0

# Wait this long after the unit returns from unavailable (or after Home
# Assistant started) before re-sending mode and setpoint unconditionally; also
# the pause before a failed command is tried again.
RECONNECT_SETTLE: Final = timedelta(seconds=30)

# Upper bound for one service call to the unit; a cloud unit that hangs must
# not hold the evaluation lock forever.
SERVICE_TIMEOUT_SECONDS: Final = 30

KEY_DOOR_OPEN_DELAY: Final = "door_open_delay"
KEY_DOOR_CLOSE_DELAY: Final = "door_close_delay"
KEY_SENSOR_MAX_AGE: Final = "sensor_max_age"
KEY_PRESET_DISTANCE: Final = "preset_distance"

# Option of the near-target preset select that leaves the unit's preset alone.
PRESET_OFF: Final = "off"
# The preset a unit runs without any special mode (Home Assistant's PRESET_NONE).
PRESET_NONE: Final = "none"


class Reason(StrEnum):
    """Why the unit is in its current state; shown as a diagnostic attribute."""

    NOT_CONFIGURED = "not_configured"
    OFF_MODE = "off_mode"
    IN_BAND = "in_band"
    HEATING = "heating"
    COOLING = "cooling"
    DOOR_OPEN = "door_open"
    OUTSIDE_SCHEDULE = "outside_schedule"
    LOCKED = "locked"
    SENSOR_MISSING = "sensor_missing"
    UNIT_UNAVAILABLE = "unit_unavailable"


class NumberUnit(StrEnum):
    """Unit family of a tuning value; the temperature unit is resolved at runtime."""

    KELVIN = "K"
    NONE = ""
    MINUTES = "min"
    SECONDS = "s"
    TEMPERATURE = "temperature"


@dataclass(frozen=True, kw_only=True)
class NumberSpec:
    """Range and unit of one tuning value. The default lives in ``logic.Parameters``
    for control fields and in ``EXTRA_DEFAULTS`` for the others."""

    key: str
    unit: NumberUnit
    minimum: float
    maximum: float
    step: float
    # Fine tuning: disabled by default, so the device page folds it into "+N disabled entities".
    advanced: bool = False


NUMBER_SPECS: Final[tuple[NumberSpec, ...]] = (
    NumberSpec(key="heat_start", unit=NumberUnit.KELVIN, minimum=0.0, maximum=5.0, step=0.05),
    NumberSpec(key="heat_stop", unit=NumberUnit.KELVIN, minimum=0.0, maximum=5.0, step=0.05),
    NumberSpec(key="cool_start", unit=NumberUnit.KELVIN, minimum=0.0, maximum=5.0, step=0.05),
    NumberSpec(key="cool_stop", unit=NumberUnit.KELVIN, minimum=0.0, maximum=5.0, step=0.05),
    NumberSpec(key="auto_start", unit=NumberUnit.KELVIN, minimum=0.0, maximum=5.0, step=0.05),
    NumberSpec(key="auto_stop", unit=NumberUnit.KELVIN, minimum=0.0, maximum=5.0, step=0.05),
    NumberSpec(key="min_offset", unit=NumberUnit.KELVIN, minimum=0.0, maximum=10.0, step=0.1),
    NumberSpec(key="knee", unit=NumberUnit.KELVIN, minimum=0.0, maximum=10.0, step=0.1, advanced=True),
    NumberSpec(key="factor", unit=NumberUnit.NONE, minimum=0.0, maximum=10.0, step=0.05, advanced=True),
    NumberSpec(key="lock_minutes", unit=NumberUnit.MINUTES, minimum=0.0, maximum=240.0, step=1.0),
    NumberSpec(key="min_setpoint", unit=NumberUnit.TEMPERATURE, minimum=MIN_TARGET, maximum=MAX_TARGET, step=0.5, advanced=True),
    NumberSpec(key="max_setpoint", unit=NumberUnit.TEMPERATURE, minimum=MIN_TARGET, maximum=MAX_TARGET, step=0.5, advanced=True),
    NumberSpec(key=KEY_DOOR_OPEN_DELAY, unit=NumberUnit.SECONDS, minimum=0.0, maximum=3600.0, step=1.0),
    NumberSpec(key=KEY_DOOR_CLOSE_DELAY, unit=NumberUnit.SECONDS, minimum=0.0, maximum=3600.0, step=1.0),
    NumberSpec(key=KEY_SENSOR_MAX_AGE, unit=NumberUnit.MINUTES, minimum=0.0, maximum=1440.0, step=1.0, advanced=True),
    NumberSpec(key=KEY_PRESET_DISTANCE, unit=NumberUnit.KELVIN, minimum=0.0, maximum=5.0, step=0.05),
)

# Tuning values that are not logic parameters; 0 as sensor age means "no limit".
EXTRA_DEFAULTS: Final[dict[str, float]] = {
    KEY_DOOR_OPEN_DELAY: 60.0,
    KEY_DOOR_CLOSE_DELAY: 15.0,
    KEY_SENSOR_MAX_AGE: 0.0,
    KEY_PRESET_DISTANCE: 0.3,
}
