"""Constants for the Somfy UAI+ integration."""

DOMAIN = "somfy_uai_plus"

# Configuration keys (use homeassistant.const for standard keys: CONF_HOST, CONF_USERNAME, CONF_PASSWORD)
CONF_SCAN_INTERVAL = "scan_interval"

# Default values
DEFAULT_SCAN_INTERVAL = 5  # seconds - frequent polling for movement detection
DEFAULT_PORT = 23
DEFAULT_USERNAME = "Telnet 1"
DEFAULT_PASSWORD = "Password 1"

# Device information
MANUFACTURER = "Somfy"
MODEL = "UAI+"

# State tracking thresholds
POSITION_TOLERANCE = 2  # Consider position reached if within this percentage
CONSECUTIVE_STABLE_COUNT = 2  # Number of same positions to consider movement stopped
