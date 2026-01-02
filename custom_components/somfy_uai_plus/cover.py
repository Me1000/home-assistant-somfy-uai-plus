"""Cover platform for Somfy UAI+ integration."""
import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import MovementState, ShadeState, SomfyUAIPlusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Somfy UAI+ cover entities."""
    coordinator: SomfyUAIPlusCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Wait for initial data
    await coordinator.async_config_entry_first_refresh()

    # Create cover entities for each shade
    entities = []
    for node_id, shade_state in coordinator.data.shades.items():
        entities.append(SomfyUAIPlusCover(coordinator, node_id, shade_state))

    async_add_entities(entities)


class SomfyUAIPlusCover(CoordinatorEntity[SomfyUAIPlusCoordinator], CoverEntity):
    """Representation of a Somfy UAI+ shade."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.SHADE
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        coordinator: SomfyUAIPlusCoordinator,
        node_id: str,
        shade_state: ShadeState,
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._node_id = node_id
        self._attr_unique_id = f"{DOMAIN}_{node_id}"
        # Set name to None so entity uses the device name
        # This allows users to rename via the device and have the entity follow
        self._attr_name = None
        # Store the initial name for device_info
        self._initial_name = shade_state.name

    @property
    def _shade(self) -> ShadeState | None:
        """Get the current shade state from the coordinator."""
        return self.coordinator.get_shade(self._node_id)

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        shade = self._shade
        return {
            "identifiers": {(DOMAIN, self._node_id)},
            "name": shade.name if shade else self._initial_name,
            "manufacturer": MANUFACTURER,
            "model": shade.device_type if shade else MODEL,
        }

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover (0=closed, 100=open).

        While the shade is moving, returns the target position.
        Once movement stops, returns the actual position.
        """
        shade = self._shade
        if not shade:
            return None

        # Return target position while moving, actual position when idle
        if shade.movement_state != MovementState.IDLE and shade.target_position is not None:
            return shade.target_position

        return shade.position

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        position = self.current_cover_position
        return position == 0 if position is not None else None

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        shade = self._shade
        return shade.movement_state == MovementState.CLOSING if shade else False

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        shade = self._shade
        return shade.movement_state == MovementState.OPENING if shade else False

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        _LOGGER.debug("Opening shade %s", self._node_id)

        # Mark as moving before sending command
        self.coordinator.set_shade_moving(
            self._node_id, target_position=100, opening=True
        )
        self.async_write_ha_state()

        # Send command
        await self.coordinator.api.open_shade(self._node_id)

        # Request immediate refresh to start tracking
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        _LOGGER.debug("Closing shade %s", self._node_id)

        # Mark as moving before sending command
        self.coordinator.set_shade_moving(
            self._node_id, target_position=0, opening=False
        )
        self.async_write_ha_state()

        # Send command
        await self.coordinator.api.close_shade(self._node_id)

        # Request immediate refresh to start tracking
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs.get("position", 0)
        _LOGGER.debug("Setting shade %s to position %s", self._node_id, position)

        shade = self._shade
        current_position = shade.position if shade else 0
        opening = position > current_position

        # Mark as moving before sending command
        self.coordinator.set_shade_moving(
            self._node_id, target_position=position, opening=opening
        )
        self.async_write_ha_state()

        # Send command
        await self.coordinator.api.set_position(self._node_id, position)

        # Request immediate refresh to start tracking
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        _LOGGER.debug("Stopping shade %s", self._node_id)

        # Send stop command
        await self.coordinator.api.stop_shade(self._node_id)

        # Mark as stopped
        self.coordinator.set_shade_stopped(self._node_id)
        self.async_write_ha_state()

        # Request immediate refresh to get current position
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        shade = self._shade
        if not shade:
            return {}

        attrs = {
            "node_id": self._node_id,
            "device_type": shade.device_type,
        }

        if shade.target_position is not None:
            attrs["target_position"] = shade.target_position

        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # The coordinator handles movement state tracking internally
        # Just update our state based on coordinator data
        super()._handle_coordinator_update()
