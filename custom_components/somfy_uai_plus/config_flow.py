"""Config flow for Somfy UAI+ integration."""
import ipaddress
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
)
from .somfy_api import SomfyUAIPlusAPI

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidHost(Exception):
    """Error to indicate invalid host format."""


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input and test connection."""
    host = data[CONF_HOST]
    username = data.get(CONF_USERNAME, DEFAULT_USERNAME)
    password = data.get(CONF_PASSWORD, DEFAULT_PASSWORD)

    # Validate IP address format
    try:
        ipaddress.ip_address(host)
    except ValueError as err:
        raise InvalidHost("Invalid IP address format") from err

    # Test connection
    api = SomfyUAIPlusAPI(host, username=username, password=password)

    try:
        if not await api.test_connection():
            raise CannotConnect("Cannot connect to Somfy UAI+ controller")

        # Get device count for confirmation
        shade_ids = await api.get_shade_ids()

        return {
            "title": f"Somfy UAI+ ({host})",
            "device_count": len(shade_ids),
        }
    finally:
        await api.disconnect()


class SomfyUAIPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Somfy UAI+."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return SomfyUAIPlusOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                # Check if already configured
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidHost:
                errors["base"] = "invalid_host"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                    vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
                }
            ),
            errors=errors,
        )


class SomfyUAIPlusOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Somfy UAI+."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if connection settings changed
            new_host = user_input.get(CONF_HOST)
            new_username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
            new_password = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)

            current_host = self.config_entry.data.get(CONF_HOST)
            current_username = self.config_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME)
            current_password = self.config_entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD)

            connection_changed = (
                new_host != current_host
                or new_username != current_username
                or new_password != current_password
            )

            if connection_changed:
                try:
                    await validate_input(
                        self.hass,
                        {
                            CONF_HOST: new_host,
                            CONF_USERNAME: new_username,
                            CONF_PASSWORD: new_password,
                        },
                    )

                    # Update config entry data
                    new_data = dict(self.config_entry.data)
                    new_data[CONF_HOST] = new_host
                    new_data[CONF_USERNAME] = new_username
                    new_data[CONF_PASSWORD] = new_password

                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=new_data,
                        title=f"Somfy UAI+ ({new_host})",
                    )
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidHost:
                    errors["base"] = "invalid_host"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"

            if not errors:
                # Save options
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    },
                )

        # Show form with current values
        current_host = self.config_entry.data.get(CONF_HOST, "")
        current_username = self.config_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME)
        current_password = self.config_entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD)
        current_scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=current_host): str,
                    vol.Optional(CONF_USERNAME, default=current_username): str,
                    vol.Optional(CONF_PASSWORD, default=current_password): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=current_scan_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                }
            ),
            errors=errors,
        )
