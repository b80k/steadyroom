"""Manifest promises: no Python dependency, schedule loaded first when present."""

from __future__ import annotations

import json
import pathlib

_MANIFEST = pathlib.Path(__file__).parents[1] / "custom_components" / "steadyroom" / "manifest.json"


def test_manifest_has_no_requirements() -> None:
    """Nothing but Home Assistant itself (ISC-23)."""
    assert json.loads(_MANIFEST.read_text(encoding="utf-8"))["requirements"] == []


def test_manifest_loads_after_schedule() -> None:
    """The schedule helper is set up first, so its state exists when SteadyRoom starts deciding."""
    assert json.loads(_MANIFEST.read_text(encoding="utf-8"))["after_dependencies"] == ["schedule"]
