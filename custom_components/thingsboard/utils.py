from homeassistant.helpers.entity_registry import async_get


async def get_all_device_classes(hass):
    """Retrieve all unique device_classes from entities in Home Assistant."""
    entity_registry = async_get(hass)
    device_classes = set()

    entities = entity_registry.entities.values()

    for entity in entities:
        if entity.original_device_class:
            device_classes.add(entity.original_device_class)

    return sorted(device_classes)
