"""The thingsboard integration."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
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


async def get_device_id(hass: HomeAssistant, entity_id: str) -> str:
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entity = entity_registry.async_get(entity_id)
    
    if entity is not None:
        if entity.device_id is not None:
            device_registry = hass.helpers.device_registry.async_get(hass)
            device = device_registry.async_get(entity.device_id)
            return entity.device_id, device.dict_repr 
        
        # no device found (some entities don't have a device)
        # so we return the entity_id as the device_id (but hash it before)
        
        return hashlib.sha1(entity_id.encode('utf-8')).hexdigest(), entity.as_partial_dict
    
    return None,None

def publishState(client, device_id, state):
    client.publish('v1/gateway/telemetry', json.dumps({
        device_id: [{
            state.entity_id: state.as_dict()['state']
        }]
    }))
    
def publishAttributes(client, device_id, state):
    client.publish('v1/gateway/attributes', json.dumps({
        device_id: {
            state.entity_id: state.as_dict()['attributes']
        }
    }))
    
def publishDevice(client, device_id, device):
    client.publish('v1/gateway/attributes', json.dumps({
        device_id: {
            'device': device
        }
    }))
    
def publishConnectDevice(client, device_id):
    client.publish('v1/gateway/connect', json.dumps({
        "device" : device_id
    }))
    
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:    
    client = mqtt.Client("home-assistant", protocol=mqtt.MQTTv31)
    client.username_pw_set(entry.data.get('access_token'), password=None)
    client.connect(entry.data.get('host'), entry.data.get('port'))
     
    device_cache = dict()
    
    async def state_event_listener(event: Event) -> None:
        if state := event.data.get("new_state"):     
            device_id, device = await get_device_id(hass, state.entity_id)
            if device_id is None:
                return

            publishConnectDevice(client=client, device_id=device_id)
            
            # see here: https://www.home-assistant.io/docs/configuration/state_object/
            old_state = event.data.get("old_state")   
            if old_state is None:
                publishState(client=client, device_id=device_id, state=state)
                publishAttributes(client=client, device_id=device_id, state=state)
                publishDevice(client=client, device_id=device_id, device=device)
                device_cache[device_id] = device  
            elif old_state is not None and state is not None:
                if state.attributes != old_state.attributes:
                    publishAttributes(client=client, device_id=device_id, state=state)
                if state.state != old_state.state:
                    publishState(client=client, device_id=device_id, state=state)     
                if cached_device := device_cache.get(device_id):
                    if cached_device != device:
                        publishDevice(client=client, device_id=device_id, device=device)
                        device_cache[device_id] = device
                else:
                    publishDevice(client=client, device_id=device_id, device=device)
                    device_cache[device_id] = device
                
    hass.bus.async_listen(MATCH_ALL, state_event_listener)
    
    return True
