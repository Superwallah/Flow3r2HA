# This flow3r app connects to a MQTT broker and integrates with Home Assistant via MQTT Discovery.
# It exposes each LED as a separate MQTT Light Entity and each petal sensor as a separate MQTT Sensor Entity.
# The app handles MQTT connection with backoff, publishes LED states, and reacts to MQTT commands to control the LEDs.
# Configure MQTT connection parameters in config.py (MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS)!
# Required is 
# - a running MQTT broker (e.g. Mosquitto add-on in Home Assistant)
# - Home Assistant with MQTT integration enabled
# - flow3r firmware >=1.4.0 with WiFi configured

import time
import network

from st3m.reactor import Responder
import st3m.run

import leds
import captouch

try:
    import ujson as json
except ImportError:
    import json

from umqtt.simple import MQTTClient

from . import config  # config.py with MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS

# ========= CONFIG =========
MQTT_KEEPALIVE = 30

DEVICE_ID = "flow3r-01"
DEVICE_NAME = "flow3r Badge 01"
TOPIC_BASE = b"flow3r/" + DEVICE_ID.encode()

LED_COUNT = 40  # flow3r LEDs are 0..39
PETAL_COUNT = 10  # captouch.petals has 10 elements


def wifi_is_connected() -> bool:
    try:
        sta = network.WLAN()
        return bool(sta.active()) and bool(sta.isconnected())
    except Exception:
        return False


def clamp01(x: float) -> float:
    """Clamp value to 0.0-1.0 range"""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


class MqttHaApp(Responder):
    def __init__(self) -> None:
        self._status = "init"
        self._mqtt = None
        self._connected_mqtt = False

        self._next_mqtt_try_ms = 0
        self._backoff_ms = 1000

        # Cache: per LED remember last state (0..255)
        self._led_r = [255] * LED_COUNT
        self._led_g = [255] * LED_COUNT
        self._led_b = [255] * LED_COUNT
        self._led_br = [0] * LED_COUNT  # brightness 0..255 (mapped to alpha)

        # Make LEDs responsive
        try:
            # For reaction-critical apps: at least 200, or for very fast: 255
            leds.set_slew_rate(max(leds.get_slew_rate(), 200))
            # Enable auto update for faster visual changes
            leds.set_auto_update(True)
            # Optional: global brightness (0..255), default is 70
            # leds.set_brightness(255)
        except Exception:
            pass

        # Petal last payload to reduce spam
        self._petal_last = [None] * PETAL_COUNT
        self._petal_last_ms = [0] * PETAL_COUNT

        self._discovery_sent = False

        # Captouch: activate positional output
        # 3 = 2D (for top petals), bottom petals typically don't support 2D
        try:
            conf = captouch.Config.default()
            # Enable 2D for top petals (even indices) where supported
            for i in range(0, PETAL_COUNT, 2):
                try:
                    conf.petals[i].mode = 3
                except Exception:
                    pass
            conf.apply()
        except Exception:
            pass

    # ---------- MQTT helpers ----------
    def _mqtt_disconnect(self):
        """Disconnect from MQTT broker"""
        try:
            if self._mqtt:
                try:
                    self._mqtt.publish(self._avail_topic(), b"offline", retain=True)
                except Exception:
                    pass
                self._mqtt.disconnect()
        except Exception:
            pass
        self._mqtt = None
        self._connected_mqtt = False

    def _mqtt_connect(self) -> bool:
        """Connect to MQTT broker"""
        try:
            self._mqtt = MQTTClient(
                client_id=DEVICE_ID.encode(),
                server=config.MQTT_HOST,
                port=config.MQTT_PORT,
                user=config.MQTT_USER,
                password=config.MQTT_PASS,
                keepalive=MQTT_KEEPALIVE,
            )
            self._mqtt.set_callback(self._on_mqtt_msg)

            # Last will
            try:
                self._mqtt.set_last_will(self._avail_topic(), b"offline", retain=True, qos=0)
            except Exception:
                pass

            self._mqtt.connect()
            self._mqtt.publish(self._avail_topic(), b"online", retain=True)

            # Subscribe LED command topics
            for i in range(LED_COUNT):
                self._mqtt.subscribe(self._led_cmd_topic(i))

            self._connected_mqtt = True
            self._backoff_ms = 1000
            return True
        except Exception as e:
            self._status = f"mqtt err: {str(e)[:20]}"
            return False

    def _safe_pub(self, topic: bytes, payload: bytes, retain: bool = False):
        """Wrapper: mark MQTT as lost on errors"""
        try:
            self._mqtt.publish(topic, payload, retain=retain)
            return True
        except Exception:
            self._mqtt_disconnect()
            self._status = "mqtt pub err"
            return False

    # ---------- Topics ----------
    def _avail_topic(self) -> bytes:
        """Availability topic"""
        return TOPIC_BASE + b"/availability"

    def _led_cmd_topic(self, i: int) -> bytes:
        """LED command topic for index i"""
        return TOPIC_BASE + b"/led/" + str(i).encode() + b"/set"

    def _led_state_topic(self, i: int) -> bytes:
        """LED state topic for index i"""
        return TOPIC_BASE + b"/led/" + str(i).encode() + b"/state"

    def _petal_topic(self, i: int) -> bytes:
        """Petal sensor topic for index i"""
        return TOPIC_BASE + b"/petal/" + str(i).encode()

    # ---------- Home Assistant MQTT Discovery ----------
    def _send_discovery(self):
        """
        Send MQTT Discovery messages for Home Assistant:
        - 40 MQTT Light Entities (json schema) for individual LEDs
        - 10 MQTT Sensor Entities for Petals (state=raw_cap, attributes=x/y/pressed)
        """
        # Device block (for "Device" in HA)
        dev = {
            "identifiers": [DEVICE_ID],
            "name": DEVICE_NAME,
            "manufacturer": "flow3r",
            "model": "flow3r badge",
        }

        # Lights
        for i in range(LED_COUNT):
            # MQTT Light JSON schema:
            # - command_topic receives JSON: {"state":"ON","brightness":128,"color":{"r":255,"g":0,"b":0}}
            # - state_topic sends JSON in the same format
            cfg = {
                "name": f"{DEVICE_NAME} LED {i}",
                "unique_id": f"{DEVICE_ID}_led_{i}",
                "device": dev,

                # Discovery topics als STRING
                "command_topic": f"flow3r/{DEVICE_ID}/led/{i}/set",
                "state_topic":   f"flow3r/{DEVICE_ID}/led/{i}/state",
                "availability_topic": f"flow3r/{DEVICE_ID}/availability",
                "payload_available": "online",
                "payload_not_available": "offline",

                # => sorgt dafür, dass HA den Farbwähler zeigt
                "supported_color_modes": ["rgb"],
                "brightness": True,

                # JSON rein/raus über Templates (robust)
                "command_template": (
                    '{"state":"{{ value }}",'
                    '"brightness":{{ brightness | default(255) }},'
                    '"color":{"r":{{ red | default(255) }},'
                            '"g":{{ green | default(255) }},'
                            '"b":{{ blue | default(255) }}}}'
                    '}'
                ),

                "state_value_template": "{{ value_json.state }}",
                "brightness_value_template": "{{ value_json.brightness }}",
                "red_value_template": "{{ value_json.color.r }}",
                "green_value_template": "{{ value_json.color.g }}",
                "blue_value_template": "{{ value_json.color.b }}",
            }


            disc_topic = f"homeassistant/light/{DEVICE_ID}/led_{i}/config"
            self._mqtt.publish(disc_topic, json.dumps(cfg).encode(), retain=True)

            # Initial state publish (retained), so HA sees something after restart
            self._publish_led_state(i, retain=True)

        # Petal sensors
        for i in range(PETAL_COUNT):
            # We publish JSON on flow3r/<id>/petal/<i>
            # state = raw_cap (Float), attributes: pressed,x,y
            cfg = {
                "name": f"{DEVICE_NAME} Petal {i}",
                "unique_id": f"{DEVICE_ID}_petal_{i}",
                "state_topic": self._petal_topic(i).decode(),
                "availability_topic": self._avail_topic().decode(),
                "payload_available": "online",
                "payload_not_available": "offline",
                "value_template": "{{ value_json.raw_cap }}",
                "json_attributes_topic": self._petal_topic(i).decode(),
                "unit_of_measurement": "cap",
                "device": dev,
            }
            disc_topic = f"homeassistant/sensor/{DEVICE_ID}/petal_{i}/config"
            self._mqtt.publish(disc_topic, json.dumps(cfg).encode(), retain=True)

        self._discovery_sent = True

    # ---------- LED control ----------
    def _apply_led(self, i: int, r255: int, g255: int, b255: int, br255: int):
        """Apply LED color and brightness to hardware"""
        # Mapping: brightness -> alpha (0..1) in set_rgba
        a = clamp01(br255 / 255.0)
        r = clamp01(r255 / 255.0)
        g = clamp01(g255 / 255.0)
        b = clamp01(b255 / 255.0)

        leds.set_rgba(i, r, g, b, a)  # per LED RGB + "brightness" via alpha
        leds.update()

        self._led_r[i] = r255
        self._led_g[i] = g255
        self._led_b[i] = b255
        self._led_br[i] = br255

        self._publish_led_state(i, retain=True)

    def _publish_led_state(self, i: int, retain: bool = True):
        """Publish LED state to MQTT"""
        # HA JSON schema state
        state = "ON" if self._led_br[i] > 0 else "OFF"
        payload = {
            "state": state,
            "brightness": int(self._led_br[i]),
            "color": {"r": int(self._led_r[i]), "g": int(self._led_g[i]), "b": int(self._led_b[i])},
        }
        self._safe_pub(self._led_state_topic(i), json.dumps(payload).encode(), retain=retain)

    # ---------- MQTT callback ----------
    def _on_mqtt_msg(self, topic, msg):
        """Handle incoming MQTT messages"""
        # topic: bytes, msg: bytes (MicroPython umqtt)
        if not (isinstance(topic, (bytes, bytearray)) and isinstance(msg, (bytes, bytearray))):
            return

        # We're only interested in: flow3r/<id>/led/<i>/set
        if (b"/led/" not in topic) or (not topic.endswith(b"/set")):
            return

        # Extract index
        parts = topic.split(b"/")  # [b'flow3r', b'flow3r-01', b'led', b'0', b'set']
        try:
            i = int(parts[-2])
            if i < 0 or i >= LED_COUNT:
                return
        except Exception:
            return

        # Read JSON payload
        try:
            data = json.loads(msg.decode())
        except Exception:
            return

        state = str(data.get("state", "ON")).upper()

        # brightness default: if missing, take current or 255 (so ON is visible)
        br = int(data.get("brightness", self._led_br[i] if self._led_br[i] > 0 else 255))

        col = data.get("color", {})
        r = int(col.get("r", self._led_r[i]))
        g = int(col.get("g", self._led_g[i]))
        b = int(col.get("b", self._led_b[i]))

        # clamp
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        br = max(0, min(255, br))
        
        if state == "OFF":
            # hart aus: Farbe und Helligkeit auf 0
            r = 0
            g = 0
            b = 0
            br = 0
 
        # Apply LED changes
        self._status = f"rx LED{i} {state} br={br}"
        self._apply_led(i, r, g, b, br)

    # ---------- Petal publish ----------
    def _petal_payload(self, i: int, pet) -> str:
        """Build petal sensor JSON payload"""
        # pet.pos can be None or complex/float with real/imag
        x = None
        y = None
        try:
            if pet.pos is not None:
                # pos is typically complex
                x = round(float(pet.pos.real), 2)
                y = round(float(pet.pos.imag), 2)
                if abs(x) < 0.02: x = 0.0
                if abs(y) < 0.02: y = 0.0
        except Exception:
            pass

        raw_cap = None
        try:
            raw_cap = round(float(pet.raw_cap), 1)
        except Exception:
            raw_cap = 0.0

        pressed = False
        try:
            pressed = bool(pet.pressed)
        except Exception:
            pass

        obj = {
            "pressed": pressed,
            "x": x,
            "y": y,
            "raw_cap": raw_cap,
        }
        return json.dumps(obj)

    # ---------- flow3r lifecycle ----------
    def draw(self, ctx):
        """Draw status on screen"""
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(1, 1, 1)

        ctx.move_to(-110, -50)
        ctx.text(f"flow3r -> HA MQTT")

        ctx.move_to(-110, -25)
        ctx.text(f"WiFi: {'OK' if wifi_is_connected() else 'waiting...'}")

        ctx.move_to(-110, 0)
        ctx.text(f"MQTT: {'OK' if self._connected_mqtt else 'connecting...'}")

        ctx.move_to(-110, 25)
        ctx.text(f"{self._status}")

        ctx.move_to(-110, 50)
        ctx.text(f"right button to exit")

    def think(self, ins, delta_ms: int):
        """Main logic loop"""
        now = time.ticks_ms()
        
        # Exit app on button press
        if ins.buttons.os:
            return False

        # WiFi must be managed by firmware
        if not wifi_is_connected():
            if self._connected_mqtt:
                self._mqtt_disconnect()
            self._status = "WiFi disconnected"
            self._next_mqtt_try_ms = 0
            self._backoff_ms = 1000
            return

        # MQTT connect/reconnect with backoff
        if not self._connected_mqtt:
            if time.ticks_diff(now, self._next_mqtt_try_ms) >= 0:
                try:
                    self._status = "connecting MQTT..."
                    if self._mqtt_connect():
                        self._status = "MQTT connected"
                    else:
                        raise Exception("connect failed")
                except Exception as e:
                    self._mqtt_disconnect()
                    self._status = f"MQTT fail (retry)"
                    self._backoff_ms = min(self._backoff_ms * 2, 30_000)
                    self._next_mqtt_try_ms = time.ticks_add(now, self._backoff_ms)
            return

        # Send discovery once after MQTT is up
        if not self._discovery_sent:
            try:
                self._send_discovery()
                self._status = "discovery sent, ready"
            except Exception as e:
                self._status = f"discovery err"
                self._mqtt_disconnect()
                return

        # Handle incoming messages
        try:
            self._mqtt.check_msg()
        except Exception:
            self._mqtt_disconnect()
            self._status = "MQTT lost"
            self._next_mqtt_try_ms = time.ticks_add(now, self._backoff_ms)
            return

        # Publish petals on change (and when pressed) – topics are per petal
        # Rate limit per petal to avoid flooding (min 50ms)
        for i in range(PETAL_COUNT):
            try:
                pet = ins.captouch.petals[i]
                payload = self._petal_payload(i, pet)

                last = self._petal_last[i]
                last_ms = self._petal_last_ms[i]
                if time.ticks_diff(now, last_ms) < 50:
                    continue

                # Send if changed or pressed
                pressed = False
                try:
                    pressed = bool(pet.pressed)
                except Exception:
                    pass

                if pressed or (payload != last):
                    ok = self._safe_pub(self._petal_topic(i), payload.encode(), retain=False)
                    if not ok:
                        return
                    self._petal_last[i] = payload
                    self._petal_last_ms[i] = now
            except Exception:
                # Skip this petal if there's an error
                pass


# Run the app
st3m.run.run_responder(MqttHaApp())
