"""API client for Somfy UAI+ controller."""
import asyncio
import json
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
        
        try:
            # Get device info to determine actual limits
            device_info = await self.get_device_info(node_id)
            if not device_info:
                _LOGGER.error("Could not get device info for %s to determine limits", node_id)
                return False
            
            # Parse limits from device info
            try:
                limits_up = int(device_info.get("LIMITS UP", "0"))
                limits_down = int(device_info.get("LIMITS DOWN", "100"))
            except (ValueError, TypeError):
                _LOGGER.error("Invalid limits for device %s: up=%s, down=%s", 
                             node_id, device_info.get("LIMITS UP"), device_info.get("LIMITS DOWN"))
                return False
            
            # Calculate device position based on actual device limits
            if limits_down <= limits_up:
                _LOGGER.error("Invalid limits for device %s: up=%s >= down=%s", 
                             node_id, limits_up, limits_down)
                return False
            
            position_range = limits_down - limits_up
            device_position = int((position / 100) * position_range) + limits_up
            
            _LOGGER.debug("Device %s: HA position=%s%%, device_position=%s, limits=[%s,%s]", 
                         node_id, position, device_position, limits_up, limits_down)
            
            async with async_timeout.timeout(10):
                async with self.session.get(f"{self.base_url}/somfy.cgi?{node_id}:POSITION={device_position}") as response:
                    success = response.status == 200
                    if not success:
                        _LOGGER.error("Failed to set position for %s: HTTP %s", node_id, response.status)
                    return success
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Failed to set position for %s: %s", node_id, err)
            return False

    async def set_position_raw(self, node_id: str, raw_position: int) -> bool:
        """Set the raw position of a shade using actual device limits."""
        try:
            # Get device info to determine actual limits
            device_info = await self.get_device_info(node_id)
            if not device_info:
                _LOGGER.error("Could not get device info for %s to determine limits", node_id)
                return False
            
            # Parse limits from device info
            try:
                limits_up = int(device_info.get("LIMITS UP", "0"))
                limits_down = int(device_info.get("LIMITS DOWN", "100"))
            except (ValueError, TypeError):
                _LOGGER.error("Invalid limits for device %s: up=%s, down=%s", 
                             node_id, device_info.get("LIMITS UP"), device_info.get("LIMITS DOWN"))
                return False
            
            # Calculate percentage based on actual device limits
            if limits_down <= limits_up:
                _LOGGER.error("Invalid limits for device %s: up=%s >= down=%s", 
                             node_id, limits_up, limits_down)
                return False
            
            # Clamp raw position to device limits
            clamped_position = max(limits_up, min(limits_down, raw_position))
            
            # Convert to percentage
            position_range = limits_down - limits_up
            relative_position = clamped_position - limits_up
            percentage = int((relative_position / position_range) * 100)
            
            _LOGGER.debug("Device %s: raw_position=%s, limits=[%s,%s], percentage=%s", 
                         node_id, raw_position, limits_up, limits_down, percentage)
            
            return await self.set_position(node_id, percentage)
            
        except Exception as err:
            _LOGGER.error("Failed to set raw position for %s: %s", node_id, err)
            return False


class TelnetConnectionManager:
    """Shared connection manager for telnet protocol."""
    _instances: Dict[str, "TelnetConnectionManager"] = {}
    _locks: Dict[str, asyncio.Lock] = {}
    
    def __new__(cls, host: str, port: int = 23, username: str = "Telnet 1", password: str = "Password 1"):
        """Singleton per host to share connections."""
        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = super().__new__(cls)
            cls._locks[key] = asyncio.Lock()
        return cls._instances[key]
    
    def __init__(self, host: str, port: int = 23, username: str = "Telnet 1", password: str = "Password 1") -> None:
        """Initialize the connection manager."""
        if hasattr(self, '_initialized'):
            return
        
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._request_id = 8900
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
        self._connected = False
        self._request_queue = asyncio.Queue()
        self._queue_task: Optional[asyncio.Task] = None
        self._request_lock = asyncio.Lock()
        self._initialized = True

    async def _connect(self) -> bool:
        """Connect to the telnet server and authenticate."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=10
            )
            
            # Read "User:" prompt
            await self._read_until(b"User:")
            
            # Send username
            self._writer.write(f"{self.username}\r\n".encode())
            await self._writer.drain()
            
            # Read "Password:" prompt
            await self._read_until(b"Password:")
            
            # Send password
            self._writer.write(f"{self.password}\r\n".encode())
            await self._writer.drain()
            
            # Read "Connected:" confirmation
            await self._read_until(b"Connected:")
            
            self._connected = True
            
            # Start the response reading task and queue processor
            self._read_task = asyncio.create_task(self._read_responses())
            self._queue_task = asyncio.create_task(self._process_queue())
            
            _LOGGER.info("Successfully connected to telnet server at %s:%s", self.host, self.port)
            return True
            
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.error("Failed to connect to telnet server: %s", err)
            await self._disconnect()
            return False

    async def _read_until(self, delimiter: bytes) -> bytes:
        """Read data until delimiter is found."""
        data = b""
        while delimiter not in data:
            chunk = await asyncio.wait_for(self._reader.read(1024), timeout=10)
            if not chunk:
                raise ConnectionError("Connection closed unexpectedly")
            data += chunk
        return data

    async def _disconnect(self) -> None:
        """Disconnect from the telnet server."""
        self._connected = False
        
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None
        
        if self._queue_task:
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
            self._queue_task = None
        
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        
        self._reader = None
        
        # Cancel any pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

    async def _read_responses(self) -> None:
        """Read and handle JSON-RPC responses from the server."""
        buffer = ""
        
        try:
            while self._connected and self._reader:
                try:
                    data = await asyncio.wait_for(self._reader.read(1024), timeout=1.0)
                    if not data:
                        break
                    
                    buffer += data.decode('utf-8', errors='ignore')
                    
                    # Look for complete JSON objects
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        
                        if line.startswith('{') and line.endswith('}'):
                            try:
                                response = json.loads(line)
                                await self._handle_response(response)
                            except json.JSONDecodeError as err:
                                _LOGGER.warning("Failed to parse JSON response: %s", err)
                                
                except asyncio.TimeoutError:
                    continue
                except Exception as err:
                    _LOGGER.error("Error reading responses: %s", err)
                    break
                    
        finally:
            self._connected = False

    async def _handle_response(self, response: Dict[str, Any]) -> None:
        """Handle a JSON-RPC response."""
        request_id = response.get("id")
        if request_id and request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                if "result" in response:
                    future.set_result(response["result"])
                elif "error" in response:
                    future.set_exception(Exception(f"JSON-RPC error: {response['error']}"))
                else:
                    future.set_exception(Exception("Invalid JSON-RPC response"))

    async def _process_queue(self) -> None:
        """Process queued requests sequentially."""
        try:
            while self._connected:
                try:
                    # Get next request from queue
                    request_data = await asyncio.wait_for(self._request_queue.get(), timeout=1.0)
                    
                    if not self._connected or not self._writer:
                        # Connection lost, reject request
                        request_data["future"].set_exception(ConnectionError("Connection lost"))
                        continue
                    
                    try:
                        # Send request
                        request_json = json.dumps(request_data["request"]) + "\r\n"
                        self._writer.write(request_json.encode())
                        await self._writer.drain()
                        
                        # Small delay between requests to avoid overwhelming the device
                        await asyncio.sleep(0.1)
                        
                    except Exception as err:
                        request_data["future"].set_exception(err)
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as err:
                    _LOGGER.error("Error processing request queue: %s", err)
                    break
                    
        finally:
            # Reject any remaining queued requests
            while not self._request_queue.empty():
                try:
                    request_data = self._request_queue.get_nowait()
                    request_data["future"].set_exception(ConnectionError("Queue processor stopped"))
                except asyncio.QueueEmpty:
                    break

    async def _send_request(self, method: str, params: List[Dict[str, Any]]) -> Any:
        """Send a JSON-RPC request and wait for response."""
        async with self._request_lock:
            if not self._connected:
                if not await self._connect():
                    raise ConnectionError("Failed to connect to telnet server")
            
            self._request_id += 1
            request_id = self._request_id
            
            request = {
                "method": method,
                "params": params,
                "id": request_id
            }
            
            # Create future for response
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            # Queue the request for sequential processing
            request_data = {
                "request": request,
                "future": future
            }
            
            try:
                await self._request_queue.put(request_data)
                
                # Wait for response with timeout
                result = await asyncio.wait_for(future, timeout=10)
                return result
                
            except asyncio.TimeoutError:
                self._pending_requests.pop(request_id, None)
                raise asyncio.TimeoutError(f"Request {method} timed out")
            except Exception as err:
                self._pending_requests.pop(request_id, None)
                raise err

    async def test_connection(self) -> bool:
        """Test connection to the controller."""
        try:
            # Try to ping all devices
            result = await self._send_request("sdn.status.ping", [{"targetID": "*"}])
            return isinstance(result, list)
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", err)
            return False

    def _normalize_node_id(self, telnet_node_id: str) -> str:
        """Convert telnet node ID format to HTTP API format.
        
        Telnet: 132A01 -> HTTP: 13.2A.01
        """
        if len(telnet_node_id) == 6:
            return f"{telnet_node_id[:2]}.{telnet_node_id[2:4]}.{telnet_node_id[4:6]}"
        return telnet_node_id
    
    def _denormalize_node_id(self, http_node_id: str) -> str:
        """Convert HTTP API node ID format to telnet format.
        
        HTTP: 13.2A.01 -> Telnet: 132A01
        """
        return http_node_id.replace(".", "")

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get all available shade devices."""
        try:
            # Get list of device IDs
            device_ids = await self._send_request("sdn.status.ping", [{"targetID": "*"}])
            
            if not isinstance(device_ids, list):
                _LOGGER.error("Invalid response from sdn.status.ping: %s", device_ids)
                return []
            
            devices = []
            for device_id in device_ids:
                try:
                    # Get device info
                    info = await self._send_request("sdn.status.info", [{"targetID": device_id}])
                    if info and isinstance(info, dict):
                        # Normalize node ID to match HTTP API format
                        normalized_node_id = self._normalize_node_id(device_id)
                        devices.append({
                            "NODE": normalized_node_id,
                            "LABEL": info.get("name", f"Device {device_id}"),
                            "TYPE": info.get("type", "Unknown")
                        })
                except Exception as err:
                    _LOGGER.warning("Failed to get info for device %s: %s", device_id, err)
            
            return devices
            
        except Exception as err:
            _LOGGER.error("Failed to get devices: %s", err)
            return []

    async def get_device_info(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific device."""
        try:
            # Convert HTTP API node ID format to telnet format for requests
            telnet_node_id = self._denormalize_node_id(node_id)
            
            # Get device info and position
            info_task = self._send_request("sdn.status.info", [{"targetID": telnet_node_id}])
            position_task = self._send_request("sdn.status.position", [{"targetID": telnet_node_id}])
            
            info, position = await asyncio.gather(info_task, position_task, return_exceptions=True)
            
            if isinstance(info, Exception):
                _LOGGER.error("Failed to get device info for %s: %s", node_id, info)
                return None
            
            if isinstance(position, Exception):
                _LOGGER.warning("Failed to get position for %s: %s", node_id, position)
                position = 0
            
            if not isinstance(info, dict):
                _LOGGER.error("Invalid device info response for %s: %s", node_id, info)
                return None
            
            # Telnet API returns inverted position (100% = closed, 0% = open)
            # Convert to Home Assistant convention (100% = open, 0% = closed)
            position_value = position if isinstance(position, (int, float)) else 0
            ha_position = 100 - position_value  # Invert the position
            
            # The telnet protocol doesn't provide device limits, so we'll use percentage format
            # The coordinator will handle the position calculation properly
            position_str = f"0 ({ha_position} %)"  # Raw value not available from telnet API
            
            return {
                "LABEL": info.get("name", f"Device {node_id}"),
                "TYPE": info.get("type", "Unknown"),
                "POSITION": position_str,
                "LOCK": "UNLOCKED",  # Telnet protocol doesn't provide this
                "DIRECTION": "STANDARD",  # Default, could be made configurable
                "LIMITS UP": "0",      # Telnet protocol doesn't provide actual limits
                "LIMITS DOWN": "100",  # Use percentage range since telnet works in percentages
                "SERIAL NUMBER": node_id,  # Use node_id as serial
            }
            
        except Exception as err:
            _LOGGER.error("Failed to get device info for %s: %s", node_id, err)
            return None

    async def set_position(self, node_id: str, position: int) -> bool:
        """Set the position of a shade (0-100)."""
        if not 0 <= position <= 100:
            _LOGGER.error("Invalid position %s for device %s", position, node_id)
            return False
        
        try:
            # Convert HTTP API node ID format to telnet format for requests
            telnet_node_id = self._denormalize_node_id(node_id)
            
            # Telnet API expects inverted position (100% = closed, 0% = open)
            # Convert from Home Assistant convention (100% = open, 0% = closed)
            telnet_position = 100 - position
            
            _LOGGER.debug("Setting position for %s: HA %s%% -> telnet %s%%", 
                         node_id, position, telnet_position)
            
            # Send move command with inverted position
            result = await self._send_request(
                "sdn.move.to",
                [{
                    "targetID": telnet_node_id,
                    "position": telnet_position,
                    "type": "percent",
                    "seq": self._request_id  # Use current request ID as sequence
                }]
            )
            
            success = result is True or result == "true"
            if not success:
                _LOGGER.error("Failed to set position for %s: response was %s", node_id, result)
            return success
            
        except Exception as err:
            _LOGGER.error("Failed to set position for %s: %s", node_id, err)
            return False

    async def move_up(self, node_id: str) -> bool:
        """Move the shade up."""
        try:
            # Convert HTTP API node ID format to telnet format for requests
            telnet_node_id = self._denormalize_node_id(node_id)
            
            _LOGGER.debug("Moving shade %s up", node_id)
            
            # Send move up command
            result = await self._send_request(
                "sdn.move.up",
                [{
                    "targetID": telnet_node_id,
                    "seq": self._request_id  # Use current request ID as sequence
                }]
            )
            
            success = result is True or result == "true"
            if not success:
                _LOGGER.error("Failed to move %s up: response was %s", node_id, result)
            return success
            
        except Exception as err:
            _LOGGER.error("Failed to move %s up: %s", node_id, err)
            return False

    async def move_down(self, node_id: str) -> bool:
        """Move the shade down."""
        try:
            # Convert HTTP API node ID format to telnet format for requests
            telnet_node_id = self._denormalize_node_id(node_id)
            
            _LOGGER.debug("Moving shade %s down", node_id)
            
            # Send move down command
            result = await self._send_request(
                "sdn.move.down",
                [{
                    "targetID": telnet_node_id,
                    "seq": self._request_id  # Use current request ID as sequence
                }]
            )
            
            success = result is True or result == "true"
            if not success:
                _LOGGER.error("Failed to move %s down: response was %s", node_id, result)
            return success
            
        except Exception as err:
            _LOGGER.error("Failed to move %s down: %s", node_id, err)
            return False

    async def move_stop(self, node_id: str) -> bool:
        """Stop the shade movement."""
        try:
            # Convert HTTP API node ID format to telnet format for requests
            telnet_node_id = self._denormalize_node_id(node_id)
            
            _LOGGER.debug("Stopping shade %s movement", node_id)
            
            # Send move stop command
            result = await self._send_request(
                "sdn.move.stop",
                [{
                    "targetID": telnet_node_id,
                    "seq": self._request_id  # Use current request ID as sequence
                }]
            )
            
            success = result is True or result == "true"
            if not success:
                _LOGGER.error("Failed to stop %s: response was %s", node_id, result)
            return success
            
        except Exception as err:
            _LOGGER.error("Failed to stop %s: %s", node_id, err)
            return False

    async def set_position_raw(self, node_id: str, raw_position: int) -> bool:
        """Set the raw position of a shade using actual device limits."""
        try:
            # Get device info to determine actual limits
            device_info = await self.get_device_info(node_id)
            if not device_info:
                _LOGGER.error("Could not get device info for %s to determine limits", node_id)
                return False
            
            # Parse limits from device info
            try:
                limits_up = int(device_info.get("LIMITS UP", "0"))
                limits_down = int(device_info.get("LIMITS DOWN", "100"))
            except (ValueError, TypeError):
                _LOGGER.error("Invalid limits for device %s: up=%s, down=%s", 
                             node_id, device_info.get("LIMITS UP"), device_info.get("LIMITS DOWN"))
                return False
            
            # Calculate percentage based on actual device limits
            if limits_down <= limits_up:
                _LOGGER.error("Invalid limits for device %s: up=%s >= down=%s", 
                             node_id, limits_up, limits_down)
                return False
            
            # Clamp raw position to device limits
            clamped_position = max(limits_up, min(limits_down, raw_position))
            
            # Convert to percentage
            position_range = limits_down - limits_up
            relative_position = clamped_position - limits_up
            percentage = int((relative_position / position_range) * 100)
            
            _LOGGER.debug("Device %s: raw_position=%s, limits=[%s,%s], percentage=%s", 
                         node_id, raw_position, limits_up, limits_down, percentage)
            
            return await self.set_position(node_id, percentage)
            
        except Exception as err:
            _LOGGER.error("Failed to set raw position for %s: %s", node_id, err)
            return False

    async def close(self) -> None:
        """Close the telnet connection."""
        await self._disconnect()


class TelnetSomfyUAIClient:
    """Client for communicating with Somfy UAI+ controller via telnet protocol."""

    def __init__(self, host: str, port: int = 23, username: str = "Telnet 1", password: str = "Password 1") -> None:
        """Initialize the telnet client."""
        self._manager = TelnetConnectionManager(host, port, username, password)

    async def test_connection(self) -> bool:
        """Test connection to the controller."""
        return await self._manager.test_connection()

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get all available shade devices."""
        return await self._manager.get_devices()

    async def get_device_info(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific device."""
        return await self._manager.get_device_info(node_id)

    async def set_position(self, node_id: str, position: int) -> bool:
        """Set the position of a shade (0-100)."""
        return await self._manager.set_position(node_id, position)

    async def set_position_raw(self, node_id: str, raw_position: int) -> bool:
        """Set the raw position of a shade using actual device limits."""
        return await self._manager.set_position_raw(node_id, raw_position)

    async def move_up(self, node_id: str) -> bool:
        """Move the shade up."""
        return await self._manager.move_up(node_id)

    async def move_down(self, node_id: str) -> bool:
        """Move the shade down."""
        return await self._manager.move_down(node_id)

    async def move_stop(self, node_id: str) -> bool:
        """Stop the shade movement."""
        return await self._manager.move_stop(node_id)

    async def close(self) -> None:
        """Close the telnet connection."""
        # Don't close the shared connection, just disconnect this client
        pass