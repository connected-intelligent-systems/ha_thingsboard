"""The thingsboard integration."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.const import (
    MATCH_ALL
)

import hashlib
import paho.mqtt.client as mqtt
import json


@dataclass
class StateCache:
    last_updated: datetime
    last_changed: datetime


async def get_platform_from_entity_id(hass, entity_id):
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entity = entity_registry.async_get(entity_id)

    if entity:
        return entity.platform
    return None


async def get_device_id(hass: HomeAssistant, entity_id: str) -> str:
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entity = entity_registry.async_get(entity_id)

    if entity is not None:
        if entity.device_id is not None:
            return entity.device_id

    return None, None


def publishState(client, device_id, state, device_class):
    client.publish('v1/gateway/telemetry', json.dumps({
        device_id: [{
            device_class: state.as_dict()['state']
        }]
    }))


def publishAttributes(client, device_id, attributes):
    client.publish('v1/gateway/attributes', json.dumps({
        device_id: attributes
    }))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = mqtt.Client("home-assistant", protocol=mqtt.MQTTv31)
    client.username_pw_set(entry.data.get('access_token'), password=None)
    client.connect(entry.data.get('host'), entry.data.get('port'))
    entity_id_cache = dict()

    async def state_event_listener(event: Event) -> None:
        if state := event.data.get("new_state"):
            device_class = state.attributes.get('device_class')
            if device_class and state.domain == "sensor":
                entity_id = hashlib.sha1(event.data.get(
                    'entity_id').encode('utf-8')).hexdigest()
                device_id = await get_device_id(hass, event.data.get('entity_id'))

                if entity_id_cache.get(entity_id) is None:
                    attributes = {
                        'thing-metadata': {
                            'parent': device_id,
                            'description': state.attributes.get('friendly_name'),
                            'icon': state.attributes.get('icon'),
                            device_class: {
                                'unit': state.attributes.get('unit_of_measurement')
                            }
                        },
                        'thing-model': f"https://raw.githubusercontent.com/salberternst/thing-models/main/home_assistant/{device_class}.json"
                    }

                    # we are sending the attributes once
                    publishAttributes(
                        client=client, device_id=entity_id, attributes=attributes)

                    # update the cache
                    entity_id_cache[entity_id] = entity_id

                # send the current state to the thingsbaord
                publishState(client=client, device_id=entity_id,
                             state=state, device_class=device_class)

    hass.bus.async_listen(MATCH_ALL, state_event_listener)

    return True
