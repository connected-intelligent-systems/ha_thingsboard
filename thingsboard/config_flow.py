"""Config flow for thingsboard integration."""
from __future__ import annotations
import logging
import queue
from typing import Any
import paho.mqtt.client as mqtt
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_SENSORS
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector
from .const import DOMAIN

home_assistant_device_classes = [
    "battery",
    "cold",
    "connectivity",
    "door",
    "garage_door",
    "gas",
    "heat",
    "light",
    "lock",
    "moisture",
    "motion",
    "moving",
    "occupancy",
    "opening",
    "plug",
    "power",
    "presence",
    "problem",
    "safety",
    "smoke",
    "sound",
    "update",
    "vibration",
    "window",
    "apparent_power",
    "aqi",
    "carbon_dioxide",
    "carbon_monoxide",
    "current",
    "data_rate",
    "data_size",
    "distance",
    "energy",
    "enum",
    "frequency",
    "humidity",
    "illuminance",
    "monetary",
    "nitrogen_dioxide",
    "nitrogen_monoxide",
    "nitrous_oxide",
    "ozone",
    "pm1",
    "pm10",
    "pm25",
    "power_factor",
    "pressure",
    "signal_strength",
    "speed",
    "sulphur_dioxide",
    "temperature",
    "timestamp",
    "volatile_organic_compounds",
    "voltage",
    "weight",
    "wind_speed"
]


MQTT_TIMEOUT = 5
_LOGGER = logging.getLogger(__name__)

STEP_MQTT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host", default="dataspace.plaiful.org"): str,
        vol.Required("port", default=8883): cv.port,
        vol.Required("tls", default=True): bool,
        vol.Required("access_token"): str,
        vol.Required("thing_model_repo_url",
                     default="https://raw.githubusercontent.com/salberternst/thing-models/main/home_assistant"): str,
        vol.Required(CONF_SENSORS, default=[]): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=home_assistant_device_classes, translation_key=CONF_SENSORS, multiple=True
            ),
        ),
    }
)


def try_connection(
    user_input: dict[str, Any],
) -> int:
    client = mqtt.Client("home-assistant", protocol=mqtt.MQTTv31, userdata={})
    result: queue.Queue[int] = queue.Queue(maxsize=1)

    def on_connect(result_code: int) -> None:
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
            step_id="user", data_schema=STEP_MQTT_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
