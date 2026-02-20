"""Data update coordinator for Somfy UAI+."""
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any

from homeassistant.components.persistent_notification import async_create, async_dismiss
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONSECUTIVE_STABLE_COUNT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    NOTIFICATION_ID_DEGRADED,
)
from .somfy_api import ShadeInfo, SomfyUAIPlusAPI

_LOGGER = logging.getLogger(__name__)


class MovementState(Enum):
    """Shade movement state."""

    IDLE = "idle"
    OPENING = "opening"
    CLOSING = "closing"


@dataclass
class ShadeState:
    """State tracking for a single shade."""

    node_id: str
    name: str
    device_type: str
    position: int  # Current position (0=closed, 100=open)
    target_position: int | None = None  # Target position when moving
    movement_state: MovementState = MovementState.IDLE
    last_positions: list[int] = field(default_factory=list)  # Recent position history

    def update_position(self, new_position: int) -> None:
        """Update position and track history for movement detection."""
        self.last_positions.append(new_position)
        # Keep only the last N positions
        if len(self.last_positions) > CONSECUTIVE_STABLE_COUNT + 1:
            self.last_positions = self.last_positions[-(CONSECUTIVE_STABLE_COUNT + 1) :]

        self.position = new_position

    def check_if_stopped(self) -> bool:
        """Check if shade has stopped moving based on position history.

        Returns True if the last N positions are the same, indicating
        the shade has stopped moving.
        """
        if len(self.last_positions) < CONSECUTIVE_STABLE_COUNT:
            return False

        recent = self.last_positions[-CONSECUTIVE_STABLE_COUNT:]
        return len(set(recent)) == 1

    def is_at_target(self) -> bool:
        """Check if shade has reached its target position."""
        if self.target_position is None:
            return True
        return self.position == self.target_position


@dataclass
class CoordinatorData:
    """Data returned by the coordinator."""

    shades: dict[str, ShadeState] = field(default_factory=dict)


class SomfyUAIPlusCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Coordinator to manage Somfy UAI+ shade data and state."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SomfyUAIPlusAPI,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self._shade_states: dict[str, ShadeState] = {}
        self._device_degraded = False

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch data from API and update shade states."""
        try:
            # Get all shade IDs (sends sdn.status.ping)
            shade_ids = await self.api.get_shade_ids()

            if not shade_ids:
                if self._shade_states:
                    # Previously had shades but ping returned nothing — device
                    # is likely in a degraded state (ping timed out or failed).
                    self._set_device_degraded()
                    raise UpdateFailed(
                        f"Somfy UAI+ at {self.api.host} is not responding "
                        "to status ping"
                    )
                _LOGGER.warning("No shades found")
                return CoordinatorData(shades=self._shade_states)

            # Device is responding — clear any degraded notification
            self._clear_device_degraded()

            # Update each shade
            for node_id in shade_ids:
                await self._update_shade(node_id)

            return CoordinatorData(shades=self._shade_states)

        except UpdateFailed:
            raise
        except Exception as err:
            self._set_device_degraded()
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    def _set_device_degraded(self) -> None:
        """Create a persistent notification indicating the device is degraded."""
        if self._device_degraded:
            return
        self._device_degraded = True
        _LOGGER.warning(
            "Somfy UAI+ at %s is not responding — device may be in a degraded "
            "state and might need to be restarted",
            self.api.host,
        )
        async_create(
            self.hass,
            (
                f"The Somfy UAI+ controller at **{self.api.host}** is not "
                "responding to status checks. The device may be in a degraded "
                "state and might need to be restarted.\n\n"
                "Check **Settings → System → Logs** and filter for "
                "`somfy_uai_plus` for more details."
            ),
            title="Somfy UAI+ Not Responding",
            notification_id=NOTIFICATION_ID_DEGRADED,
        )

    def _clear_device_degraded(self) -> None:
        """Dismiss the degraded notification if the device has recovered."""
        if not self._device_degraded:
            return
        self._device_degraded = False
        _LOGGER.info("Somfy UAI+ at %s has recovered", self.api.host)
        async_dismiss(self.hass, NOTIFICATION_ID_DEGRADED)

    async def _update_shade(self, node_id: str) -> None:
        """Update state for a single shade."""
        # Get current position
        position = await self.api.get_shade_position(node_id)
        if position is None:
            _LOGGER.warning("Failed to get position for shade %s", node_id)
            return

        if node_id in self._shade_states:
            # Update existing shade
            shade = self._shade_states[node_id]
            shade.update_position(position)

            # Check if shade has stopped moving
            if shade.movement_state != MovementState.IDLE:
                if shade.check_if_stopped() or shade.is_at_target():
                    _LOGGER.debug(
                        "Shade %s stopped moving at position %s", node_id, position
                    )
                    shade.movement_state = MovementState.IDLE
                    shade.target_position = None
        else:
            # New shade - get info and create state
            info = await self.api.get_shade_info(node_id)
            if info:
                shade = ShadeState(
                    node_id=node_id,
                    name=info.name,
                    device_type=info.device_type,
                    position=position,
                )
                shade.last_positions.append(position)
                self._shade_states[node_id] = shade
            else:
                _LOGGER.warning("Failed to get info for shade %s", node_id)

    def get_shade(self, node_id: str) -> ShadeState | None:
        """Get shade state by node ID."""
        return self._shade_states.get(node_id)

    def set_shade_moving(
        self, node_id: str, target_position: int, opening: bool
    ) -> None:
        """Mark a shade as moving toward a target position.

        This should be called when a movement command is sent to properly
        track the movement state until the shade reaches its target.

        Args:
            node_id: The shade's node ID
            target_position: The target position (0-100)
            opening: True if opening (position increasing), False if closing
        """
        if node_id in self._shade_states:
            shade = self._shade_states[node_id]
            shade.target_position = target_position
            shade.movement_state = (
                MovementState.OPENING if opening else MovementState.CLOSING
            )
            # Clear position history when starting a new movement
            shade.last_positions.clear()
            _LOGGER.debug(
                "Shade %s started %s to position %s",
                node_id,
                shade.movement_state.value,
                target_position,
            )

    def set_shade_stopped(self, node_id: str) -> None:
        """Mark a shade as stopped (e.g., after stop command).

        Sets the internal position to the target position (optimistic),
        then the next poll will update it to the real position.

        Args:
            node_id: The shade's node ID
        """
        if node_id in self._shade_states:
            shade = self._shade_states[node_id]
            # Set position to target (optimistic) - next poll will get real position
            if shade.target_position is not None:
                shade.position = shade.target_position
            shade.movement_state = MovementState.IDLE
            shade.target_position = None
            _LOGGER.debug("Shade %s marked as stopped at position %s", node_id, shade.position)

    async def async_shutdown(self) -> None:
        """Disconnect from the API when shutting down."""
        await self.api.disconnect()
