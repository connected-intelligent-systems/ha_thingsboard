from __future__ import annotations
import json
import hashlib
import uuid
import datetime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry
)
from homeassistant.const import (
    MATCH_ALL
)
import paho.mqtt.client as mqtt


async def get_device_id(hass: HomeAssistant, entity_id: str) -> str:
    """
    Retrieves the device ID associated with the given entity ID.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_id (str): The ID of the entity.

    Returns:
        str: The device ID associated with the entity ID.
    """
    entity_registry = async_get_entity_registry(hass)
    entity: Entity = entity_registry.async_get(entity_id)

    if entity is not None:
        if entity.device_id is not None:
            return entity.device_id, str(uuid.uuid5(uuid.NAMESPACE_OID, entity.device_id))

    return None, None


def publish_connect(client: mqtt.Client, entity_id: str, device_class: str,
                    qos: int = 0, wait: bool = False):
    """
    Publishes a connect message to the ThingsBoard gateway.

    Args:
        client (mqtt.Client): The MQTT client instance.
        entity_id (str): The ID of the device/entity to connect.
        device_class (str): The class/type of the device.
        qos (int, optional): The quality of service level for the message (default is 0).
        wait (bool, optional): Whether to wait for the message to be published (default is False).

    Returns:
        mqtt.MQTTMessageInfo: Information about the published message.

    """
    message_info = client.publish('v1/gateway/connect', json.dumps({
        'device': entity_id,
        'type': device_class
    }), qos=qos)

    if qos > 0 and wait:
        message_info.wait_for_publish()


def publish_state(client: mqtt.Client, entity_id: str, state,
                  device_class: str, qos: int = 0, wait: bool = False):
    """
    Publishes the state of an entity to the ThingsBoard IoT platform.

    Args:
        client (mqtt.Client): The MQTT client used for publishing the state.
        entity_id (str): The ID of the entity whose state is being published.
        state: The state of the entity.
        device_class (str): The device class of the entity.
        qos (int, optional): The quality of service level for the MQTT message. Defaults to 0.
        wait (bool, optional): Whether to wait for the message to be published before returning. Defaults to False.
    """
    timestamp = int(datetime.datetime.fromisoformat(
        state.last_changed.isoformat()).timestamp() * 1000)

    if state.state == "unknown" or state.state == "unavailable":
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
    """
    Publishes attributes to the ThingsBoard gateway.

    Args:
        client (mqtt.Client): The MQTT client object.
        entity_id: The ID of the entity to which the attributes belong.
        attributes: The attributes to be published.
        qos (int, optional): The quality of service level for the MQTT message. Defaults to 0.
        wait (bool, optional): Whether to wait for the message to be published. Defaults to False.
    """
    message_info = client.publish('v1/gateway/attributes', json.dumps({
        entity_id: attributes
    }), qos=qos)

    if qos > 0 and wait:
        message_info.wait_for_publish()


def build_attributes(state, device_id_uuid, device_id, device_class, entry):
    """
    Build and return a dictionary of attributes for a Thing in Thingsboard.

    Args:
        state (object): The state object containing the attributes.
        device_id_uuid (str): The UUID of the device.
        device_id (str): The ID of the device.
        device_class (str): The class of the device.
        entry (object): The entry object containing the data.

    Returns:
        dict: A dictionary of attributes for the Thing in Thingsboard.
    """
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
    """
    Set up an entry for the ThingsBoard integration.

    This function is called by Home Assistant when a ThingsBoard entry is being set up.
    It establishes a connection to the ThingsBoard MQTT broker and starts listening for state events.

    Parameters:
    - hass (HomeAssistant): The Home Assistant instance.
    - entry (ConfigEntry): The ThingsBoard configuration entry.

    Returns:
    - bool: True if the setup was successful, False otherwise.
    """
    client = mqtt.Client("home-assistant", protocol=mqtt.MQTTv31)
    client.username_pw_set(entry.data.get('access_token'), password=None)
    client.reconnect_delay_set(min_delay=1, max_delay=120)
    if entry.data.get('tls'):
        client.tls_set()
        if entry.data.get('tls_insecure'):
            client.tls_insecure_set(True)
    client.connect_async(entry.data.get('host'), entry.data.get('port'))
    client.loop_start()

    entity_id_cache = {}

#    async def state_event_listener(event: Event) -> None:
#        if state := event.data.get("new_state"):
#            device_class = state.attributes.get('device_class')
#            if device_class and state.domain in {"sensor", "binary_sensor"} and device_class in entry.data.get('sensors'):
#                entity_id = hashlib.sha1(event.data.get(
#                    'entity_id').encode('utf-8')).hexdigest()
#                device_id, device_id_uuid = await get_device_id(hass, event.data.get('entity_id'))
#
#                # If the entity ID is not in the cache, publish the device's metadata and model
#                if entity_id_cache.get(entity_id) is None:
#                    publish_connect(
#                        client=client,
#                        entity_id=entity_id,
#                        device_class=device_class,
#                        qos=1,
#                        wait=True
#                    )
#
#                    publish_attributes(
#                        client=client,
#                        entity_id=entity_id,
#                        attributes=build_attributes(
#                            state, device_id_uuid, device_id, device_class, entry),
#                        qos=1
#                    )
#
#                    entity_id_cache[entity_id] = entity_id
#
#                publish_state(
#                    client=client,
#                    entity_id=entity_id,
#                    state=state,
#                    device_class=device_class,
#                    qos=1
#                )
#
#        elif state := event.data.get("entity_id"):
#            entity_id = hashlib.sha1(state.encode('utf-8')).hexdigest()
#            if entity_id_cache.get(entity_id) is not None:
#                del entity_id_cache[entity_id]

    async def state_event_listener(event: Event) -> None:
        if state := event.data.get("new_state"):
            entity_id = event.data.get('entity_id')
            if entity_id and entity_id in entry.data.get('entities'):
                hashed_entity_id = hashlib.sha1(entity_id.encode('utf-8')).hexdigest()
                device_id, device_id_uuid = await get_device_id(hass, entity_id)

                if entity_id_cache.get(hashed_entity_id) is None:
                    publish_connect(
                        client=client,
                        entity_id=hashed_entity_id,
                        device_class=state.attributes.get('device_class'),
                        qos=1,
                        wait=True
                    )

                    publish_attributes(
                        client=client,
                        entity_id=hashed_entity_id,
                        attributes=build_attributes(
                            state, device_id_uuid, device_id, state.attributes.get('device_class'), entry),
                        qos=1
                    )

                    entity_id_cache[hashed_entity_id] = hashed_entity_id

                publish_state(
                    client=client,
                    entity_id=hashed_entity_id,
                    state=state,
                    device_class=state.attributes.get('device_class'),
                    qos=1
                )

        elif entity_id := event.data.get("entity_id"):
            hashed_entity_id = hashlib.sha1(entity_id.encode('utf-8')).hexdigest()
            if entity_id_cache.get(hashed_entity_id) is not None:
                del entity_id_cache[hashed_entity_id]

    hass.bus.async_listen(MATCH_ALL, state_event_listener)

    return True

