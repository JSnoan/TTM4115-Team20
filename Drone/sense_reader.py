import math
import time


class SenseReader:
    """Reads Sense HAT data when available, with a portable fallback."""

    def __init__(self, use_mock=False):
        self.use_mock = use_mock
        self.sense = None
        self.error = None
        self.started_at = time.time()

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
            }

        try:
            return {
                "available": True,
                # "source": "sense_hat",
                "acceleration": self.sense.get_accelerometer_raw(),
                # "orientation": self.sense.get_orientation_degrees(),
                # "temperature": round(self.sense.get_temperature(), 2),
                # "pressure": round(self.sense.get_pressure(), 2),
                # "humidity": round(self.sense.get_humidity(), 2),
            }
        except Exception as err:
            return {
                "available": False,
                "source": "sense_hat",
                "error": str(err),
            }

    def _mock_reading(self):
        elapsed = time.time() - self.started_at
        wobble = math.sin(elapsed / 2)

        return {
            "available": False,
            # "source": "mock",
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
            # "temperature": round(22.0 + 0.4 * wobble, 2),
            # "pressure": round(1013.0 + 0.8 * wobble, 2),
            # "humidity": round(38.0 + 2.0 * math.cos(elapsed / 5), 2),
        }
