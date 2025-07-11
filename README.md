# Somfy UAI+ Home Assistant Integration

A Home Assistant custom component for controlling Somfy shades through the UAI+ controller.

## Features

- **Easy Setup**: Simple IP address configuration through Home Assistant UI
- **Auto-Discovery**: Automatically discovers all connected shades
- **Full Control**: Open, close, and set precise positions (0-100%)
- **Room Assignment**: Assign shades to specific rooms in Home Assistant
- **Real-time Updates**: Automatic polling for position updates
- **Device Information**: Shows device type, lock status, and limits

## Installation

### Method 1: HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the "+" button and search for "Somfy UAI+"
4. Install the integration
5. Restart Home Assistant

### Method 2: Manual Installation

1. Download the latest release from [GitHub](https://github.com/me1000/somfy-uai-plus)
2. Extract the `somfy_uai_plus` folder to your `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Somfy UAI+"
4. Enter your UAI+ controller IP address (e.g., `10.1.1.50`)
5. Click **Submit**

The integration will automatically discover all connected shades and create cover entities for each one.

## Usage

Once configured, you'll have cover entities for each shade that support:

- **Open/Close**: Basic up/down controls
- **Position**: Set exact position (0-100%)
- **Stop**: Stop movement (sends current position command)

### Automation Example

```yaml
# Open bedroom shades at sunrise
automation:
  - alias: "Open bedroom shades at sunrise"
    trigger:
      platform: sun
      event: sunrise
    action:
      service: cover.open_cover
      target:
        entity_id: cover.bedroom_2
```

## API Endpoints

The integration uses these UAI+ controller endpoints:

- `GET /somfy_devices.json` - List all devices
- `GET /somfy_device.json?{NODE_ID}` - Get device details
- `GET /somfy.cgi?{NODE_ID}:POSITION={VALUE}` - Control position

## Device Information

Each shade provides additional information:

- **Device Type**: Somfy motor model (e.g., "Sonesse 50DC")
- **Lock Status**: Whether the shade is locked
- **Direction**: Motor direction setting
- **Limits**: Upper and lower position limits
- **Node ID**: Unique device identifier

## Troubleshooting

### Connection Issues

- Verify the IP address is correct
- Ensure the UAI+ controller is on the same network
- Check firewall settings

### Shades Not Responding

- Verify shades are properly paired with the controller
- Check controller web interface directly
- Restart the Home Assistant integration

### Position Accuracy

- The integration converts between percentage (0-100%) and device units
- Some shades may have slightly different limit ranges
- Calibrate limits through the Somfy controller if needed

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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For issues and support:

- [GitHub Issues](https://github.com/me1000/somfy-uai-plus/issues)
- [Home Assistant Community](https://community.home-assistant.io/)