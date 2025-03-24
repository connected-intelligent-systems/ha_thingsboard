"""Constants for the thingsboard integration."""

DOMAIN = "thingsboard"
MQTT_TIMEOUT = 5
DEFAULT_HOST = "mqtt.example.local"
DEFAULT_PORT = 8883
DEFAULT_TLS = True
DEFAULT_TLS_INSECURE = False
DEFAULT_THING_MODEL_URL = "https://raw.githubusercontent.com/connected-intelligent-systems/thing-models/main/home_assistant"
QOS_DEFAULT = 0
QOS_RELIABLE = 1
TIMESTAMP_MULTIPLIER = 1000

# define here to avoid errors if hass version < 2024.7
EVENT_STATE_CHANGED = "state_changed"
EVENT_STATE_REPORTED = "state_reported"
