from __future__ import annotations
import logging
import queue
from typing import Any
import voluptuous as vol
import paho.mqtt.client as mqtt
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
from .const import DOMAIN, MQTT_TIMEOUT, DEFAULT_HOST, DEFAULT_PORT, DEFAULT_TLS, DEFAULT_TLS_INSECURE, DEFAULT_THING_MODEL_URL
from .utils import get_all_device_classes

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """Error indicating connection failure."""


class InvalidAuth(HomeAssistantError):
    """Error indicating authentication failure."""


async def try_connection(hass: HomeAssistant, user_input: dict[str, Any]) -> int:
    """Test MQTT connection with provided credentials."""
    client = mqtt.Client(protocol=mqtt.MQTTv31)
    result_queue: queue.Queue[int] = queue.Queue(maxsize=1)

    def on_connect(client_: mqtt.Client, userdata: None, flags: dict[str, Any],
                   result_code: int, properties: mqtt.Properties | None = None) -> None:
        result_queue.put(result_code)

    client.on_connect = on_connect
    client.username_pw_set(user_input["access_token"], password=None)
    client.connect_async(user_input["host"], user_input["port"])

    if user_input["tls"]:
        await hass.async_add_executor_job(client.tls_set)
        if user_input["tls_insecure"]:
            client.tls_insecure_set(True)

    client.loop_start()
    try:
        return result_queue.get(timeout=MQTT_TIMEOUT)
    except queue.Empty:
        return mqtt.CONNACK_REFUSED_SERVER_UNAVAILABLE
    finally:
        client.disconnect()
        client.loop_stop()


async def validate_mqtt_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate MQTT-specific user input and establish connection."""
    result = await try_connection(hass, data)

    if result == mqtt.CONNACK_ACCEPTED:
        return {"title": data["host"]}
    if result in (mqtt.AUTH, mqtt.CONNACK_REFUSED_BAD_USERNAME_PASSWORD):
        raise InvalidAuth
    raise CannotConnect


def get_mqtt_schema(defaults: dict[str, Any] = {}) -> vol.Schema:
    """Generate schema for MQTT settings."""
    return vol.Schema({
        vol.Required("host", default=defaults.get("host", DEFAULT_HOST)): str,
        vol.Required("port", default=defaults.get("port", DEFAULT_PORT)): cv.port,
        vol.Required("tls", default=defaults.get("tls", DEFAULT_TLS)): bool,
        vol.Required("tls_insecure", default=defaults.get("tls_insecure", DEFAULT_TLS_INSECURE)): bool,
        vol.Required("access_token", default=defaults.get("access_token", "")): str,
        vol.Required("thing_model_repo_url",
                     default=defaults.get("thing_model_repo_url", DEFAULT_THING_MODEL_URL)): str,
    })


def get_entities_schema(device_classes: list[str], defaults: dict[str, Any] = {}) -> vol.Schema:
    """Generate schema for entity and sensor selection."""
    return vol.Schema({
        vol.Required("sensors", default=defaults.get("sensors", [])):
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=device_classes,
                    translation_key="sensors",
                    multiple=True
                )
        ),
        vol.Required("entities", default=defaults.get("entities", [])):
            selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
        ),
    })


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle ThingsBoard configuration flow."""
    VERSION = 1

    def __init__(self):
        """Initialize flow instance."""
        self._mqtt_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle MQTT configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_mqtt_input(self.hass, user_input)
                self._mqtt_data = user_input
                return await self.async_step_entities()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=get_mqtt_schema(),
            errors=errors
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle entity and sensor selection step."""
        errors: dict[str, str] = {}
        config_entry = None

        if "entry_id" in self.context:
            config_entry = self.hass.config_entries.async_get_entry(
                self.context["entry_id"])

        if user_input is not None:
            try:
                combined_data = {**self._mqtt_data, **user_input}
                if config_entry:
                    return self.async_update_reload_and_abort(config_entry, data_updates=combined_data)
                return self.async_create_entry(title=self._mqtt_data["host"], data=combined_data)
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        device_classes = await get_all_device_classes(self.hass)
        return self.async_show_form(
            step_id="entities",
            data_schema=get_entities_schema(
                device_classes, config_entry.data if config_entry else {}),
            errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle reconfiguration starting with MQTT settings."""
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"])
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_mqtt_input(self.hass, user_input)
                self._mqtt_data = user_input
                return await self.async_step_entities()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=get_mqtt_schema(config_entry.data),
            errors=errors
        )
