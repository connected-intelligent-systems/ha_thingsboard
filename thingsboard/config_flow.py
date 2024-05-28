"""Config flow for thingsboard integration."""
from __future__ import annotations
import logging
import queue
from typing import Any
import voluptuous as vol
import paho.mqtt.client as mqtt
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_SENSORS
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
from .const import DOMAIN, HOME_ASSISTANT_DEVICE_CLASSES


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


MQTT_TIMEOUT = 5
_LOGGER = logging.getLogger(__name__)


def try_connection(
    user_input: dict[str, Any],
) -> int:
    """
    Tries to establish a connection to the MQTT broker using the provided user input.

    Args:
        user_input (dict[str, Any]): A dictionary containing the user input parameters.

    Returns:
        int: The result code indicating the connection status.

    Raises:
        queue.Empty: If the result queue is empty after the specified timeout.

    """
    client = mqtt.Client("home-assistant", protocol=mqtt.MQTTv31, userdata={})
    result: queue.Queue[int] = queue.Queue(maxsize=1)

    def on_connect(
        result_code: int,
        **_
    ) -> None:
        result.put(result_code)

    client.on_connect = on_connect
    client.username_pw_set(user_input['access_token'], password=None)
    client.connect_async(user_input['host'], user_input['port'])
    if user_input['tls']:
        client.tls_set()
    client.loop_start()

    try:
        return result.get(timeout=5)
    except queue.Empty:
        return mqtt.CONNACK_REFUSED_SERVER_UNAVAILABLE
    finally:
        client.disconnect()
        client.loop_stop()


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    connect_result = await hass.async_add_executor_job(
        try_connection, data
    )

    if connect_result == mqtt.CONNACK_ACCEPTED:
        return {"title": data["host"]}

    if connect_result in (mqtt.AUTH, mqtt.CONNACK_REFUSED_BAD_USERNAME_PASSWORD):
        raise InvalidAuth()
    raise CannotConnect()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for thingsboard."""

    VERSION = 1

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    config_entry,
                    data=user_input,
                    title=info["title"],
                )
                return self.async_abort(reason="updated_configuration")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required("host", default=config_entry.data.get('host')): str,
                    vol.Required("port", default=config_entry.data.get('port')): cv.port,
                    vol.Required("tls", default=config_entry.data.get('tls')): bool,
                    vol.Required("access_token", default=config_entry.data.get('access_token')): str,
                    vol.Required("thing_model_repo_url",
                                 default=config_entry.data.get('thing_model_repo_url')): str,
                    vol.Required(CONF_SENSORS, default=config_entry.data.get(CONF_SENSORS)): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=HOME_ASSISTANT_DEVICE_CLASSES, translation_key=CONF_SENSORS, multiple=True
                        ),
                    ),
                }
            ),
            errors=errors
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("host", default="thingsboard.mvp-ds.dev-prd01.fsn.iotx.materna.work"): str,
                    vol.Required("port", default=8883): cv.port,
                    vol.Required("tls", default=True): cv.boolean,
                    vol.Required("access_token"): str,
                    vol.Required("thing_model_repo_url",
                                 default="https://raw.githubusercontent.com/salberternst/thing-models/main/home_assistant"): str,
                    vol.Required(CONF_SENSORS, default=[]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=HOME_ASSISTANT_DEVICE_CLASSES, translation_key=CONF_SENSORS, multiple=True
                        ),
                    ),
                }
            ),
            errors=errors
        )
