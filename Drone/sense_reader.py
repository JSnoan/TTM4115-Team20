import math
import time


class SenseReader:
    """Reads Sense HAT data when available, with a portable fallback."""

    def __init__(self, use_mock=False, mock_joystick_active=False):
        self.use_mock = use_mock
        self.mock_joystick_active = mock_joystick_active
        self.sense = None
        self.error = None
        self.started_at = time.time()
        self.joystick_active_until = 0
        self.last_joystick_direction = None
        self.last_joystick_action = None

        if self.use_mock:
            return

        try:
            from sense_hat import SenseHat

            self.sense = SenseHat()
        except Exception as err:
            self.error = str(err)

    def read(self):
        if self.sense is None:
            if self.use_mock:
                return self._mock_reading()

            return {
                "available": False,
                "source": "fallback",
                "error": self.error or "Sense HAT not available",
                "joystick": self._inactive_joystick("fallback"),
            }

        try:
            return {
                "available": True,
                "source": "sense_hat",
                "acceleration": self.sense.get_accelerometer_raw(),
                "orientation": self.sense.get_orientation_degrees(),
                "temperature": round(self.sense.get_temperature(), 2),
                "pressure": round(self.sense.get_pressure(), 2),
                "humidity": round(self.sense.get_humidity(), 2),
                "joystick": self._read_joystick(),
            }
        except Exception as err:
            return {
                "available": False,
                "source": "sense_hat",
                "error": str(err),
                "joystick": self._read_joystick(),
            }

    def _mock_reading(self):
        elapsed = time.time() - self.started_at
        wobble = math.sin(elapsed / 2)

        return {
            "available": False,
            "source": "mock",
            "acceleration": {
                "x": round(0.02 * wobble, 3),
                "y": round(0.01 * math.cos(elapsed / 3), 3),
                "z": round(0.98 + 0.01 * wobble, 3),
            },
            "orientation": {
                "pitch": round(2.0 * wobble, 2),
                "roll": round(1.5 * math.cos(elapsed / 4), 2),
                "yaw": round((elapsed * 8) % 360, 2),
            },
            "temperature": round(22.0 + 0.4 * wobble, 2),
            "pressure": round(1013.0 + 0.8 * wobble, 2),
            "humidity": round(38.0 + 2.0 * math.cos(elapsed / 5), 2),
            "joystick": {
                "available": True,
                "active": self.mock_joystick_active,
                "direction": "middle" if self.mock_joystick_active else None,
                "action": "mock_active" if self.mock_joystick_active else "mock_idle",
                "source": "mock",
            },
        }

    def _read_joystick(self):
        if self.sense is None:
            return self._inactive_joystick("fallback")

        try:
            events = self.sense.stick.get_events()
        except Exception as err:
            return {
                "available": False,
                "active": False,
                "direction": None,
                "action": None,
                "source": "sense_hat",
                "error": str(err),
            }

        now = time.time()
        for event in events:
            self.last_joystick_direction = event.direction
            self.last_joystick_action = event.action

            if event.action in ["pressed", "held"]:
                self.joystick_active_until = now + 0.8
            elif event.action == "released":
                self.joystick_active_until = 0

        active = now < self.joystick_active_until
        return {
            "available": True,
            "active": active,
            "direction": self.last_joystick_direction if active else None,
            "action": self.last_joystick_action,
            "source": "sense_hat",
        }

    def _inactive_joystick(self, source):
        return {
            "available": False,
            "active": False,
            "direction": None,
            "action": None,
            "source": source,
        }
