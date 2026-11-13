"""English and German texts cover the same keys as strings.json."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from custom_components.steadyroom.const import NUMBER_SPECS, Reason

_BASE = pathlib.Path(__file__).parents[1] / "custom_components" / "steadyroom"


def _load(name: str) -> dict[str, Any]:
    return json.loads((_BASE / name).read_text(encoding="utf-8"))


def _paths(tree: dict[str, Any], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        paths |= _paths(value, path) if isinstance(value, dict) else {path}
    return paths


def test_translation_english_equals_strings() -> None:
    """Custom integrations read translations/en.json; it must be strings.json."""
    assert _load("translations/en.json") == _load("strings.json")


@pytest.mark.parametrize("language", ["de"])
def test_translation_has_every_key(language: str) -> None:
    """No text falls back to English or to a raw key."""
    assert _paths(_load(f"translations/{language}.json")) == _paths(_load("strings.json"))


def test_translation_names_every_number_and_reason() -> None:
    """Every tuning value and the observation switch have a name, every reason a text."""
    strings = _load("strings.json")
    assert set(strings["entity"]["number"]) == {spec.key for spec in NUMBER_SPECS}
    reasons = strings["entity"]["climate"]["steadyroom"]["state_attributes"]["reason"]["state"]
    assert set(reasons) == {reason.value for reason in Reason}
    assert _load("translations/de.json")["entity"]["switch"]["observe_only"]["name"] == "Nur beobachten"
    assert strings["entity"]["switch"]["observe_only"]["name"] == "Observe only"
