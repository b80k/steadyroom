"""Table tests for the control logic.

The values mirror scenarios rendered against the Home Assistant automations
this integration replaces (13.11.2026).
"""

import importlib.util
import pathlib
import sys

import pytest

# Load logic.py directly so the test needs no Home Assistant import.
_PATH = pathlib.Path(__file__).parents[1] / "custom_components" / "steadyroom" / "logic.py"
_spec = importlib.util.spec_from_file_location("steadyroom_logic", _PATH)
logic = importlib.util.module_from_spec(_spec)
sys.modules["steadyroom_logic"] = logic
_spec.loader.exec_module(logic)

D = logic.Direction
M = logic.Mode
TARGET = 21.0


@pytest.mark.parametrize(
    ("mode", "running", "room", "expected"),
    [
        (M.HEAT, D.OFF, 20.8, D.HEAT),  # at the start point
        (M.HEAT, D.OFF, 20.81, D.OFF),
        (M.HEAT, D.HEAT, 21.19, D.HEAT),
        (M.HEAT, D.HEAT, 21.2, D.OFF),
        (M.HEAT, D.OFF, 21.0, D.OFF),
        (M.HEAT, D.COOL, 21.0, D.OFF),
        (M.COOL, D.OFF, 21.2, D.COOL),  # at the start point
        (M.COOL, D.OFF, 21.19, D.OFF),
        (M.COOL, D.COOL, 20.81, D.COOL),
        (M.COOL, D.COOL, 20.8, D.OFF),
        (M.COOL, D.HEAT, 21.0, D.OFF),
        (M.OFF, D.HEAT, 18.0, D.OFF),
    ],
)
def test_band(mode, running, room, expected):
    assert logic.decide(mode, room, TARGET, running) is expected


@pytest.mark.parametrize(
    ("running", "room", "locked", "expected"),
    [
        (D.OFF, 20.6, D.OFF, D.OFF),  # 0.4 K too cold: not yet at the start point
        (D.OFF, 20.5, D.OFF, D.HEAT),
        (D.OFF, 21.4, D.OFF, D.OFF),
        (D.OFF, 21.5, D.OFF, D.COOL),
        (D.HEAT, 21.1, D.OFF, D.HEAT),
        (D.HEAT, 21.19, D.OFF, D.HEAT),
        (D.HEAT, 21.2, D.OFF, D.OFF),
        (D.COOL, 20.85, D.OFF, D.COOL),
        (D.COOL, 20.81, D.OFF, D.COOL),
        (D.COOL, 20.8, D.OFF, D.OFF),
    ],
)
def test_auto(running, room, locked, expected):
    assert logic.decide(M.AUTO, room, TARGET, running, locked=locked) is expected


@pytest.mark.parametrize("band", [0.1, 0.2, 0.3, 0.5])
@pytest.mark.parametrize("target", [16.1, 16.2, 19.5, 20.0, 20.3, 20.5, 21.0, 22.3, 23.7])
def test_band_is_symmetric_for_sensor_steps(target, band):
    """With a sensor in 0.1 K steps, a band of 0.2 K heats from target - 0.2 to target + 0.2.

    The values are built the way they arrive (rounded sensor readings), so float noise in
    "target - band" (16.2 - 0.1 = 16.099999999999998) must not shift a switching point by
    one sensor step.
    """
    params = logic.Parameters(heat_start=band, heat_stop=band, cool_start=band, cool_stop=band)
    below, above = round(target - band, 1), round(target + band, 1)
    assert logic.decide(M.HEAT, below, target, D.OFF, params) is D.HEAT
    assert logic.decide(M.HEAT, round(below + 0.1, 1), target, D.OFF, params) is D.OFF
    assert logic.decide(M.HEAT, round(above - 0.1, 1), target, D.HEAT, params) is D.HEAT
    assert logic.decide(M.HEAT, above, target, D.HEAT, params) is D.OFF
    assert logic.decide(M.COOL, above, target, D.OFF, params) is D.COOL
    assert logic.decide(M.COOL, round(above - 0.1, 1), target, D.OFF, params) is D.OFF
    assert logic.decide(M.COOL, round(below + 0.1, 1), target, D.COOL, params) is D.COOL
    assert logic.decide(M.COOL, below, target, D.COOL, params) is D.OFF


def test_band_of_zero_width_stops_at_the_target():
    params = logic.Parameters(heat_start=0.0, heat_stop=0.0, cool_start=0.0, cool_stop=0.0)
    assert logic.decide(M.HEAT, TARGET, TARGET, D.OFF, params) is D.OFF
    assert logic.decide(M.HEAT, TARGET, TARGET, D.HEAT, params) is D.OFF
    assert logic.decide(M.HEAT, TARGET - 0.1, TARGET, D.OFF, params) is D.HEAT
    assert logic.decide(M.COOL, TARGET, TARGET, D.COOL, params) is D.OFF
    assert logic.decide(M.COOL, TARGET + 0.1, TARGET, D.OFF, params) is D.COOL


def test_auto_only_changes_direction_through_off():
    assert logic.decide(M.AUTO, 21.6, TARGET, D.HEAT) is D.OFF
    assert logic.decide(M.AUTO, 20.4, TARGET, D.COOL) is D.OFF


@pytest.mark.parametrize(
    ("last", "minutes", "room", "expected"),
    [
        (D.HEAT, 5, 21.6, D.OFF),  # heating ended 5 min ago, cooling is locked
        (D.HEAT, 16, 21.6, D.COOL),
        (D.HEAT, 5, 20.4, D.HEAT),  # the own direction stays free
        (D.COOL, 5, 20.4, D.OFF),
        (D.COOL, 15, 20.4, D.HEAT),
        (D.HEAT, None, 21.6, D.COOL),  # run still going or never ended
    ],
)
def test_lock(last, minutes, room, expected):
    locked = logic.locked_direction(last, minutes)
    assert logic.decide(M.AUTO, room, TARGET, D.OFF, locked=locked) is expected


def test_lock_only_applies_to_auto():
    locked = logic.locked_direction(D.HEAT, 1)
    assert logic.decide(M.COOL, 21.6, TARGET, D.OFF, locked=locked) is D.COOL


def test_doors_block_start_but_not_a_running_unit():
    assert logic.decide(M.HEAT, 20.0, TARGET, D.OFF, may_start=False) is D.OFF
    assert logic.decide(M.HEAT, 20.0, TARGET, D.HEAT, may_start=False) is D.HEAT
    assert logic.decide(M.AUTO, 20.0, TARGET, D.OFF, may_start=False) is D.OFF


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (-0.15, 0.5), (0, 0.5), (0.5, 0.5), (0.51, 1.0), (0.91, 1.0), (0.92, 1.5),
        (1.23, 1.5), (1.24, 2.0), (1.5, 2.0), (1.51, 2.5), (1.73, 2.5), (1.74, 3.0),
        (1.94, 3.0), (1.95, 3.5), (2.14, 3.5), (2.15, 4.0), (2.5, 4.5), (5, 15.5),
    ],
)
def test_offset_steps(distance, expected):
    assert logic.offset(distance, 0.5) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("direction", "room", "unit", "expected"),
    [
        (D.HEAT, 20.4, 23, 24.0),
        (D.HEAT, 20.09, 23, 24.0),
        (D.HEAT, 19.77, 23, 24.5),
        (D.HEAT, 18.5, 23, 27.5),
        (D.HEAT, 16.0, 23, 30.0),  # 31 steps, clamped to max_setpoint
        (D.HEAT, 21.1, 23, 23.5),
        (D.HEAT, 19.98, 23, 24.5),  # observed live on 13.11.2026
        (D.COOL, 21.6, 23, 22.0),
        (D.COOL, 20.85, 23, 22.5),
        (D.COOL, 25.0, 17, 16.0),  # clamped to min_setpoint
        (D.OFF, 20.0, 23, None),
    ],
)
def test_setpoint(direction, room, unit, expected):
    assert logic.setpoint(direction, room, TARGET, unit, 0.5) == expected


def test_setpoint_rounds_half_up_to_the_unit_step():
    assert logic.round_to_step(23.25, 0.5) == 23.5
    assert logic.round_to_step(23.24, 0.5) == 23.0


@pytest.mark.parametrize(
    ("current", "desired", "expected"),
    [(None, 24.0, True), (24.0, 24.0, False), (24.0, 24.5, True), (24.0, 24.2, False)],
)
def test_should_send(current, desired, expected):
    assert logic.should_send(current, desired, 0.5) is expected


def test_parameters_change_thresholds():
    params = logic.Parameters(auto_start=1.0, lock_minutes=30)
    assert logic.decide(M.AUTO, 20.4, TARGET, D.OFF, params) is D.OFF
    assert logic.decide(M.AUTO, 19.9, TARGET, D.OFF, params) is D.HEAT
    assert logic.locked_direction(D.HEAT, 20, params) is D.COOL
