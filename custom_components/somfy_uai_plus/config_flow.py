"""Config flow for Somfy UAI+ integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import ipaddress

from .api import SomfyUAIClient, TelnetSomfyUAIClient
from .const import (
    DOMAIN, 
    CONF_PROTOCOL, 
    CONF_SCAN_INTERVAL, 
    DEFAULT_SCAN_INTERVAL,
    PROTOCOL_HTTP,
    PROTOCOL_TELNET,
    DEFAULT_PROTOCOL
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In([PROTOCOL_HTTP, PROTOCOL_TELNET]),
})


async def validate_input(hass: HomeAssistant, data: dict) -> Dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    protocol = data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
    
    # Validate IP address format
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise InvalidHost("Invalid IP address format")
    
    # Test connection based on protocol
    if protocol == PROTOCOL_TELNET:
        client = TelnetSomfyUAIClient(host)
    else:
        session = async_get_clientsession(hass)
        client = SomfyUAIClient(host, session)
    
    try:
        if not await client.test_connection():
            raise CannotConnect("Cannot connect to Somfy UAI+ controller")
        
        # Get device count for info
        devices = await client.get_devices()
        
        return {
            "title": f"Somfy UAI+ ({host}) - {protocol.upper()}",
            "host": host,
            "protocol": protocol,
            "device_count": len(devices)
        }
    finally:
        # Clean up telnet connection
        if hasattr(client, 'close'):
            await client.close()


class SomfyUAIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Somfy UAI+."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return SomfyUAIOptionsFlow(config_entry)

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        
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
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidHost(Exception):
    """Error to indicate invalid host format."""


class SomfyUAIOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Somfy UAI+."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Manage the options."""
        errors = {}
        
        if user_input is not None:
            try:
                # Validate the new IP address
                info = await validate_input(self.hass, user_input)
                
                # Update the config entry data and options
                new_data = dict(self.config_entry.data)
                new_data[CONF_HOST] = user_input[CONF_HOST]
                if CONF_PROTOCOL in user_input:
                    new_data[CONF_PROTOCOL] = user_input[CONF_PROTOCOL]
                
                new_options = dict(self.config_entry.options)
                if CONF_SCAN_INTERVAL in user_input:
                    new_options[CONF_SCAN_INTERVAL] = user_input[CONF_SCAN_INTERVAL]
                
                self.hass.config_entries.async_update_entry(
                    self.config_entry, 
                    data=new_data,
                    options=new_options,
                    title=info["title"]
                )
                
                # Trigger reload to use new settings
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                
                return self.async_create_entry(title="", data={})
                
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidHost:
                errors["base"] = "invalid_host"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Show form with current values as defaults
        current_host = self.config_entry.data.get(CONF_HOST, "")
        current_protocol = self.config_entry.data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
        current_scan_interval = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=current_host): str,
            vol.Optional(CONF_PROTOCOL, default=current_protocol): vol.In([PROTOCOL_HTTP, PROTOCOL_TELNET]),
            vol.Optional(CONF_SCAN_INTERVAL, default=current_scan_interval): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=300)
            ),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={"current_host": current_host},
        )