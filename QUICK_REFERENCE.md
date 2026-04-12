# Quick Reference Guide - flow3r HA Integration

## File Structure
```
/flash/sys/apps/flow3r2ha-mqtt/
├── __init__.py          # Main application code
├── config.py            # Your MQTT configuration
└── flow3r.toml          # App manifest
```

## Essential Configuration

**config.py:**
```python
MQTT_HOST = "192.168.1.100"  # Home Assistant IP
MQTT_PORT = 1883
MQTT_USER = b"mqtt_user"     # Note: must be bytes (b prefix)
MQTT_PASS = b"mqtt_pass"     # Note: must be bytes (b prefix)
```

## MQTT Topics

### LED Control
```
Command: flow3r/flow3r-01/led/{0-39}/set
State:   flow3r/flow3r-01/led/{0-39}/state
```

**Example Command:**
```json
{
  "state": "ON",
  "brightness": 128,
  "color": {"r": 255, "g": 100, "b": 0}
}
```

### Petal Sensors
```
State: flow3r/flow3r-01/petal/{0-9}
```

**Example Response:**
```json
{
  "pressed": true,
  "x": 0.234,
  "y": -0.567,
  "raw_cap": 45.3
}
```

### Availability
```
flow3r/flow3r-01/availability  → "online" or "offline"
```

## Home Assistant Entities

### Lights (40 total)
```
light.flow3r_badge_01_led_0
light.flow3r_badge_01_led_1
...
light.flow3r_badge_01_led_39
```

### Sensors (10 total)
```
sensor.flow3r_badge_01_petal_0
sensor.flow3r_badge_01_petal_1
...
sensor.flow3r_badge_01_petal_9
```

## Quick Commands

### Turn LED On (Red)
```yaml
service: light.turn_on
target:
  entity_id: light.flow3r_badge_01_led_0
data:
  brightness: 255
  rgb_color: [255, 0, 0]
```

### Turn All LEDs Same Color
```yaml
service: light.turn_on
target:
  entity_id:
    - light.flow3r_badge_01_led_0
    - light.flow3r_badge_01_led_1
    # ... (list all 40)
data:
  brightness: 200
  rgb_color: [0, 255, 0]  # Green
```

### Automation: Petal Touch → LED
```yaml
automation:
  - alias: "Petal Touch Response"
    trigger:
      platform: state
      entity_id: sensor.flow3r_badge_01_petal_0
      attribute: pressed
      to: true
    action:
      service: light.turn_on
      target:
        entity_id: light.flow3r_badge_01_led_0
      data:
        rgb_color: [255, 0, 255]
```

## Status Messages

| Message | Meaning |
|---------|---------|
| `WiFi: OK` | Connected to WiFi |
| `WiFi: waiting...` | Not connected, check WiFi settings |
| `MQTT: OK` | Connected to broker |
| `MQTT: connecting...` | Attempting connection |
| `MQTT fail (retry)` | Connection failed, will retry |
| `discovery sent, ready` | All set up, ready to use |

## Common Issues & Fixes

| Issue | Solution |
|-------|----------|
| Can't connect to MQTT | Check IP, username, password in config.py |
| Entities not in HA | Wait 30s, check MQTT discovery is enabled |
| LEDs don't respond | Verify app is running, check entity state |
| Badge shows errors | Check WiFi connection, restart app |

## Exit App
Press the **App** button (middle button on badge)

## Badge LED Layout
```
Top view - 40 LEDs in circular arrangement:
     0
 39     1
38       2
  ...
```

## Petal Layout
```
10 capacitive touch petals around the edge:
- Even numbers (0,2,4,6,8): Top petals with 2D position
- Odd numbers (1,3,5,7,9): Bottom petals (capacitance only)
```

## Useful Developer Tools Commands

### Check MQTT Messages
```
Developer Tools → MQTT
Listen to: flow3r/#
```

### Test LED Command
```
Developer Tools → Services
Service: mqtt.publish
Data:
  topic: flow3r/flow3r-01/led/0/set
  payload: '{"state":"ON","brightness":255,"color":{"r":255,"g":0,"b":0}}'
```

### Check Entity State
```
Developer Tools → States
Filter: flow3r
```

## Files to Customize

1. **config.py** - Your MQTT credentials
2. **__init__.py** - Change `DEVICE_ID` for multiple badges (line 18)
3. Dashboard - Use ha_dashboard_example.yaml

## Default Values

- Device ID: `flow3r-01`
- Device Name: `flow3r Badge 01`
- LED Count: 40
- Petal Count: 10
- MQTT Keepalive: 30 seconds
- Petal Rate Limit: 50ms

## Color Reference

```python
Red:     [255, 0, 0]
Green:   [0, 255, 0]
Blue:    [0, 0, 255]
Yellow:  [255, 255, 0]
Cyan:    [0, 255, 255]
Magenta: [255, 0, 255]
White:   [255, 255, 255]
Orange:  [255, 165, 0]
Purple:  [128, 0, 128]
```

## Getting More Help

- INSTALLATION.md - Detailed setup guide
- README.md - Complete documentation
- ha_dashboard_example.yaml - Dashboard examples
