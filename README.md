# flow3r Badge - Home Assistant MQTT Integration

This integration allows you to control the flow3r badge LEDs and monitor petal sensor states from Home Assistant via MQTT.

## Features

- **40 Individual LED Controls**: Full RGB color and brightness control for each LED
- **10 Petal Sensors**: Monitor capacitive touch with position (x/y) and raw capacitance values
- **MQTT Auto-Discovery**: Automatic device registration in Home Assistant
- **Real-time Updates**: Immediate LED response and petal state publishing
- **Persistent Connection**: Automatic reconnection with exponential backoff
- **Availability Tracking**: Online/offline status in Home Assistant

## Prerequisites

### Hardware
- flow3r badge with WiFi capability
- Network connection to Home Assistant

### Software
- Home Assistant with Mosquitto MQTT broker (add-on or standalone)
- flow3r badge firmware with MicroPython support

## Installation

### 1. Setup MQTT Broker in Home Assistant

Install the Mosquitto broker add-on:
1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Search for "Mosquitto broker"
3. Click **Install**
4. Configure the add-on:
   ```yaml
   logins:
     - username: your_username
       password: your_password
   ```
5. Start the add-on and enable "Start on boot"

### 2. Install the App on flow3r Badge

1. Copy these files to your flow3r badge in the apps directory:
   ```
   /apps/flow3r2ha-mqtt/
   ├── __init__.py
   ├── config.py
   └── flow3r.toml
   ```

2. Create `config.py` from `config_example.py`:
   ```python
   MQTT_HOST = "192.168.0.101"  # Your Home Assistant IP
   MQTT_PORT = 1883
   MQTT_USER = b"your_username"
   MQTT_PASS = b"your_password"
   ```

3. Ensure WiFi is configured on your badge (via settings)

### 3. Run the App

1. On your flow3r badge, navigate to **Apps** → **flow3r2HA-MQTT**
2. The app will:
   - Connect to WiFi
   - Connect to MQTT broker
   - Send auto-discovery messages to Home Assistant
   - Start publishing petal states

3. Check the badge screen for connection status:
   - WiFi: OK / waiting...
   - MQTT: OK / connecting...
   - Status message

### 4. Verify in Home Assistant

1. Go to **Settings** → **Devices & Services** → **MQTT**
2. You should see a device: **flow3r Badge 01**
3. Click on it to see:
   - 40 Light entities (LED 0-39)
   - 10 Sensor entities (Petal 0-9)

## Usage

### LED Control

#### Via Dashboard
Create light cards in your dashboard to control LEDs:
- Toggle on/off
- Adjust brightness (0-255)
- Set RGB color

#### Via Automation
```yaml
service: light.turn_on
target:
  entity_id: light.flow3r_badge_01_led_0
data:
  brightness: 200
  rgb_color: [255, 0, 0]  # Red
```

#### Via MQTT
```json
Topic: flow3r/flow3r-01/led/0/set
Payload: {
  "state": "ON",
  "brightness": 128,
  "color": {"r": 255, "g": 100, "b": 0}
}
```

### Petal Monitoring

Each petal sensor provides:
- **State**: Raw capacitance value
- **Attributes**:
  - `pressed`: Boolean (true when touched)
  - `x`: X position (for top petals with 2D support)
  - `y`: Y position (for top petals with 2D support)
  - `raw_cap`: Capacitance value

#### Create Automations Based on Petal Touch

```yaml
automation:
  - alias: "Petal 0 Pressed - Turn LED Red"
    trigger:
      - platform: state
        entity_id: sensor.flow3r_badge_01_petal_0
        attribute: pressed
        to: true
    action:
      - service: light.turn_on
        target:
          entity_id: light.flow3r_badge_01_led_0
        data:
          rgb_color: [255, 0, 0]
```

## Dashboard Examples

See `ha_dashboard_example.yaml` for complete dashboard configurations.

### Quick Start Dashboard

```yaml
type: vertical-stack
cards:
  # Master LED control
  - type: light
    entity: light.flow3r_badge_01_led_0
    name: LED 0 (Master)
  
  # Petal status
  - type: entities
    title: Petals
    entities:
      - sensor.flow3r_badge_01_petal_0
      - sensor.flow3r_badge_01_petal_1
      - sensor.flow3r_badge_01_petal_2
```

## Troubleshooting

### Badge Shows "WiFi disconnected"
- Check WiFi settings on badge
- Ensure badge is in range of WiFi network
- Verify WiFi credentials

### Badge Shows "MQTT fail (retry)"
- Verify MQTT broker is running in Home Assistant
- Check `config.py` settings (IP, username, password)
- Ensure MQTT port 1883 is accessible
- Check Home Assistant logs for MQTT connection attempts

### Entities Not Appearing in Home Assistant
- Wait 30 seconds after app starts
- Check MQTT integration is enabled
- Go to Settings → Devices & Services → MQTT → Configure
- Enable "Enable discovery"
- Check topic prefix is "homeassistant"

### LEDs Not Responding
- Verify entity is available (not "unavailable" state)
- Check MQTT topics in MQTT explorer or HA Developer Tools
- Try sending test command via MQTT directly
- Restart the app on the badge

### Petal Sensors Not Updating
- Touch petals to trigger updates
- Check that discovery was sent (status shows "discovery sent, ready")
- Verify MQTT broker receives petal messages

## MQTT Topics

### LED Control
- Command: `flow3r/flow3r-01/led/{0-39}/set`
- State: `flow3r/flow3r-01/led/{0-39}/state`

### Petal Sensors
- State: `flow3r/flow3r-01/petal/{0-9}`

### Availability
- `flow3r/flow3r-01/availability` (online/offline)

### Discovery
- `homeassistant/light/flow3r-01/led_{0-39}/config`
- `homeassistant/sensor/flow3r-01/petal_{0-9}/config`

## Advanced Configuration

### Multiple Badges

To use multiple badges, change the `DEVICE_ID` in `__init__.py`:

```python
DEVICE_ID = "flow3r-02"  # Change for each badge
DEVICE_NAME = "flow3r Badge 02"
```

### Custom LED Patterns

Create automations or scripts to control multiple LEDs:

```yaml
script:
  rainbow_effect:
    sequence:
      - repeat:
          count: 40
          sequence:
            - service: light.turn_on
              target:
                entity_id: "light.flow3r_badge_01_led_{{ repeat.index - 1 }}"
              data:
                rgb_color: 
                  - "{{ (repeat.index * 6.375) | int }}"
                  - "{{ (255 - repeat.index * 6.375) | int }}"
                  - 128
            - delay:
                milliseconds: 50
```

## License

LGPL-3.0-only

## Credits

- Author: superwallah
- flow3r badge: https://flow3r.garden
