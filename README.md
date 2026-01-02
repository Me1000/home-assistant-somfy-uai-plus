# Somfy UAI+ Home Assistant Integration

A custom Home Assistant integration for controlling Somfy motorized shades through the Somfy UAI+ (Universal Automation Interface) controller.

This integration communicates directly with a Somfy UAI+ controller over your local network using the Telnet protocol, which was reverse engineered via a proxy that intercepted messages to and from a proprietary client. There's no reason for this protocol to not be published, so I've included all that in this repo.

> **Note**: This integration was largely written with Claude Code, so I make no guarantee about the quality of the code itself.

## Features

- **Shade control**: Open, close, stop, and set position (0-100%)
- **Automatic device discovery**: Finds all shades connected to your UAI+ controller
- **Movement state tracking**:  Reports when shades are opening, closing, or idle via internal state management (more below)
- **Position monitoring**: Polls shade positions
- **Local control**: Direct communication with your UAI+ controller over your LAN

## Supported Devices

This integration works with any Somfy motorized shade connected to a UAI+ controller.

## Requirements

- Somfy UAI+ controller accessible on your local network
- The UAI+ controller's IP address

## Installation

### Manual Installation

> **Note**: If you know how to get this repo installable via HACS please submit a PR with those instructions included.

1. Download or clone this repository

2. Copy the `custom_components/somfy_uai_plus` folder to your Home Assistant configuration directory:
   ```
   <config>/custom_components/somfy_uai_plus/
   ```

   Your directory structure should look like:
   ```
   homeassistant/
   ├── configuration.yaml
   └── custom_components/
       └── somfy_uai_plus/
           ├── __init__.py
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── cover.py
           ├── manifest.json
           ├── somfy_api.py
           └── strings.json
   ```

3. Restart Home Assistant

4. Add the integration:
   - Go to **Settings** → **Devices & Services**
   - Click **+ Add Integration**
   - Search for "Somfy UAI+"
   - Enter your UAI+ controller's IP address
   - Click **Submit**

Once configured and logged in the integration will connect to your controller, discover all connected shades, and create cover entities for each one.

## Configuration

### Initial Setup

The only required configuration is the IP address of your Somfy UAI+ controller.

### Options

After setup, you can configure additional options by clicking **Configure** on the integration:

| Option | Description | Default |
|--------|-------------|---------|
| **IP Address** | IP address of your UAI+ controller | — |
| **Scan Interval** | How often to poll shade positions (in seconds) | 5 |

## Usage

### Cover Entities

Each shade appears as a cover entity with the following controls:

| Control | Description |
|---------|-------------|
| **Open** | Fully open the shade (position 100%) |
| **Close** | Fully close the shade (position 0%) |
| **Stop** | Stop the shade at its current position |
| **Set Position** | Move to a specific position (0-100%) |

### Position Convention

This integration uses Home Assistant's standard cover position convention:

- **0%** = Fully closed (shade down)
- **100%** = Fully open (shade up)

### Limitations of Movement States

The integration infers shade movement states:

Since the Somfy API doesn't report whether a shade is currently moving, this integration infers movement state:

1. When you send a command (open, close, or set position), the shade is immediately marked as "opening" or "closing"
2. The integration polls the shade's position at regular intervals
3. When two consecutive polls return the same position, the shade is marked as "idle"
4. The shade is also marked as "idle" when it reaches the target position

This approach provides accurate movement feedback while working within the limitations of the Somfy API.

### Entity Attributes

Each shade entity includes additional attributes:

| Attribute | Description |
|-----------|-------------|
| `node_id` | The shade's unique identifier on the SDN network |
| `device_type` | The Somfy motor model (e.g., "Sonesse 50DC") |
| `target_position` | The position the shade is moving toward (when moving) |


### Viewing Logs

To enable debug logging, add this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.somfy_uai_plus: debug
```

## Technical Details

### Telnet Communication Protocol of the Somfy UAI+

This integration uses a JSON-RPC protocol over Telnet (port 23) to communicate with the UAI+ controller.

#### Connection Handshake

```
Server: User:
Client: Telnet 1
Server: Password:
Client: Password 1
Server: Connected:
```

#### API Methods

| Method | Description |
|--------|-------------|
| `sdn.status.ping` | Discover all shade node IDs |
| `sdn.status.info` | Get shade name and type |
| `sdn.status.position` | Get current shade position |
| `sdn.move.to` | Move shade to specific position |
| `sdn.move.up` | Open shade |
| `sdn.move.down` | Close shade |
| `sdn.move.stop` | Stop shade movement |

### Reverse Engineering

The Telnet protocol was reverse engineered by intercepting traffic between a Crestron Home system (running the Somfy UAI+ driver) and the UAI+ controller.

The reverse engineering work, including message captures and protocol documentation, can be found in the `reverse-engineered-protocols/` directory of this repository.

### Architecture

The integration consists of several components:

- **`somfy_api.py`**: Standalone async API client for the UAI+ controller. Handles connection management, message queuing (to prevent out-of-order operations), and all API calls.

- **`coordinator.py`**: Home Assistant DataUpdateCoordinator that polls shade positions and tracks movement states.

- **`cover.py`**: Cover entity implementation with movement state inference.

- **`config_flow.py`**: Configuration UI for setup and options.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.
