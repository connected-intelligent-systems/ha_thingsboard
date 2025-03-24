from __future__ import annotations
import json
import hashlib
import uuid
import datetime
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
import paho.mqtt.client as mqtt
from .const import QOS_DEFAULT, QOS_RELIABLE, TIMESTAMP_MULTIPLIER, EVENT_STATE_REPORTED, EVENT_STATE_CHANGED


class ThingsBoardClientManager:
    def __init__(self):
        self.clients: dict[str, mqtt.Client] = {}

    def get_client(self, entry_id: str) -> mqtt.Client | None:
        return self.clients.get(entry_id)

    def create_client(self, entry: ConfigEntry, hass: HomeAssistant) -> mqtt.Client:
        client = mqtt.Client(protocol=mqtt.MQTTv31)
        client.username_pw_set(entry.data.get('access_token'))
        client.reconnect_delay_set(min_delay=1, max_delay=120)

        if entry.data.get('tls'):
            hass.async_add_executor_job(client.tls_set)
            if entry.data.get('tls_insecure'):
                client.tls_insecure_set(True)

        client.connect_async(entry.data.get('host'), entry.data.get('port'))
        client.loop_start()

        self.clients[entry.entry_id] = client
        return client

    def remove_client(self, entry_id: str) -> bool:
        if client := self.clients.get(entry_id):
            client.loop_stop()
            client.disconnect()
            del self.clients[entry_id]
            return True
        return False


client_manager = ThingsBoardClientManager()


async def get_device_ids(hass: HomeAssistant, entity_id: str) -> tuple[str | None, str | None]:
    """Get device ID and UUID for a given entity."""
    registry = async_get_entity_registry(hass)
    entity = registry.async_get(entity_id)

    if entity and entity.device_id:
        return entity.device_id, str(uuid.uuid5(uuid.NAMESPACE_OID, entity.device_id))
    return None, None


def publish_mqtt(client: mqtt.Client, topic: str, payload: dict, qos: int = QOS_DEFAULT) -> None:
    """Generic MQTT publish function."""
    message_info = client.publish(topic, json.dumps(payload), qos=qos)


def publish_connect(client: mqtt.Client, entity_id: str, device_class: str = "generic",
                    qos: int = QOS_DEFAULT) -> None:
    """Publish device connection message to ThingsBoard."""
    payload = {"device": entity_id, "type": device_class or "generic"}
    publish_mqtt(client, "v1/gateway/connect", payload, qos)


def publish_state(client: mqtt.Client, entity_id: str, state: Any,
                  device_class: str = "generic", qos: int = QOS_DEFAULT) -> None:
    """Publish entity state to ThingsBoard."""
    if state.state in ("unknown", "unavailable"):
        return

    timestamp = int(datetime.datetime.fromisoformat(
        state.last_reported.isoformat()).timestamp() * TIMESTAMP_MULTIPLIER)

    payload = {
        entity_id: [{
            "ts": timestamp,
            "values": {device_class or "generic": state.state}
        }]
    }
    publish_mqtt(client, "v1/gateway/telemetry", payload, qos)


def build_attributes(state: Any, device_id_uuid: str | None, device_id: str | None,
                     device_class: str, entry: ConfigEntry) -> dict:
    """Build ThingsBoard attributes dictionary."""
    device_class = device_class or "generic"
    return {
        "thing-metadata": {
            "parents": [device_id_uuid] if device_id else [],
            "model": state.attributes.get("model"),
            "icon": state.attributes.get("icon"),
            device_class: {"unit": state.attributes.get("unit_of_measurement")}
        },
        "thing-model": f"{entry.data.get('thing_model_repo_url')}/{device_class}.json"
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ThingsBoard integration from config entry."""
    client = client_manager.create_client(entry, hass)
    entity_id_cache: dict[str, bool] = {}

    async def handle_device_registration(entity_id: str, state: Any, device_class: str) -> None:
        """Register new device with ThingsBoard."""
        if entity_id in entity_id_cache:
            return

        device_id, device_id_uuid = await get_device_ids(hass, entity_id)
        publish_connect(client, entity_id, device_class, QOS_RELIABLE)
        publish_mqtt(
            client,
            "v1/gateway/attributes",
            {entity_id: build_attributes(
                state, device_id_uuid, device_id, device_class, entry)},
            QOS_RELIABLE
        )
        entity_id_cache[entity_id] = True

    @callback
    def should_process_event(event_data: dict) -> bool:
        """Check if event should be processed based on filters."""
        entity_id = event_data.get("entity_id")
        if entity_id in entry.data.get("entities", []):
            return True

        device_class = event_data.get("device_class")
        return device_class in entry.data.get("sensors", [])

    async def process_state_event(event: Event) -> None:
        """Process state events and publish to ThingsBoard."""
        state = event.data.get("new_state")
        entity_id = event.data.get("entity_id")
        if not state or not entity_id:
            return

        hashed_entity_id = hashlib.sha1(
            entity_id.encode("utf-8")).hexdigest()
        device_class = state.attributes.get("device_class", "generic")

        if should_process_event({"entity_id": entity_id, "device_class": device_class}):
            await handle_device_registration(hashed_entity_id, state, device_class)
            publish_state(client, hashed_entity_id, state,
                          device_class, QOS_RELIABLE)

    for event_type in (EVENT_STATE_REPORTED, EVENT_STATE_CHANGED):
        hass.bus.async_listen(
            event_type,
            process_state_event,
            event_filter=should_process_event if event_type == EVENT_STATE_REPORTED else None,
            run_immediately=True
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload ThingsBoard integration."""
    return client_manager.remove_client(entry.entry_id)
