# Installation Guide - flow3r Badge Home Assistant Integration

## Quick Start

Follow these steps to get your flow3r badge connected to Home Assistant:

### Step 1: Prepare Home Assistant

1. **Install Mosquitto MQTT Broker**
   - Navigate to: Settings → Add-ons → Add-on Store
   - Search for "Mosquitto broker"
   - Click Install and wait for completion
   
2. **Configure Mosquitto**
   - Go to the Mosquitto broker add-on
   - Click on the "Configuration" tab
   - Add a user (example):
   ```yaml
   logins:
     - username: mqtt_user
       password: mqtt_password_123
   ```
   - Click "Save"
   - Go to "Info" tab and click "Start"
   - Enable "Start on boot"

3. **Verify MQTT Integration**
   - Go to: Settings → Devices & Services
   - You should see "MQTT" integration
   - If not, click "Add Integration" and search for MQTT
   - Configure with:
     - Broker: localhost (or your HA IP)
     - Port: 1883
     - Username: mqtt_user
     - Password: mqtt_password_123

### Step 2: Prepare the Badge Files

1. **Download/Copy Files**
   You need these files on your computer:
   - `__init__.py` (main application)
   - `config.py` (your configuration)
   - `flow3r.toml` (app manifest)

2. **Configure MQTT Settings**
   Edit `config.py` with your settings:
   ```python
   MQTT_HOST = "192.168.1.100"  # Your Home Assistant IP
   MQTT_PORT = 1883
   MQTT_USER = b"mqtt_user"      # Must match Mosquitto config
   MQTT_PASS = b"mqtt_password_123"  # Must match Mosquitto config
   ```
   
   **Important Notes:**
   - Find your Home Assistant IP: Settings → System → Network
   - Username and password must be **bytes** (note the `b` prefix)
   - Must match your Mosquitto configuration exactly

### Step 3: Install on flow3r Badge

1. Connect badge via USB
2. Mount as USB storage: Select from menu: System -> Disk Mode (SD)
3. Copy files to: `/flash/sys/apps/superwallah-MqttHaApp`
4. Ensure all three files are in the same directory

### Step 4: Run the Application

1. **On the Badge:**
   - Press the Menu button
   - Navigate to "Apps"
   - Select "flow3r2HA-MQTT"
   - The app will start and show connection status

2. **Expected Behavior:**
   - Screen should show:
     ```
     flow3r -> HA MQTT
     WiFi: OK
     MQTT: OK
     discovery sent, ready
     right button to exit
     ```

3. **If Issues Occur:**
   - "WiFi: waiting..." → Check WiFi settings on badge
   - "MQTT: connecting..." → Check config.py settings
   - "MQTT fail (retry)" → Verify Home Assistant IP and Mosquitto credentials

### Step 5: Verify in Home Assistant

1. **Check Device Registration:**
   - Go to: Settings → Devices & Services → MQTT
   - Click "Devices" tab
   - Look for "flow3r Badge 01"
   - Click on it to see all entities

2. **Expected Entities:**
   - 40 Light entities: `light.flow3r_badge_01_led_0` through `led_39`
   - 10 Sensor entities: `sensor.flow3r_badge_01_petal_0` through `petal_9`

3. **Test LED Control:**
   - Click on any LED entity
   - Toggle it on
   - Verify LED on badge responds

4. **Test Petal Sensors:**
   - Touch a petal on the badge
   - Check the corresponding sensor in HA
   - Should show updated values and "pressed: true" attribute



## Security Notes

⚠️ **Current Implementation:**
- Uses unencrypted MQTT (port 1883)
- Credentials sent in plain text
- Suitable for trusted home networks only

