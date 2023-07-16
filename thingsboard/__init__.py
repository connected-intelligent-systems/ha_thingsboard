"""The thingsboard integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, State

from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    EVENT_STATE_CHANGED,
    MATCH_ALL
)

from .const import DOMAIN

import paho.mqtt.client as mqtt
import sys
import json

async def get_device_id(hass: HomeAssistant, entity_id: str) -> str:
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entry = entity_registry.async_get(entity_id)
    
    if entry is not None:
        if entry.device_id is not None:
            return entry.device_id
    
    return entity_id

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:    
    client = mqtt.Client("home-assistant", protocol=mqtt.MQTTv31)
    client.username_pw_set(entry.data.get('access_token'), password=None)
    client.connect(entry.data.get('host'), entry.data.get('port'))
    
    # async def stop_event_lisstener() -> None:
    #     client.disconnect()
        
    # hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop_event_lisstener)
    
    async def state_event_listener(event: Event) -> None:
        if state := event.data.get("new_state"):
            device_id = await get_device_id(hass, state.entity_id)
            
            client.publish('v1/gateway/connect', json.dumps({
                "device" : device_id
            }))
            
            client.publish('v1/gateway/telemetry', json.dumps({
                device_id: [{
                    state.entity_id: state.as_dict()['state']
                }]
            }))
    
    hass.bus.async_listen(MATCH_ALL, state_event_listener)
    
    return True
