# Somfy UAI+ Home Assistant Integration

A custom Home Assistant integration for controlling Somfy motorized shades, blinds, and other window coverings through the Somfy UAI+ (Universal Automation Interface) controller.

Almost all of the code in this repo was written by Claude Code, I make no claims about it's quality but it works to control my blinds in my home.

## Features

- **Full shade control**: Open, close, set position, and stop shades
- **Multiple protocols**: Supports both HTTP and Telnet communication
- **Device discovery**: Automatically discovers all connected Somfy devices
- **Position tracking**: Real-time position updates with optimistic UI feedback
- **Direction support**: Handles both standard and reversed motor directions
- **Local control**: Communicates directly with your UAI+ controller (no cloud required)

## Supported Devices

This integration works with Somfy devices connected to a UAI+ controller, including:
- Motorized shades and blinds
- Awnings and exterior shades
- Skylights and roof windows
- Any Somfy RTS or io-enabled window covering

## Installation

### Via HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=me1000&repository=home-assistant-somfy-uai-plus&category=integration)

1. **Add custom repository**:
   - Open HACS in Home Assistant
   - Go to "Integrations" tab
   - Click the three dots menu (⋮) in the top right
   - Select "Custom repositories"
   - Add repository URL: `https://github.com/me1000/home-assistant-somfy-uai-plus`
   - Select category: "Integration"
   - Click "Add"

2. **Install the integration**:
   - Search for "Somfy UAI+" in HACS
   - Click "Download"
   - Restart Home Assistant

3. **Configure the integration**:
   - Go to Settings → Devices & Services
   - Click "Add Integration"
   - Search for "Somfy UAI+"
   - Enter your UAI+ controller's IP address
   - Choose communication protocol (HTTP or Telnet)
   - Configure scan interval (default: 30 seconds)

### Manual Installation

1. Copy the `custom_components/somfy_uai_plus` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration through the UI as described above

## Configuration

### Basic Setup

The integration requires minimal configuration:

- **Host**: IP address of your Somfy UAI+ controller
- **Protocol**: Choose between HTTP (default) or Telnet
- **Scan Interval**: How often to poll for device updates (default: 30 seconds)

### Protocol Selection

- **HTTP**: Basic functionality, but has known issues with large position values
- **Telnet**: **Recommended** - More reliable and more accurate position reporting

## Usage

Once configured, your Somfy devices will appear as cover entities in Home Assistant with the following features:

### Cover Controls
- **Open/Close**: Fully open or close the shade
- **Set Position**: Move to any position between 0-100%
- **Stop**: Stop the shade at current position

### Device Information
- Device name and model
- Serial number
- Current position
- Direction (standard or reversed)
- Lock status
- Position limits

## Device Information

Each shade provides additional information:

- **Device Type**: Somfy motor model (e.g., "Sonesse 50DC")
- **Lock Status**: Whether the shade is locked
- **Direction**: Motor direction setting
- **Limits**: Upper and lower position limits
- **Node ID**: Unique device identifier

## Troubleshooting

### Common Issues

**Shades wont move to a specific position**:
- Try switching to the Telnet protocol. The HTTP API that Somfy provides is buggy.

## Protocol Information

This integration supports two communication protocols with the UAI+ controller:

### HTTP Protocol
- **Source**: Reverse engineered from the Somfy UAI+ web dashboard
- **Stability**: Generally stable but has known issues
- **Known Issues**: Buggy with certain large position values (this is also broken in the official web UI)
- **Recommendation**: Use for basic functionality, but Telnet is preferred for reliability

### Telnet Protocol (Recommended) 
- **Source**: Reverse engineered from network traffic analysis
- **Stability**: More reliable than HTTP, especially for position commands
- **Performance**: More accurate position reporting
- **Recommendation**: **Preferred protocol** for best reliability

I reverse engineered this protocol by setting up a proxy server between a Crestron Home device with the Somfy UAI+ driver
and the UAI+ and just inspected the messages. The work and protocol documentation can be found in 
the `reverse-engineered-protocols/` directory of this repository.

## Development

### API Client

The integration includes a comprehensive API client (`api.py`) that handles:

- Connection testing
- Device discovery
- Position control
- Error handling and timeouts

### Data Coordinator

Uses Home Assistant's `DataUpdateCoordinator` for:

- Efficient polling (30-second intervals)
- Automatic error recovery
- Coordinated updates across all entities

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
