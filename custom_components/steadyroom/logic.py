"""Control logic of SteadyRoom, free of Home Assistant imports.

The air conditioner measures the temperature at its own housing, which is
often far from the room's centre. SteadyRoom decides heat, cool or off from a
room sensor and gives the unit a setpoint relative to the unit's *own*
reading, so the unit keeps running steadily instead of short cycling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    """Mode selected by the user."""

    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    AUTO = "auto"


class Direction(StrEnum):
    """What the unit is doing (or should do)."""

    OFF = "off"
    HEAT = "heat"
    COOL = "cool"


@dataclass(frozen=True)
class Parameters:
    """Tunable thresholds; defaults are the values in use since 13.11.2026.

    All temperature values are in kelvin relative to the target.
    """

    heat_start: float = 0.2  # Heat: start below target - heat_start
    heat_stop: float = 0.2  # Heat: stop at target + heat_stop
    cool_start: float = 0.2  # Cool: start above target + cool_start
    cool_stop: float = 0.2  # Cool: stop at target - cool_stop
    auto_start: float = 0.5  # Auto: start at target -/+ auto_start
    auto_stop: float = 0.2  # Auto: stop at target +/- auto_stop
    min_offset: float = 0.5  # smallest offset given to the unit
    knee: float = 0.5  # distance where the offset starts to grow faster
    factor: float = 0.5  # weight of the quadratic part above the knee
    lock_minutes: float = 15.0  # Auto: opposite direction locked after a run
    min_setpoint: float = 16.0  # lowest setpoint sent to the unit
    max_setpoint: float = 30.0  # highest setpoint sent to the unit


DEFAULT_PARAMETERS = Parameters()
EPSILON = 1e-6


def decide(
    mode: Mode,
    room: float,
    target: float,
    running: Direction,
    params: Parameters = DEFAULT_PARAMETERS,
    *,
    locked: Direction = Direction.OFF,
    may_start: bool = True,
) -> Direction:
    """Return the direction the unit should run in.

    ``running`` is what the unit does now. ``locked`` is the direction that
    Auto may not start (the opposite of a run that ended recently).
    ``may_start`` is False while a door or window has not been closed long
    enough; a running unit continues, a stopped one does not start.
    """

    def start(direction: Direction) -> Direction:
        if running is not Direction.OFF or may_start:
            return direction
        return Direction.OFF

    if mode is Mode.OFF:
        return Direction.OFF

    # Every threshold is a switching point: the unit switches once the room is AT it,
    # on both sides of the target, so start and stop are symmetric. EPSILON absorbs
    # float noise in "target - 0.2" and the like. Stop comes first, so a band of
    # zero width stops at the target instead of starting there.
    if mode is Mode.HEAT:
        if _at_or_above(room, target + params.heat_stop):
            return Direction.OFF
        if _at_or_below(room, target - params.heat_start):
            return start(Direction.HEAT)
        return running if running is Direction.HEAT else Direction.OFF

    if mode is Mode.COOL:
        if _at_or_below(room, target - params.cool_stop):
            return Direction.OFF
        if _at_or_above(room, target + params.cool_start):
            return start(Direction.COOL)
        return running if running is Direction.COOL else Direction.OFF

    # Auto: a running unit only ever stops; the other direction starts from off.
    if running is Direction.HEAT:
        return Direction.OFF if _at_or_above(room, target + params.auto_stop) else Direction.HEAT
    if running is Direction.COOL:
        return Direction.OFF if _at_or_below(room, target - params.auto_stop) else Direction.COOL
    if _at_or_below(room, target - params.auto_start) and locked is not Direction.HEAT:
        return start(Direction.HEAT)
    if _at_or_above(room, target + params.auto_start) and locked is not Direction.COOL:
        return start(Direction.COOL)
    return Direction.OFF


def _at_or_below(value: float, limit: float) -> bool:
    return value <= limit + EPSILON


def _at_or_above(value: float, limit: float) -> bool:
    return value >= limit - EPSILON


def offset(distance: float, step: float, params: Parameters = DEFAULT_PARAMETERS) -> float:
    """Offset in kelvin for a distance to the target (positive = behind it).

    Up to the knee the offset is the minimum; above it the effective distance
    grows quadratically. The result is a whole number of steps and never less
    than ``min_offset``. There is deliberately no upper limit here; only the
    final setpoint is clamped.
    """
    if distance <= params.knee:
        grown = distance
    else:
        grown = distance + params.factor * (distance - params.knee) ** 2
    steps = math.ceil(grown / step - EPSILON)
    return max(params.min_offset, steps * step)


def round_to_step(value: float, step: float) -> float:
    """Round half up to the unit's step, like Jinja's ``round(0, 'common')``."""
    return round(math.floor(value / step + 0.5) * step, 2)


def setpoint(
    direction: Direction,
    room: float,
    target: float,
    unit_temperature: float,
    step: float,
    params: Parameters = DEFAULT_PARAMETERS,
) -> float | None:
    """Setpoint for the unit, or None when it should be off."""
    if direction is Direction.HEAT:
        bias = offset(target - room, step, params)
    elif direction is Direction.COOL:
        bias = -offset(room - target, step, params)
    else:
        return None
    value = round_to_step(unit_temperature + bias, step)
    return min(params.max_setpoint, max(params.min_setpoint, value))


def should_send(current: float | None, desired: float, step: float) -> bool:
    """Send a new setpoint only when it differs by at least half a step."""
    if current is None:
        return True
    return abs(current - desired) >= step / 2 - 0.01


def locked_direction(
    last_direction: Direction, minutes_since_end: float | None, params: Parameters = DEFAULT_PARAMETERS
) -> Direction:
    """Direction Auto may not start after a run that ended recently."""
    if minutes_since_end is None or minutes_since_end >= params.lock_minutes:
        return Direction.OFF
    if last_direction is Direction.HEAT:
        return Direction.COOL
    if last_direction is Direction.COOL:
        return Direction.HEAT
    return Direction.OFF
