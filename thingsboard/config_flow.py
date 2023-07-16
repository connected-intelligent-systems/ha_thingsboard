"""Config flow for thingsboard integration."""
from __future__ import annotations

import paho.mqtt.client as mqtt 

import logging
from typing import Any

import voluptuous as vol
import queue

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

MQTT_TIMEOUT = 5
_LOGGER = logging.getLogger(__name__)

# TODO adjust the data schema to the data that you need
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("port", default=8081): cv.port,
        vol.Required("access_token", default="thetoken"): str
    }
)

def try_connection(
    user_input: dict[str, Any],
) -> int:
    client = mqtt.Client("home-assistant", protocol=mqtt.MQTTv31, userdata={})
    result: queue.Queue[int] = queue.Queue(maxsize=1)

    def on_connect(
        client_: mqtt.Client,
        userdata: None,
        flags: dict[str, Any],
        result_code: int,
        properties: mqtt.Properties | None = None,
    ) -> None:
        """Handle connection result."""
        result.put(result_code)

    client.on_connect = on_connect
    client.username_pw_set(user_input['access_token'], password=None)
    client.connect_async(user_input['host'], user_input['port'])
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
    elif connect_result == mqtt.AUTH or connect_result == mqtt.CONNACK_REFUSED_BAD_USERNAME_PASSWORD:
        raise InvalidAuth()
    else:
        raise CannotConnect()

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for thingsboard."""

    VERSION = 1

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
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
