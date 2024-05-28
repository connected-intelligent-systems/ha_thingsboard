"""The thingsboard integration."""
from __future__ import annotations
import json
import hashlib
import uuid
import datetime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.const import (
    MATCH_ALL
)
import paho.mqtt.client as mqtt


async def get_platform_from_entity_id(hass, entity_id):
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entity = entity_registry.async_get(entity_id)

    if entity:
        return entity.platform
    return None


async def get_device_id(hass: HomeAssistant, entity_id: str) -> str:
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entity: Entity = entity_registry.async_get(entity_id)

    if entity is not None:
        if entity.device_id is not None:
            return entity.device_id, str(uuid.uuid5(uuid.NAMESPACE_OID, entity.device_id))

    return None, None


def publish_connect(client: mqtt.Client, entity_id, device_class, qos: int = 0, wait: bool = False):
    message_info = client.publish('v1/gateway/connect', json.dumps({
        'device': entity_id,
        'type': device_class
    }), qos=qos)

    if qos > 0 and wait:
        message_info.wait_for_publish()


def publish_state(client: mqtt.Client, entity_id, state, device_class, qos: int = 0, wait: bool = False):
    timestamp = int(datetime.datetime.fromisoformat(
        state.last_changed.isoformat()).timestamp() * 1000)

    if state.state == "unknown":
        return

    message_info = client.publish('v1/gateway/telemetry', json.dumps({
        entity_id: [{
            "ts": timestamp,
            "values": {
                device_class: state.state
            }
        }]
    }), qos=qos)

    if qos > 0 and wait:
        message_info.wait_for_publish()


def publish_attributes(client: mqtt.Client, entity_id, attributes, qos: int = 0, wait: bool = False):
    message_info = client.publish('v1/gateway/attributes', json.dumps({
        entity_id: attributes
    }), qos=qos)

    if qos > 0 and wait:
        message_info.wait_for_publish()


def build_attributes(state, device_id_uuid, device_id, device_class, entry):
    return {
        'thing-metadata': {
            'parents': [
                device_id_uuid
            ] if device_id is not None else [],
            'description': state.attributes.get('friendly_name'),
            'icon': state.attributes.get('icon'),
            device_class: {
                'unit': state.attributes.get('unit_of_measurement')
            }
        },
        'thing-model': f"{entry.data.get('thing_model_repo_url')}/{device_class}.json"
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = mqtt.Client("home-assistant", protocol=mqtt.MQTTv31)
    client.username_pw_set(entry.data.get('access_token'), password=None)
    client.reconnect_delay_set(min_delay=1, max_delay=120)
    if entry.data.get('tls'):
        client.tls_set()
    client.connect(entry.data.get('host'), entry.data.get('port'))
    client.loop_start()

    entity_id_cache = {}

    async def state_event_listener(event: Event) -> None:
        if state := event.data.get("new_state"):
            device_class = state.attributes.get('device_class')
            if device_class and state.domain == "sensor" and device_class in entry.data.get('sensors'):
                entity_id = hashlib.sha1(event.data.get(
                    'entity_id').encode('utf-8')).hexdigest()
                device_id, device_id_uuid = await get_device_id(hass, event.data.get('entity_id'))

                # If the entity ID is not in the cache, publish the device's metadata and model
                if entity_id_cache.get(entity_id) is None:
                    publish_connect(
                        client=client,
                        entity_id=entity_id,
                        device_class=device_class,
                        qos=1,
                        wait=True
                    )

                    publish_attributes(
                        client=client,
                        entity_id=entity_id,
                        attributes=build_attributes(
                            state, device_id_uuid, device_id, device_class, entry),
                        qos=1
                    )

                    entity_id_cache[entity_id] = entity_id

                publish_state(
                    client=client,
                    entity_id=entity_id,
                    state=state,
                    device_class=device_class,
                    qos=1
                )

        elif state := event.data.get("entity_id"):
            entity_id = hashlib.sha1(state.encode('utf-8')).hexdigest()
            if entity_id_cache.get(entity_id) is not None:
                del entity_id_cache[entity_id]

    hass.bus.async_listen(MATCH_ALL, state_event_listener)

    return True
