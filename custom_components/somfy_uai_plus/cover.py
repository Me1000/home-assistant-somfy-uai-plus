"""Cover platform for Somfy UAI+ integration."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    CoverDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SomfyUAICoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Somfy UAI+ cover entities."""
    coordinator: SomfyUAICoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Wait for initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Create cover entities for each device
    entities = []
    for node_id, device_data in coordinator.data.items():
        entities.append(SomfyUAICover(coordinator, node_id, device_data))
    
    async_add_entities(entities)


class SomfyUAICover(CoordinatorEntity, CoverEntity):
    """Representation of a Somfy UAI+ cover."""

    def __init__(
        self,
        coordinator: SomfyUAICoordinator,
        node_id: str,
        device_data: Dict[str, Any],
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._node_id = node_id
        self._attr_unique_id = f"{DOMAIN}_{node_id}"
        self._attr_name = device_data.get("label", f"Shade {node_id}")
        self._attr_device_class = CoverDeviceClass.SHADE
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.STOP
        )

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._node_id)},
            "name": self._attr_name,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
            "sw_version": self.coordinator.data.get(self._node_id, {}).get("serial_number"),
        }

    @property
    def current_cover_position(self) -> Optional[int]:
        """Return current position of cover (0-100)."""
        if self._node_id in self.coordinator.data:
            somfy_position = self.coordinator.data[self._node_id].get("position")
            if somfy_position is not None:
                # Convert Somfy position (0=open, 100=closed) to HA position (0=closed, 100=open)
                return 100 - somfy_position
        return None

    @property
    def is_closed(self) -> Optional[bool]:
        """Return if the cover is closed."""
        position = self.current_cover_position
        return position == 0 if position is not None else None

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        return False  # API doesn't provide motion state

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        return False  # API doesn't provide motion state

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # Convert HA open (100) to Somfy open (0)
        await self.coordinator.client.set_position(self._node_id, 0)
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        # Convert HA close (0) to Somfy close (100)
        await self.coordinator.client.set_position(self._node_id, 100)
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        ha_position = kwargs.get("position", 0)
        # Convert HA position (0=closed, 100=open) to Somfy position (0=open, 100=closed)
        somfy_position = 100 - ha_position
        await self.coordinator.client.set_position(self._node_id, somfy_position)
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        # The API doesn't seem to have a dedicated stop command
        # We could potentially send the current position to stop movement
        current_ha_position = self.current_cover_position
        if current_ha_position is not None:
            # Convert current HA position back to Somfy position
            current_somfy_position = 100 - current_ha_position
            await self.coordinator.client.set_position(self._node_id, current_somfy_position)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        if self._node_id not in self.coordinator.data:
            return {}
        
        device_data = self.coordinator.data[self._node_id]
        return {
            "node_id": self._node_id,
            "device_type": device_data.get("type"),
            "lock_status": device_data.get("lock"),
            "direction": device_data.get("direction"),
            "limits_up": device_data.get("limits_up"),
            "limits_down": device_data.get("limits_down"),
        }