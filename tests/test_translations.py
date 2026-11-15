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
    """Every tuning value and the control switch have a name, every reason a text."""
    strings = _load("strings.json")
    assert set(strings["entity"]["number"]) == {spec.key for spec in NUMBER_SPECS}
    reasons = strings["entity"]["climate"]["steadyroom"]["state_attributes"]["reason"]["state"]
    assert set(reasons) == {reason.value for reason in Reason}
    assert _load("translations/de.json")["entity"]["switch"]["control"]["name"] == "Anlage steuern"
    assert strings["entity"]["switch"]["control"]["name"] == "Control the unit"


@pytest.mark.parametrize("name", ["strings.json", "translations/de.json"])
def test_translation_number_names_carry_a_group(name: str) -> None:
    """Every tuning value is named "Group · detail", so the device page sorts them into groups."""
    names = {key: value["name"] for key, value in _load(name)["entity"]["number"].items()}
    assert all(" · " in label for label in names.values()), names
    groups = {key: label.split(" · ")[0] for key, label in names.items()}
    english = {key: value["name"].split(" · ")[0] for key, value in _load("strings.json")["entity"]["number"].items()}
    # German groups the same keys together as English does.
    assert _partition(groups) == _partition(english)


def _partition(groups: dict[str, str]) -> list[list[str]]:
    return sorted(sorted(key for key, group in groups.items() if group == wanted) for wanted in set(groups.values()))
