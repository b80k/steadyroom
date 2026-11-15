"""Config and options flow of SteadyRoom: which entities the device works with."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er, selector

from .const import (
    CONF_CONTACTS,
    CONF_CONTACTS_INVERTED,
    CONF_FALLBACK_SENSOR,
    CONF_OBSERVE_ONLY,
    CONF_ROOM_SENSOR,
    CONF_SCHEDULE,
    CONF_UNDERLYING,
    DEFAULT_NAME,
    DEFAULT_OBSERVE_ONLY,
    DOMAIN,
)

# The schedule helper is chosen by domain only; importing its module would make
# it a dependency of this integration.
SCHEDULE_DOMAIN = "schedule"


def _temperature_sensor() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=SENSOR_DOMAIN, device_class=SensorDeviceClass.TEMPERATURE)
    )


def _schema() -> probatio.Schema:
    fields: dict[Any, Any] = {
        probatio.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
        probatio.Required(CONF_UNDERLYING): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
        ),
        probatio.Required(CONF_ROOM_SENSOR): _temperature_sensor(),
        probatio.Optional(CONF_FALLBACK_SENSOR): _temperature_sensor(),
        probatio.Optional(CONF_CONTACTS): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=BINARY_SENSOR_DOMAIN, multiple=True)
        ),
        probatio.Required(CONF_CONTACTS_INVERTED, default=False): selector.BooleanSelector(),
        probatio.Optional(CONF_SCHEDULE): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=SCHEDULE_DOMAIN)
        ),
    }
    return probatio.Schema(fields)


def _name(user_input: dict[str, Any]) -> str:
    return str(user_input.get(CONF_NAME, "")).strip() or DEFAULT_NAME


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Options as stored: empty optional choices are left out, contacts are always a list."""
    options: dict[str, Any] = {
        CONF_UNDERLYING: user_input[CONF_UNDERLYING],
        CONF_ROOM_SENSOR: user_input[CONF_ROOM_SENSOR],
        CONF_CONTACTS: list(user_input.get(CONF_CONTACTS) or []),
        CONF_CONTACTS_INVERTED: bool(user_input.get(CONF_CONTACTS_INVERTED, False)),
    }
    for key in (CONF_FALLBACK_SENSOR, CONF_SCHEDULE):
        if user_input.get(key):
            options[key] = user_input[key]
    return options


def _validate(hass: HomeAssistant, user_input: dict[str, Any], own_entry: ConfigEntry | None) -> dict[str, str]:
    """Field errors shown in the form; empty when the input is usable."""
    errors: dict[str, str] = {}
    underlying = user_input[CONF_UNDERLYING]
    registry_entry = er.async_get(hass).async_get(underlying)
    if registry_entry is not None and registry_entry.platform == DOMAIN:
        errors[CONF_UNDERLYING] = "underlying_is_steadyroom"
    elif any(
        entry.options.get(CONF_UNDERLYING) == underlying
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry is not own_entry
    ):
        errors[CONF_UNDERLYING] = "underlying_in_use"
    if user_input.get(CONF_FALLBACK_SENSOR) and user_input[CONF_FALLBACK_SENSOR] == user_input[CONF_ROOM_SENSOR]:
        errors[CONF_FALLBACK_SENSOR] = "fallback_is_room_sensor"
    return errors


class SteadyRoomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a SteadyRoom device from the UI."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for name, unit, sensors, contacts and schedule."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # A second device on the same unit would fight the first one.
            self._async_abort_entries_match({CONF_UNDERLYING: user_input[CONF_UNDERLYING]})
            errors = _validate(self.hass, user_input, None)
            if not errors:
                return self.async_create_entry(
                    title=_name(user_input),
                    data={},
                    # A new device only watches until the user turns "Control the unit" on.
                    options={**_clean(user_input), CONF_OBSERVE_ONLY: DEFAULT_OBSERVE_ONLY},
                )
        schema = _schema()
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SteadyRoomOptionsFlow:
        """Change the entity choices later."""
        return SteadyRoomOptionsFlow()


class SteadyRoomOptionsFlow(OptionsFlowWithReload):
    """Change name, unit, sensors, contacts and schedule; changed entities reload the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the current choices and store the new ones."""
        errors: dict[str, str] = {}
        entry = self.config_entry
        if user_input is not None:
            errors = _validate(self.hass, user_input, entry)
            if not errors:
                self._async_rename(_name(user_input))
                observe_only = entry.options.get(CONF_OBSERVE_ONLY, DEFAULT_OBSERVE_ONLY)
                return self.async_create_entry(data={**_clean(user_input), CONF_OBSERVE_ONLY: observe_only})
        current = user_input if user_input is not None else {CONF_NAME: entry.title, **entry.options}
        schema = self.add_suggested_values_to_schema(_schema(), current)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    @callback
    def _async_rename(self, name: str) -> None:
        """Rename entry and device; a name the user gave the device on its page stays."""
        entry = self.config_entry
        if name == entry.title:
            return
        self.hass.config_entries.async_update_entry(entry, title=name)
        device_registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
            device_registry.async_update_device(device.id, name=name)
