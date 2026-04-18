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
from st3m.application import Application, ApplicationContext
import st3m.run

import leds
import captouch

try:
    import ujson as json
except ImportError:
    import json

from struct import pack
from umqtt.simple import MQTTClient

class MQTTClientWithTimeout(MQTTClient):
    def connect(self, clean_session=True):
        # Call parent connect but add timeout to socket
        super().connect(clean_session)
        self.sock.settimeout(10)

from . import config  # config.py with MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS

# ========= CONFIG =========
MQTT_KEEPALIVE = 30

DEVICE_ID = "flow3r-01"
DEVICE_NAME = "flow3r Badge 01"
TOPIC_BASE = b"flow3r/" + DEVICE_ID.encode()

LED_COUNT = 40  # flow3r LEDs are 0..39
PETAL_COUNT = 10  # captouch.petals has 10 elements


class BaseEffect:
    """Base class for LED effects"""
    
    def __init__(self, name):
        self.name = name
        self.active = False
        self.saved_led_r = [0] * LED_COUNT
        self.saved_led_g = [0] * LED_COUNT
        self.saved_led_b = [0] * LED_COUNT
        self.saved_led_br = [0] * LED_COUNT
    
    def activate(self, led_r, led_g, led_b, led_br):
        """Activate effect and save current LED state"""
        self.active = True
        self.saved_led_r[:] = led_r
        self.saved_led_g[:] = led_g
        self.saved_led_b[:] = led_b
        self.saved_led_br[:] = led_br
        self.on_activate()
    
    def deactivate(self):
        """Deactivate effect and return saved LED state"""
        self.active = False
        self.on_deactivate()
        return (self.saved_led_r[:], self.saved_led_g[:], self.saved_led_b[:], self.saved_led_br[:])
    
    def is_active(self):
        return self.active
    
    def update(self, delta_ms):
        """Update effect state. Override in subclasses."""
        pass
    
    def get_led_color(self, i):
        """Return (r, g, b, brightness) for LED i. Override in subclasses."""
        return None
    
    def on_activate(self):
        """Called when effect is activated."""
        pass
    
    def on_deactivate(self):
        """Called when effect is deactivated."""
        pass


class ChaseEffect(BaseEffect):
    """Visual effect: red dot chasing around the badge LEDs"""
    
    def __init__(self):
        super().__init__("chase")
        self.position = 0  # current LED index (0-39)
        self.speed_ms = 80  # time per step in ms
        self.last_update = 0
        self.tail_length = 3  # how many LEDs in the tail
    
    def on_activate(self):
        self.position = 0
        self.last_update = time.ticks_ms()
    
    def update(self, delta_ms):
        if not self.active:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_update) >= self.speed_ms:
            self.position = (self.position + 1) % LED_COUNT
            self.last_update = now
    
    def get_led_color(self, i):
        if not self.active:
            return None
        
        if i == self.position:
            return (255, 0, 0, 255)
        
        distance = (i - self.position) % LED_COUNT
        if distance <= self.tail_length and distance > 0:
            brightness = int(255 * (1 - distance / (self.tail_length + 1)))
            return (brightness, 0, 0, brightness)
        
        return (0, 0, 0, 0)


class BlinkColorCycleEffect(BaseEffect):
    """Blink/Color-Cycle effect: synchronous blinking or color cycling"""
    
    def __init__(self):
        super().__init__("blink_cycle")
        self.mode = "blink"  # "blink" or "cycle"
        self.colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]  # for cycle mode
        self.color_index = 0
        self.state = 0  # 0: off, 1: on
        self.interval_ms = 500
        self.last_change = 0
    
    def update(self, delta_ms):
        if not self.active:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_change) >= self.interval_ms:
            if self.mode == "blink":
                self.state = 1 - self.state
            elif self.mode == "cycle":
                self.color_index = (self.color_index + 1) % len(self.colors)
            self.last_change = now
    
    def get_led_color(self, i):
        if not self.active:
            return None
        if self.mode == "blink":
            if self.state == 1:
                return (255, 255, 255, 255)
            else:
                return (0, 0, 0, 0)
        elif self.mode == "cycle":
            r, g, b = self.colors[self.color_index]
            return (r, g, b, 255)
        return (0, 0, 0, 0)


class RainbowEffect(BaseEffect):
    """Rainbow effect: rotating color wheel across LEDs"""
    
    def __init__(self):
        super().__init__("rainbow")
        self.hue_offset = 0
        self.speed = 1  # hue change per update
    
    def update(self, delta_ms):
        if not self.active:
            return
        self.hue_offset = (self.hue_offset + self.speed) % 360
    
    def get_led_color(self, i):
        if not self.active:
            return None
        # Hue based on position + offset
        hue = (i * 360 / LED_COUNT + self.hue_offset) % 360
        r, g, b = self.hsv_to_rgb(hue, 1.0, 1.0)
        return (int(r * 255), int(g * 255), int(b * 255), 255)
    
    def hsv_to_rgb(self, h, s, v):
        """Convert HSV to RGB"""
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c
        if 0 <= h < 60:
            r, g, b = c, x, 0
        elif 60 <= h < 120:
            r, g, b = x, c, 0
        elif 120 <= h < 180:
            r, g, b = 0, c, x
        elif 180 <= h < 240:
            r, g, b = 0, x, c
        elif 240 <= h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        return r + m, g + m, b + m


class BreathingEffect(BaseEffect):
    """Breathing effect: smooth brightness fade in/out"""
    
    def __init__(self):
        super().__init__("breathing")
        self.brightness = 0
        self.direction = 1  # 1: increasing, -1: decreasing
        self.speed = 2  # brightness change per update
        self.color = (120, 120, 255)  # fixed color
    
    def update(self, delta_ms):
        if not self.active:
            return
        self.brightness += self.direction * self.speed
        if self.brightness >= 255:
            self.brightness = 255
            self.direction = -1
        elif self.brightness <= 0:
            self.brightness = 0
            self.direction = 1
    
    def get_led_color(self, i):
        if not self.active:
            return None
        r, g, b = self.color
        return (r, g, b, int(self.brightness))


class HSVDriftEffect(BaseEffect):
    """HSV Drift effect: pattern with drifting colors"""
    
    def __init__(self):
        super().__init__("hsv_drift")
        self.hue = 0
        self.speed = 1
        # Pattern: every other LED
        self.pattern = [i % 2 for i in range(LED_COUNT)]
    
    def update(self, delta_ms):
        if not self.active:
            return
        self.hue = (self.hue + self.speed) % 360
    
    def get_led_color(self, i):
        if not self.active:
            return None
        if self.pattern[i]:
            r, g, b = self.hsv_to_rgb(self.hue, 1.0, 1.0)
            return (int(r * 255), int(g * 255), int(b * 255), 255)
        else:
            return (0, 0, 0, 0)
    
    def hsv_to_rgb(self, h, s, v):
        """Convert HSV to RGB"""
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c
        if 0 <= h < 60:
            r, g, b = c, x, 0
        elif 60 <= h < 120:
            r, g, b = x, c, 0
        elif 120 <= h < 180:
            r, g, b = 0, c, x
        elif 180 <= h < 240:
            r, g, b = 0, x, c
        elif 240 <= h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        return r + m, g + m, b + m


class EffectManager:
    """Manages multiple LED effects, ensuring only one is active at a time"""
    
    def __init__(self):
        self.effects = {
            "chase": ChaseEffect(),
            "blink_cycle": BlinkColorCycleEffect(),
            "rainbow": RainbowEffect(),
            "breathing": BreathingEffect(),
            "hsv_drift": HSVDriftEffect(),
        }
        self.active_effect = None
    
    def activate_effect(self, name, led_r, led_g, led_b, led_br):
        """Activate a specific effect, deactivating others"""
        if self.active_effect:
            self.active_effect.deactivate()
        if name in self.effects:
            self.effects[name].activate(led_r, led_g, led_b, led_br)
            self.active_effect = self.effects[name]
            return True
        return False
    
    def deactivate_effect(self, name):
        """Deactivate a specific effect"""
        if self.active_effect and self.active_effect.name == name:
            saved = self.active_effect.deactivate()
            self.active_effect = None
            return saved
        return None
    
    def get_active_effect_name(self):
        """Get name of active effect or None"""
        return self.active_effect.name if self.active_effect else None
    
    def update(self, delta_ms):
        """Update active effect"""
        if self.active_effect:
            self.active_effect.update(delta_ms)
    
    def get_led_color(self, i):
        """Get LED color from active effect"""
        if self.active_effect:
            return self.active_effect.get_led_color(i)
        return None


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


class MqttHaApp(Application):
    def __init__(self, app_ctx: ApplicationContext) -> None:
        super().__init__(app_ctx)
        self._status = "init"
        self._statuslevel= 0  # -1=all good, 0=normal, 1=warning, 2=error (for LED color)
        self._mqtt = None
        self._connected_mqtt = False

        self._next_mqtt_try_ms = 0
        self._backoff_ms = 1000

        self._next_discovery_try_ms = 0

        # Cache: per LED remember last state (0..255)
        self._led_r = [255] * LED_COUNT
        self._led_g = [255] * LED_COUNT
        self._led_b = [255] * LED_COUNT
        self._led_br = [0] * LED_COUNT  # brightness 0..255 (mapped to alpha)

        # Effect manager for multiple effects
        self.effect_manager = EffectManager()

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
                conf.petals[i].mode = 3
            conf.apply()
        except Exception as e:
            self._statuslevel= 2
            self._status = "captouch err: {}".format(str(e))

    # ---------- MQTT helpers ----------
    def _mqtt_disconnect(self):
        """Disconnect from MQTT broker"""
        try:
            if self._mqtt:
                self._mqtt.publish(self._avail_topic(), b"offline", retain=True)
                self._mqtt.disconnect()
        except Exception as e:
            self._statuslevel= 2
            self._status = "discon err: {}".format(str(e))
        self._mqtt = None
        self._connected_mqtt = False

    def _mqtt_connect(self) -> bool:
        """Connect to MQTT broker"""
        try:
            self._mqtt = MQTTClientWithTimeout(
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
            except Exception as e:
                self._statuslevel= 2
                self._status = "lastwill err: {}".format(str(e))

            self._mqtt.connect()
            self._mqtt.publish(self._avail_topic(), b"online", retain=True)

            # Subscribe to LED command topics with wildcard
            self._mqtt.subscribe(TOPIC_BASE + b"/led/+/set")
            # Subscribe to effect control
            for effect_name in self.effect_manager.effects.keys():
                self._mqtt.subscribe(TOPIC_BASE + b"/effect/" + effect_name.encode() + b"/set")

            self._connected_mqtt = True
            self._backoff_ms = 1000
            return True
        except Exception as e:
            err_msg = str(e)
            self._statuslevel= 2
            self._status = f"{type(e).__name__}: {err_msg}"
            return False

    def _safe_pub(self, topic: bytes, payload: bytes, retain: bool = False):
        """Wrapper: mark MQTT as lost on errors"""
        try:
            self._mqtt.publish(topic, payload, retain=retain)
            return True
        except Exception:
            self._mqtt_disconnect()
            self._statuslevel= 2
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

    def _effect_cmd_topic(self, name) -> bytes:
        """Effect command topic"""
        return TOPIC_BASE + b"/effect/" + name.encode() + b"/set"

    def _effect_state_topic(self, name) -> bytes:
        """Effect state topic"""
        return TOPIC_BASE + b"/effect/" + name.encode() + b"/state"

    def _active_effect_topic(self) -> bytes:
        """Active effect state topic"""
        return TOPIC_BASE + b"/active_effect"

    # ---------- Home Assistant MQTT Discovery ----------
    def _send_discovery(self):
        """Send MQTT Discovery messages (batched to avoid overwhelming connection)"""
        dev = {
            "identifiers": [DEVICE_ID],
            "name": DEVICE_NAME,
            "manufacturer": "flow3r",
            "model": "flow3r badge",
        }

        # Publish availability first
        self._mqtt.publish(TOPIC_BASE + b"/availability", b"online", retain=True)

        # LEDs - config only (no states during discovery)
        for i in range(LED_COUNT):
            cfg = {
                "name": f"{DEVICE_NAME} LED {i}",
                "unique_id": f"{DEVICE_ID}_led_{i}",
                "device": dev,
                "schema": "json",
                "command_topic": f"flow3r/{DEVICE_ID}/led/{i}/set",
                "state_topic": f"flow3r/{DEVICE_ID}/led/{i}/state",
                "availability_topic": f"flow3r/{DEVICE_ID}/availability",
                "payload_available": "online",
                "payload_not_available": "offline",
                "supported_color_modes": ["rgb"],
            }
            disc_topic = f"homeassistant/light/{DEVICE_ID}/led_{i}/config"
            self._mqtt.publish(disc_topic.encode(), json.dumps(cfg).encode(), retain=True)

        # Petals
        for i in range(PETAL_COUNT):
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
            self._mqtt.publish(disc_topic.encode(), json.dumps(cfg).encode(), retain=True)

        # Effects
        for effect_name in self.effect_manager.effects.keys():
            cfg = {
                "name": f"{DEVICE_NAME} {effect_name} Effect",
                "unique_id": f"{DEVICE_ID}_effect_{effect_name}",
                "device": dev,
                "command_topic": f"flow3r/{DEVICE_ID}/effect/{effect_name}/set",
                "state_topic": f"flow3r/{DEVICE_ID}/effect/{effect_name}/state",
                "availability_topic": f"flow3r/{DEVICE_ID}/availability",
                "payload_available": "online",
                "payload_not_available": "offline",
                "payload_on": "ON",
                "payload_off": "OFF",
                "state_on": "ON",
                "state_off": "OFF",
            }
            disc_topic = f"homeassistant/switch/{DEVICE_ID}/effect_{effect_name}/config"
            self._mqtt.publish(disc_topic.encode(), json.dumps(cfg).encode(), retain=True)

        # Active effect sensor
        cfg = {
            "name": f"{DEVICE_NAME} Active Effect",
            "unique_id": f"{DEVICE_ID}_active_effect",
            "state_topic": f"flow3r/{DEVICE_ID}/active_effect",
            "availability_topic": f"flow3r/{DEVICE_ID}/availability",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": dev,
        }
        disc_topic = f"homeassistant/sensor/{DEVICE_ID}/active_effect/config"
        self._mqtt.publish(disc_topic.encode(), json.dumps(cfg).encode(), retain=True)

        # Publish initial states
        for effect_name in self.effect_manager.effects.keys():
            self._publish_effect_state(effect_name, retain=True)
        self._publish_active_effect_state(retain=True)

        # Publish initial LED states (subset: only first 5 for quick feedback)
        for i in range(min(5, LED_COUNT)):
            self._publish_led_state(i, retain=True)

        self._discovery_sent = True


    # ---------- LED control ----------
    def _apply_led(self, i: int, r255: int, g255: int, b255: int, br255: int):
        """Apply LED color and brightness to hardware"""

        scale = clamp01(br255 / 255.0)

        r = clamp01((r255 / 255.0) * scale)
        g = clamp01((g255 / 255.0) * scale)
        b = clamp01((b255 / 255.0) * scale)

        leds.set_rgb(i, r, g, b)
        leds.update()

        # gemerkte Wunschfarbe beibehalten
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

    def _publish_effect_state(self, name, retain: bool = True):
        """Publish effect state to MQTT"""
        state = "ON" if self.effect_manager.effects[name].is_active() else "OFF"
        self._safe_pub(self._effect_state_topic(name), state.encode(), retain=retain)

    def _publish_active_effect_state(self, retain: bool = True):
        """Publish active effect name to MQTT"""
        active = self.effect_manager.get_active_effect_name()
        state = active if active else "none"
        self._safe_pub(self._active_effect_topic(), state.encode(), retain=retain)

    def _update_leds(self):
        """Update all LEDs based on effect or individual control"""
        for i in range(LED_COUNT):
            color = self.effect_manager.get_led_color(i)
            if color is not None:
                r, g, b, br = color
                self._apply_led_hw(i, r, g, b, br)
            else:
                # Use cached individual control
                r = self._led_r[i]
                g = self._led_g[i]
                b = self._led_b[i]
                br = self._led_br[i]
                self._apply_led_hw(i, r, g, b, br)

    def _apply_led_hw(self, i: int, r255: int, g255: int, b255: int, br255: int):
        """Apply LED color and brightness to hardware only (no MQTT publish)"""
        scale = clamp01(br255 / 255.0)
        r = clamp01((r255 / 255.0) * scale)
        g = clamp01((g255 / 255.0) * scale)
        b = clamp01((b255 / 255.0) * scale)
        leds.set_rgb(i, r, g, b)
        leds.update()

    def _handle_led_msg(self, topic, msg):
        """Handle LED command messages"""
        # If an effect is active, ignore individual LED commands
        if self.effect_manager.get_active_effect_name() is not None:
            self._status = "LED control disabled during effect"
            return

        # Extract index
        parts = topic.split(b"/")  # [b'flow3r', b'flow3r-01', b'led', b'0', b'set']
        try:
            i = int(parts[-2])
            if i < 0 or i >= LED_COUNT:
                return
        except Exception:
            return

        try:
            raw = msg.decode().strip()
        except Exception:
            return

        # JSON oder Plaintext ON/OFF akzeptieren
        try:
            if raw == "ON" or raw == "OFF":
                data = {"state": raw}
            else:
                data = json.loads(raw)
        except Exception:
            self._status = "bad payload"
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
            # hart aus: Helligkeit auf 0
            br = 0
 
        # Apply LED changes
        self._status = f"rx LED{i} {state} br={br}"
        self._apply_led(i, r, g, b, br)

    def _handle_effect_msg(self, msg, effect_name):
        """Handle effect command messages"""
        try:
            raw = msg.decode().strip().upper()
        except Exception:
            return

        previous_effect = self.effect_manager.get_active_effect_name()

        if raw == "ON":
            # Save current LED state and activate effect
            self.effect_manager.activate_effect(effect_name, self._led_r, self._led_g, self._led_b, self._led_br)
            self._status = f"{effect_name} effect ON"
        elif raw == "OFF":
            # Deactivate effect and restore saved LED state
            saved = self.effect_manager.deactivate_effect(effect_name)
            if saved:
                saved_r, saved_g, saved_b, saved_br = saved
                # Restore all LEDs to their previous state
                for i in range(LED_COUNT):
                    self._apply_led(i, saved_r[i], saved_g[i], saved_b[i], saved_br[i])
            self._status = f"{effect_name} effect OFF"
        else:
            return

        # Publish effect state for the requested effect
        self._publish_effect_state(effect_name, retain=True)

        # If another effect was previously active, update its state too
        if previous_effect and previous_effect != effect_name:
            self._publish_effect_state(previous_effect, retain=True)

        # Publish the active effect sensor state whenever effects change
        self._publish_active_effect_state(retain=True)

    # ---------- MQTT callback ----------
    def _on_mqtt_msg(self, topic, msg):
        """Handle incoming MQTT messages"""
        # topic: bytes, msg: bytes (MicroPython umqtt)
        if not (isinstance(topic, (bytes, bytearray)) and isinstance(msg, (bytes, bytearray))):
            return

        # We're only interested in: flow3r/<id>/led/<i>/set or flow3r/<id>/effect/<name>/set
        if not topic.endswith(b"/set"):
            return
        if b"/led/" in topic:
            self._handle_led_msg(topic, msg)
        elif b"/effect/" in topic:
            # Extract effect name from topic: flow3r/<id>/effect/<name>/set
            parts = topic.split(b"/")
            if len(parts) >= 4:
                effect_name = parts[-2].decode()
                if effect_name in self.effect_manager.effects:
                    self._handle_effect_msg(msg, effect_name)
        else:
            return

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
        except Exception as e:
            self._status = "petal err: {}".format(str(e))

        raw_cap = None
        try:
            raw_cap = round(float(pet.raw_cap), 1)
        except Exception:
            raw_cap = 0.0

        pressed = False
        try:
            pressed = bool(pet.pressed)
        except Exception as e:
            self._status = "petal err: {}".format(str(e))

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

        ctx.font_size = 20
        ctx.move_to(-50, -50)
        ctx.text(f"Home Flow3r")
        
        ctx.font_size = 12
        ctx.move_to(-90, -20)
        ctx.rgb(0, 1, 0) if wifi_is_connected() else ctx.rgb(1, 0, 0)
        ctx.text(f"WiFi")
        ctx.rgb(0, 1, 0) if self._connected_mqtt else ctx.rgb(1, 0, 0)
        ctx.move_to(50, -20)
        ctx.text(f"MQTT")

        ctx.rgb(1,0, 0) if self._statuslevel == 2 else ctx.rgb(0, 1, 0)
        status = str(self._status)
        ctx.move_to(-100, 50)
        ctx.text(status)

    def think(self, ins, delta_ms: int) -> None:
        """Main logic loop"""
        super().think(ins, delta_ms)
        now = time.ticks_ms()
        
        # WiFi must be managed by firmware
        if not wifi_is_connected():
            if self._connected_mqtt:
                self._mqtt_disconnect()
            self._statuslevel= 2
            self._status = "WiFi disconnected"
            self._next_mqtt_try_ms = 0
            self._backoff_ms = 1000
            return

        # MQTT connect/reconnect with backoff
        if not self._connected_mqtt:
            if time.ticks_diff(now, self._next_mqtt_try_ms) >= 0:
                self._status = "connecting MQTT..."
                if self._mqtt_connect():
                    self._statuslevel= -1
                    self._status = "MQTT connected"
                else:
                    self._mqtt_disconnect()
                    # status already set by _mqtt_connect to error message
                    self._backoff_ms = min(self._backoff_ms * 2, 30_000)
                    self._next_mqtt_try_ms = time.ticks_add(now, self._backoff_ms)
            return

        # Send discovery once after MQTT is up, or re-send periodically (every 5 minutes)
        if not self._discovery_sent or time.ticks_diff(now, self._next_discovery_try_ms) >= 0:
            if time.ticks_diff(now, self._next_discovery_try_ms) >= 0:
                try:
                    self._send_discovery()
                    self._statuslevel= -1
                    self._status = "discovery sent, ready"
                    self._next_discovery_try_ms = time.ticks_add(now, 300_000)  # Re-send every 5 minutes
                except Exception as e:
                    self._status = f"discovery err: {str(e)}"
                    self._next_discovery_try_ms = time.ticks_add(now, 5000)

        # Handle incoming messages
        try:
            self._mqtt.check_msg()
        except Exception:
            self._mqtt_disconnect()
            self._statuslevel=2
            self._status = "MQTT lost"
            self._next_mqtt_try_ms = time.ticks_add(now, self._backoff_ms)
            self._discovery_sent = False  # Reset discovery flag on disconnect
            return

        # Update chase effect
        self.effect_manager.update(delta_ms)

        # Update LEDs based on effect or individual control
        self._update_leds()

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
                except Exception as e:
                    self._status = "petal err: {}".format(str(e))

                if pressed or (payload != last):
                    ok = self._safe_pub(self._petal_topic(i), payload.encode(), retain=False)
                    if not ok:
                        return
                    self._petal_last[i] = payload
                    self._petal_last_ms[i] = now
            except Exception as e:
                # Skip this petal if there's an error
                self._status = "petal err: {}".format(str(e))


# Run the app
if __name__ == "__main__":
    st3m.run.run_app(MqttHaApp)
