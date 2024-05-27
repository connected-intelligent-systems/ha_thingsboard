"""The thingsboard integration."""
from __future__ import annotations
import json
import hashlib
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
import datetime
from homeassistant.const import (
    MATCH_ALL
)
import paho.mqtt.client as mqtt


async def get_platform_from_entity_id(hass, entity_id):
    """
    Asynchronously retrieves the platform of an entity in the Home Assistant ecosystem.

    This function fetches the platform of a specified entity by its entity ID. If the entity
    is found in the entity registry, the function returns its associated platform. If the entity
    is not found, the function returns None.

    Args:
        hass: The HomeAssistant instance, used to access the entity registry.
        entity_id (str): The unique identifier of the entity whose platform is to be retrieved.

    Returns:
        str or None: The platform of the specified entity if found, otherwise None.
    """
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entity = entity_registry.async_get(entity_id)

    if entity:
        return entity.platform
    return None


async def get_device_id(hass: HomeAssistant, entity_id: str) -> str:
    """
    Publishes the state of a device to a specific topic in the MQTT broker.

    This function serializes the state of a device along with its device class and publishes it
    to the 'v1/gateway/telemetry' topic. The data is formatted in JSON with the device ID as the key.

    Args:
        client: The MQTT client used for publishing the message.
        device_id (str): The ID of the device whose state is being published.
        state: The state object of the device, expected to have an 'as_dict' method.
        device_class (str): The class of the device (e.g., sensor, light).

    Returns:
        None
    """
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entity = entity_registry.async_get(entity_id)

    if entity is not None:
        if entity.device_id is not None:
            return entity.device_id

    return None


def publish_connect(client, device_id, device_class):
    """
    Connects the device to Thingsboard.

    Args:
        client: The MQTT client used for publishing the message.
        device_id (str): The ID of the device whose state is being published.
        device_class (str): The class of the device (e.g., sensor, light).

    Returns:
        None
    """
    return client.publish('v1/gateway/connect', json.dumps({
        'device': device_id,
        'type': device_class
    }))


def publish_state(client, device_id, state, device_class):
    """
    Publishes the state of a device to a specific topic in the Thingsboard MQTT broker.

    This function serializes the state of a device along with its device class and publishes it
    to the 'v1/gateway/telemetry' topic. The data is formatted in JSON with the device ID as the key.

    Args:
        client: The MQTT client used for publishing the message.
        device_id (str): The ID of the device whose state is being published.
        state: The state object of the device, expected to have an 'as_dict' method.
        device_class (str): The class of the device (e.g., sensor, light).

    Returns:
        None
    """

    ts = int(datetime.datetime.fromisoformat(state.last_changed.isoformat()).timestamp() * 1000)
    return client.publish('v1/gateway/telemetry', json.dumps({
        device_id: [{
            "ts": ts,
            "values": {
                device_class: state.as_dict()['state']}
        }]
    }), qos=1)


def publish_attributes(client, device_id, attributes):
    """
    Publishes attributes of a device to a specific topic in the Thingsboard MQTT broker.

    This function takes the attributes of a device and publishes them to the
    'v1/gateway/attributes' topic in the MQTT broker. The data is formatted in JSON with
    the device ID as the key.

    Args:
        client: The MQTT client used for publishing the message.
        device_id (str): The ID of the device whose attributes are being published.
        attributes (dict): A dictionary of the attributes to be published.

    Returns:
        None
    """
    return client.publish('v1/gateway/attributes', json.dumps({
        device_id: attributes
    }), qos=1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Set up an entry for ThingsBoard integration.

    This function is called by Home Assistant when setting up a ThingsBoard integration entry.
    It establishes a connection to the ThingsBoard MQTT broker and listens for state events
    from sensors specified in the entry's configuration.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The ThingsBoard integration entry.

    Returns:
        bool: True if the setup was successful, False otherwise.
    """
    client = mqtt.Client("home-assistant", protocol=mqtt.MQTTv31)
    client.username_pw_set(entry.data.get('access_token'), password=None)
    if entry.data.get('tls'):
        client.tls_set()
    client.connect(entry.data.get('host'), entry.data.get('port'))
    entity_id_cache = {}

    async def state_event_listener(event: Event) -> None:
        if state := event.data.get("new_state"):
            device_class = state.attributes.get('device_class')
            if device_class and state.domain == "sensor" and device_class in entry.data.get('sensors'):
                entity_id = hashlib.sha1(event.data.get(
                    'entity_id').encode('utf-8')).hexdigest()
                device_id = await get_device_id(hass, event.data.get('entity_id'))
                
                # If the entity ID is not in the cache, publish the device's metadata and model
                if entity_id_cache.get(entity_id) is None:
                    attributes = {
                        'thing-metadata': {
                            'parents': [
                                device_id
                            ] if device_id is not None else [],
                            'description': state.attributes.get('friendly_name'),
                            'icon': state.attributes.get('icon'),
                            device_class: {
                                'unit': state.attributes.get('unit_of_measurement')
                            }
                        },
                        'thing-model': f"{entry.data.get('thing_model_repo_url')}/{device_class}.json"
                    }

                    message_info = publish_connect(
                        client=client, device_id=entity_id, device_class=device_class)
                    message_info.wait_for_publish()

                    publish_attributes(
                        client=client, device_id=entity_id, attributes=attributes)

                    entity_id_cache[entity_id] = entity_id

                publish_state(client=client, device_id=entity_id,
                             state=state, device_class=device_class)

    hass.bus.async_listen(MATCH_ALL, state_event_listener)

    return True