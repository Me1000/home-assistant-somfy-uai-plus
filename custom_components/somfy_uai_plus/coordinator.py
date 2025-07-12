"""Data update coordinator for Somfy UAI+."""
import logging
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SomfyUAIClient, TelnetSomfyUAIClient
from .const import (
    DEFAULT_SCAN_INTERVAL, 
    DOMAIN, 
    CONF_SCAN_INTERVAL, 
    CONF_PROTOCOL, 
    PROTOCOL_TELNET, 
    DEFAULT_PROTOCOL
)

_LOGGER = logging.getLogger(__name__)


class SomfyUAICoordinator(DataUpdateCoordinator):
    """Class to manage fetching Somfy UAI+ data."""

    def __init__(self, hass: HomeAssistant, client: SomfyUAIClient, scan_interval: int = DEFAULT_SCAN_INTERVAL) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.devices: List[Dict[str, Any]] = []

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            # Get all devices first
            devices = await self.client.get_devices()
            self.devices = devices
            
            # Get detailed info for each device
            device_data = {}
            for device in devices:
                node_id = device.get("NODE")
                if node_id:
                    device_info = await self.client.get_device_info(node_id)
                    if device_info:
                        # Parse position from the format "11093 (92 %)"
                        position_str = device_info.get("POSITION", "0 (0 %)")
                        try:
                            # Extract percentage from parentheses
                            percentage = int(position_str.split("(")[1].split(" %")[0])
                            # Also get raw position value for telnet client compatibility
                            raw_position = int(position_str.split(" (")[0])
                        except (IndexError, ValueError):
                            percentage = 0
                            raw_position = 0
                        
                        device_data[node_id] = {
                            "node_id": node_id,
                            "label": device_info.get("LABEL", device.get("LABEL", "Unknown")),
                            "type": device_info.get("TYPE", "Unknown"),
                            "position": percentage,
                            "raw_position": raw_position,
                            "lock": device_info.get("LOCK", "Unknown"),
                            "direction": device_info.get("DIRECTION", "STANDARD"),
                            "limits_up": device_info.get("LIMITS UP", "0"),
                            "limits_down": device_info.get("LIMITS DOWN", "12100"),
                            "serial_number": device_info.get("SERIAL NUMBER", "").strip(),
                        }
            
            return device_data
            
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err