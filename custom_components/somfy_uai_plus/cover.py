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
        self._optimistic_position = None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Only clear optimistic position if the real position is close to what we expect
        if self._optimistic_position is not None:
            real_position = None
            if self._node_id in self.coordinator.data:
                device_data = self.coordinator.data[self._node_id]
                
                # Get real position based on client type
                if device_data.get("is_telnet_client", False):
                    real_position = device_data.get("position", 0)
                else:
                    # Calculate for HTTP clients (existing logic)
                    raw_position = device_data.get("raw_position")
                    limits_up = int(device_data.get("limits_up", 0))
                    limits_down = int(device_data.get("limits_down", 10))
                    direction = device_data.get("direction", "STANDARD")
                    
                    if raw_position is not None and limits_down > limits_up:
                        position_range = limits_down - limits_up
                        relative_position = raw_position - limits_up
                        device_percentage = (relative_position / position_range) * 100
                        
                        if direction == "REVERSED":
                            real_position = 100 - device_percentage
                        else:
                            real_position = device_percentage
            
            # Clear optimistic position if real position is within 5% of expected
            if real_position is not None:
                position_diff = abs(real_position - self._optimistic_position)
                if position_diff <= 5:  # Within 5% tolerance
                    self._optimistic_position = None
        
        super()._handle_coordinator_update()

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
        # Use optimistic position if available, otherwise use coordinator data
        if self._optimistic_position is not None:
            return self._optimistic_position
        
        if self._node_id in self.coordinator.data:
            device_data = self.coordinator.data[self._node_id]
            
            # For telnet clients, use percentage directly since raw position isn't meaningful
            if device_data.get("is_telnet_client", False):
                percentage = device_data.get("position", 0)
                return max(0, min(100, int(percentage)))
            
            # For HTTP clients, calculate from raw position and limits
            raw_position = device_data.get("raw_position")
            limits_up = int(device_data.get("limits_up", 0))
            limits_down = int(device_data.get("limits_down", 10))
            direction = device_data.get("direction", "STANDARD")
            
            if raw_position is not None and limits_down > limits_up:
                # Calculate percentage from raw position and limits
                position_range = limits_down - limits_up
                relative_position = raw_position - limits_up
                device_percentage = (relative_position / position_range) * 100
                
                # Convert to HA position based on device direction
                if direction == "REVERSED":
                    # Reversed: device 0% = HA 100% (open), device 100% = HA 0% (closed)
                    ha_position = 100 - device_percentage
                else:
                    # Standard: device 0% = HA 0% (closed), device 100% = HA 100% (open)
                    ha_position = device_percentage
                    
                return max(0, min(100, int(ha_position)))
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
        # Set optimistic position immediately
        self._optimistic_position = 100
        self.async_write_ha_state()
        
        # Get device limits from coordinator data
        device_data = self.coordinator.data.get(self._node_id, {})
        limits_down = int(device_data.get("limits_down", 10))
        direction = device_data.get("direction", "STANDARD")
        
        # Convert HA open (100) based on device direction
        if direction == "REVERSED":
            device_position = 0  # Reversed: open = 0
        else:
            device_position = limits_down  # Standard: open = limits_down
            
        await self.coordinator.client.set_position_raw(self._node_id, device_position)
        # Don't immediately refresh - let coordinator poll on its normal schedule
        # This preserves the optimistic position for better UX

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        # Set optimistic position immediately
        self._optimistic_position = 0
        self.async_write_ha_state()
        
        # Get device limits from coordinator data
        device_data = self.coordinator.data.get(self._node_id, {})
        limits_down = int(device_data.get("limits_down", 10))
        direction = device_data.get("direction", "STANDARD")
        
        # Convert HA close (0) based on device direction
        if direction == "REVERSED":
            device_position = limits_down  # Reversed: close = limits_down
        else:
            device_position = 0  # Standard: close = 0
            
        await self.coordinator.client.set_position_raw(self._node_id, device_position)
        # Don't immediately refresh - let coordinator poll on its normal schedule
        # This preserves the optimistic position for better UX

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        ha_position = kwargs.get("position", 0)
        
        # Set optimistic position immediately
        self._optimistic_position = ha_position
        self.async_write_ha_state()
        
        # Get device limits from coordinator data
        device_data = self.coordinator.data.get(self._node_id, {})
        limits_down = int(device_data.get("limits_down", 10))
        direction = device_data.get("direction", "STANDARD")
        
        # Convert HA position based on device direction
        if direction == "REVERSED":
            # For reversed motors: HA 0%=closed maps to device 100% of limits_down
            device_position = int((100 - ha_position) * limits_down / 100)
        else:
            # For standard motors: HA 0%=closed maps to device 0% of limits_down  
            device_position = int(ha_position * limits_down / 100)
            
        _LOGGER.info("Setting position: HA %s%% -> device %s (direction=%s, limits_down=%s)", 
                     ha_position, device_position, direction, limits_down)
        await self.coordinator.client.set_position_raw(self._node_id, device_position)
        # Don't immediately refresh - let coordinator poll on its normal schedule
        # This preserves the optimistic position for better UX

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        # The API doesn't seem to have a dedicated stop command
        # We could potentially send the current position to stop movement
        current_ha_position = self.current_cover_position
        if current_ha_position is not None:
            # Get device limits from coordinator data
            device_data = self.coordinator.data.get(self._node_id, {})
            limits_down = int(device_data.get("limits_down", 10))
            direction = device_data.get("direction", "STANDARD")
            
            # Convert current HA position to device position
            if direction == "REVERSED":
                device_position = int((100 - current_ha_position) * limits_down / 100)
            else:
                device_position = int(current_ha_position * limits_down / 100)
                
            await self.coordinator.client.set_position_raw(self._node_id, device_position)

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