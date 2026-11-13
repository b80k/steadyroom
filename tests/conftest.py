"""Fixtures shared by the Home Assistant tests."""

from __future__ import annotations

import pytest

from typing import Any

from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant, ServiceRegistry, callback

from helpers import UNIT, Call, CallLog, UnitSim


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components/."""


@pytest.fixture
def calls(hass: HomeAssistant) -> CallLog:
    """Record every service call fired on the bus.

    Listening to the bus instead of mocking the climate services keeps the
    real climate services working for the SteadyRoom entity itself; a call to
    the simulated unit reaches no entity and only leaves this record.
    """
    log = CallLog()

    @callback
    def record(event: Event) -> None:
        log.append(
            Call(event.data["domain"], event.data["service"], dict(event.data["service_data"]), event.context.id)
        )

    hass.bus.async_listen(EVENT_CALL_SERVICE, record)
    return log


@pytest.fixture
def unit_sim(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> UnitSim:
    """Let the simulated unit fail commands on demand and show their effect."""
    sim = UnitSim(hass)
    original = ServiceRegistry.async_call

    async def async_call(
        registry: ServiceRegistry,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        to_unit = domain == "climate" and (service_data or {}).get("entity_id") == UNIT
        data = {k: v for k, v in (service_data or {}).items() if k != "entity_id"}
        if to_unit:
            sim.before(service, data)
        result = await original(registry, domain, service, service_data, *args, **kwargs)
        if to_unit:
            sim.after(service, data)
        return result

    monkeypatch.setattr(ServiceRegistry, "async_call", async_call)
    return sim
