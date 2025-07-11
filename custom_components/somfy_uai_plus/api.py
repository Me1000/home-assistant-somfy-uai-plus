"""API client for Somfy UAI+ controller."""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)


class SomfyUAIClient:
    """Client for communicating with Somfy UAI+ controller."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        """Initialize the client."""
        self.host = host
        self.session = session
        self.base_url = f"http://{host}"

    async def test_connection(self) -> bool:
        """Test connection to the controller."""
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(f"{self.base_url}/somfy_devices.json") as response:
                    return response.status == 200
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Connection test failed: %s", err)
            return False

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get all available shade devices."""
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(f"{self.base_url}/somfy_devices.json") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("DEVICES", [])
                    else:
                        _LOGGER.error("Failed to get devices: HTTP %s", response.status)
                        return []
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Failed to get devices: %s", err)
            return []

    async def get_device_info(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific device."""
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(f"{self.base_url}/somfy_device.json?{node_id}") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("DEVICE")
                    else:
                        _LOGGER.error("Failed to get device info for %s: HTTP %s", node_id, response.status)
                        return None
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Failed to get device info for %s: %s", node_id, err)
            return None

    async def set_position(self, node_id: str, position: int) -> bool:
        """Set the position of a shade (0-100)."""
        if not 0 <= position <= 100:
            _LOGGER.error("Invalid position %s for device %s", position, node_id)
            return False
        
        # Convert percentage to device position (0-12100 range based on your example)
        device_position = int(position * 121)
        
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(f"{self.base_url}/somfy.cgi?{node_id}:POSITION={device_position}") as response:
                    success = response.status == 200
                    if not success:
                        _LOGGER.error("Failed to set position for %s: HTTP %s", node_id, response.status)
                    return success
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Failed to set position for %s: %s", node_id, err)
            return False