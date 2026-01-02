"""Standalone API wrapper for Somfy UAI+ controller via Telnet protocol.

This module provides a clean, async interface to communicate with Somfy UAI+
controllers using the JSON-RPC over Telnet protocol.
"""
import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)

# Default connection settings
DEFAULT_PORT = 23
DEFAULT_USERNAME = "Telnet 1"
DEFAULT_PASSWORD = "Password 1"
DEFAULT_TIMEOUT = 10.0
REQUEST_DELAY = 0.1  # Delay between requests to avoid overwhelming the device


class ConnectionState(Enum):
    """Connection state enum."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


@dataclass
class ShadeInfo:
    """Information about a shade device."""

    node_id: str
    name: str
    device_type: str


class SomfyConnectionError(Exception):
    """Raised when connection to the controller fails."""


class SomfyCommandError(Exception):
    """Raised when a command fails."""


class SomfyUAIPlusAPI:
    """Async API client for Somfy UAI+ controller.

    This class manages the Telnet connection and provides methods to:
    - Discover and enumerate shades
    - Get shade positions
    - Control shade movement (open, close, stop, set position)

    All operations are queued to prevent out-of-order execution.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        username: str = DEFAULT_USERNAME,
        password: str = DEFAULT_PASSWORD,
    ) -> None:
        """Initialize the API client.

        Args:
            host: IP address or hostname of the Somfy UAI+ controller
            port: Telnet port (default: 23)
            username: Telnet username (default: "Telnet 1")
            password: Telnet password (default: "Password 1")
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        # Connection state
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._state = ConnectionState.DISCONNECTED

        # Request handling
        self._request_id = 8900
        self._sequence_number = 0
        self._pending_requests: dict[int, asyncio.Future] = {}

        # Background tasks
        self._read_task: Optional[asyncio.Task] = None
        self._queue_task: Optional[asyncio.Task] = None

        # Message queue for sequential processing
        self._request_queue: asyncio.Queue = asyncio.Queue()

        # Lock for connection operations
        self._connect_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the controller."""
        return self._state == ConnectionState.CONNECTED

    async def connect(self) -> bool:
        """Connect to the Somfy UAI+ controller.

        Performs the Telnet handshake:
        1. Connect to host:port
        2. Receive "User:" prompt
        3. Send username
        4. Receive "Password:" prompt
        5. Send password
        6. Receive "Connected:" confirmation

        Returns:
            True if connection successful, False otherwise
        """
        async with self._connect_lock:
            if self._state == ConnectionState.CONNECTED:
                return True

            if self._state == ConnectionState.CONNECTING:
                _LOGGER.debug("Connection already in progress")
                return False

            self._state = ConnectionState.CONNECTING

            try:
                _LOGGER.debug("Connecting to %s:%s", self.host, self.port)

                # Open connection
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=DEFAULT_TIMEOUT,
                )

                # Perform handshake
                await self._perform_handshake()

                # Start background tasks
                self._read_task = asyncio.create_task(self._read_responses())
                self._queue_task = asyncio.create_task(self._process_queue())

                self._state = ConnectionState.CONNECTED
                _LOGGER.info("Connected to Somfy UAI+ at %s:%s", self.host, self.port)
                return True

            except (OSError, asyncio.TimeoutError, ConnectionError) as err:
                _LOGGER.error("Failed to connect: %s", err)
                await self._cleanup_connection()
                return False

    async def _perform_handshake(self) -> None:
        """Perform the Telnet authentication handshake."""
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

        _LOGGER.debug("Handshake completed successfully")

    async def _read_until(self, delimiter: bytes) -> bytes:
        """Read data until delimiter is found."""
        data = b""
        while delimiter not in data:
            chunk = await asyncio.wait_for(
                self._reader.read(1024), timeout=DEFAULT_TIMEOUT
            )
            if not chunk:
                raise ConnectionError(
                    "Connection closed unexpectedly during handshake"
                )
            data += chunk
        return data

    async def disconnect(self) -> None:
        """Disconnect from the controller."""
        _LOGGER.debug("Disconnecting from %s", self.host)
        await self._cleanup_connection()

    async def _cleanup_connection(self) -> None:
        """Clean up connection resources."""
        self._state = ConnectionState.DISCONNECTED

        # Cancel background tasks
        for task in [self._read_task, self._queue_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._read_task = None
        self._queue_task = None

        # Close writer
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None

        self._reader = None

        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

    async def _read_responses(self) -> None:
        """Background task to read and dispatch JSON-RPC responses."""
        buffer = ""

        try:
            while self._state == ConnectionState.CONNECTED and self._reader:
                try:
                    data = await asyncio.wait_for(self._reader.read(1024), timeout=1.0)
                    if not data:
                        _LOGGER.warning("Connection closed by server")
                        break

                    buffer += data.decode("utf-8", errors="ignore")

                    # Process complete JSON objects (one per line)
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if line.startswith("{") and line.endswith("}"):
                            try:
                                response = json.loads(line)
                                await self._dispatch_response(response)
                            except json.JSONDecodeError as err:
                                _LOGGER.warning("Invalid JSON response: %s", err)

                except asyncio.TimeoutError:
                    continue
                except Exception as err:
                    _LOGGER.error("Error reading responses: %s", err)
                    break

        finally:
            if self._state == ConnectionState.CONNECTED:
                _LOGGER.warning("Response reader stopped unexpectedly")
                self._state = ConnectionState.DISCONNECTED

    async def _dispatch_response(self, response: dict[str, Any]) -> None:
        """Dispatch a JSON-RPC response to the waiting request."""
        request_id = response.get("id")

        if request_id and request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                if "result" in response:
                    future.set_result(response["result"])
                elif "error" in response:
                    future.set_exception(
                        SomfyCommandError(f"RPC error: {response['error']}")
                    )
                else:
                    future.set_exception(SomfyCommandError("Invalid response format"))
        else:
            # Unsolicited message (e.g., position update notification)
            if "method" in response:
                _LOGGER.debug("Received unsolicited message: %s", response)

    async def _process_queue(self) -> None:
        """Background task to process queued requests sequentially."""
        try:
            while self._state == ConnectionState.CONNECTED:
                try:
                    request_data = await asyncio.wait_for(
                        self._request_queue.get(), timeout=1.0
                    )

                    if self._state != ConnectionState.CONNECTED or not self._writer:
                        request_data["future"].set_exception(
                            SomfyConnectionError("Not connected")
                        )
                        continue

                    try:
                        # Send the request
                        request_json = json.dumps(request_data["request"]) + "\r\n"
                        self._writer.write(request_json.encode())
                        await self._writer.drain()

                        # Small delay between requests
                        await asyncio.sleep(REQUEST_DELAY)

                    except Exception as err:
                        request_data["future"].set_exception(err)

                except asyncio.TimeoutError:
                    continue

        except asyncio.CancelledError:
            # Reject remaining queued requests
            while not self._request_queue.empty():
                try:
                    request_data = self._request_queue.get_nowait()
                    request_data["future"].set_exception(
                        SomfyConnectionError("Connection closed")
                    )
                except asyncio.QueueEmpty:
                    break
            raise

    async def _send_request(self, method: str, params: list[dict[str, Any]]) -> Any:
        """Send a JSON-RPC request and wait for the response.

        Args:
            method: The JSON-RPC method name
            params: List of parameter dictionaries

        Returns:
            The result from the response

        Raises:
            SomfyConnectionError: If not connected
            SomfyCommandError: If the command fails
            asyncio.TimeoutError: If the request times out
        """
        if self._state != ConnectionState.CONNECTED:
            if not await self.connect():
                raise SomfyConnectionError("Failed to connect")

        self._request_id += 1
        request_id = self._request_id

        request = {"method": method, "params": params, "id": request_id}

        # Create future for the response
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[request_id] = future

        # Queue the request
        await self._request_queue.put({"request": request, "future": future})

        try:
            result = await asyncio.wait_for(future, timeout=DEFAULT_TIMEOUT)
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise asyncio.TimeoutError(f"Request {method} timed out")
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise

    def _get_next_sequence(self) -> int:
        """Get the next sequence number for move commands."""
        self._sequence_number += 1
        return self._sequence_number

    # ========== Public API Methods ==========

    async def test_connection(self) -> bool:
        """Test connection to the controller.

        Returns:
            True if connection is successful and controller responds
        """
        try:
            result = await self._send_request("sdn.status.ping", [{"targetID": "*"}])
            return isinstance(result, list)
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", err)
            return False

    async def get_shade_ids(self) -> list[str]:
        """Get all shade node IDs.

        Returns:
            List of shade node IDs (e.g., ["132A01", "1329FB"])
        """
        try:
            result = await self._send_request("sdn.status.ping", [{"targetID": "*"}])
            if isinstance(result, list):
                return result
            return []
        except Exception as err:
            _LOGGER.error("Failed to get shade IDs: %s", err)
            return []

    async def get_shade_info(self, node_id: str) -> Optional[ShadeInfo]:
        """Get information about a specific shade.

        Args:
            node_id: The shade's node ID

        Returns:
            ShadeInfo object or None if failed
        """
        try:
            result = await self._send_request(
                "sdn.status.info", [{"targetID": node_id}]
            )
            if isinstance(result, dict):
                return ShadeInfo(
                    node_id=node_id,
                    name=result.get("name", f"Shade {node_id}"),
                    device_type=result.get("type", "Unknown"),
                )
            return None
        except Exception as err:
            _LOGGER.error("Failed to get shade info for %s: %s", node_id, err)
            return None

    async def get_shade_position(self, node_id: str) -> Optional[int]:
        """Get the current position of a shade.

        The Somfy API returns position where:
        - 0 = fully open (shade up)
        - 100 = fully closed (shade down)

        This method inverts the value to match Home Assistant conventions:
        - 0 = fully closed
        - 100 = fully open

        Args:
            node_id: The shade's node ID

        Returns:
            Position (0-100) or None if failed
        """
        try:
            result = await self._send_request(
                "sdn.status.position", [{"targetID": node_id}]
            )
            if isinstance(result, (int, float)):
                # Invert: Somfy 0=open, HA 0=closed
                return 100 - int(result)
            return None
        except Exception as err:
            _LOGGER.error("Failed to get position for %s: %s", node_id, err)
            return None

    async def get_all_shades(self) -> list[tuple[ShadeInfo, int]]:
        """Get info and position for all shades.

        Returns:
            List of (ShadeInfo, position) tuples
        """
        shades = []
        node_ids = await self.get_shade_ids()

        for node_id in node_ids:
            info = await self.get_shade_info(node_id)
            if info:
                position = await self.get_shade_position(node_id)
                if position is not None:
                    shades.append((info, position))

        return shades

    async def set_position(self, node_id: str, position: int) -> bool:
        """Set the shade to a specific position.

        Args:
            node_id: The shade's node ID
            position: Target position (0=closed, 100=open) in HA convention

        Returns:
            True if command was accepted
        """
        if not 0 <= position <= 100:
            _LOGGER.error("Invalid position %s (must be 0-100)", position)
            return False

        try:
            # Invert position for Somfy API (0=open, 100=closed)
            somfy_position = 100 - position
            seq = self._get_next_sequence()

            result = await self._send_request(
                "sdn.move.to",
                [
                    {"targetID": node_id},
                    {"position": somfy_position},
                    {"type": "percent"},
                    {"seq": seq},
                ],
            )

            success = result is True
            if not success:
                _LOGGER.error("Failed to set position for %s: %s", node_id, result)
            return success

        except Exception as err:
            _LOGGER.error("Failed to set position for %s: %s", node_id, err)
            return False

    async def open_shade(self, node_id: str) -> bool:
        """Open a shade (move up).

        Args:
            node_id: The shade's node ID

        Returns:
            True if command was accepted
        """
        try:
            seq = self._get_next_sequence()
            result = await self._send_request(
                "sdn.move.up", [{"targetID": node_id}, {"seq": seq}]
            )
            return result is True
        except Exception as err:
            _LOGGER.error("Failed to open shade %s: %s", node_id, err)
            return False

    async def close_shade(self, node_id: str) -> bool:
        """Close a shade (move down).

        Args:
            node_id: The shade's node ID

        Returns:
            True if command was accepted
        """
        try:
            seq = self._get_next_sequence()
            result = await self._send_request(
                "sdn.move.down", [{"targetID": node_id}, {"seq": seq}]
            )
            return result is True
        except Exception as err:
            _LOGGER.error("Failed to close shade %s: %s", node_id, err)
            return False

    async def stop_shade(self, node_id: str) -> bool:
        """Stop a shade's movement.

        Args:
            node_id: The shade's node ID

        Returns:
            True if command was accepted
        """
        try:
            seq = self._get_next_sequence()
            result = await self._send_request(
                "sdn.move.stop", [{"targetID": node_id}, {"seq": seq}]
            )
            return result is True
        except Exception as err:
            _LOGGER.error("Failed to stop shade %s: %s", node_id, err)
            return False

    async def __aenter__(self) -> "SomfyUAIPlusAPI":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
