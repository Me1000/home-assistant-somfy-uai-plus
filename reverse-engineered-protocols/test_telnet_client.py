#!/usr/bin/env python3
"""Test script for TelnetSomfyUAIClient."""
import asyncio
import logging
import sys
import os

# Add the custom component path to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components', 'somfy_uai_plus'))

from api import TelnetSomfyUAIClient

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)


async def test_telnet_client():
    """Test the telnet client functionality."""
    # Replace with your actual Somfy UAI+ IP address
    host = "10.1.1.50"
    
    client = TelnetSomfyUAIClient(host)
    
    try:
        _LOGGER.info("Testing connection...")
        if not await client.test_connection():
            _LOGGER.error("Connection test failed")
            return
        
        _LOGGER.info("Connection test passed!")
        
        _LOGGER.info("Getting devices...")
        devices = await client.get_devices()
        _LOGGER.info("Found %d devices: %s", len(devices), devices)
        
        if devices:
            # Test with first device
            device = devices[0]
            node_id = device["NODE"]
            
            _LOGGER.info("Getting device info for %s...", node_id)
            device_info = await client.get_device_info(node_id)
            _LOGGER.info("Device info: %s", device_info)
            
            # Test position setting (be careful with this!)
            # _LOGGER.info("Testing position setting to 50%...")
            # success = await client.set_position(node_id, 50)
            # _LOGGER.info("Position set result: %s", success)
        
    except Exception as err:
        _LOGGER.error("Test failed: %s", err)
        import traceback
        traceback.print_exc()
    
    finally:
        await client.close()
        _LOGGER.info("Client closed")


if __name__ == "__main__":
    asyncio.run(test_telnet_client())