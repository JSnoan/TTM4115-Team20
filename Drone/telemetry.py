import math


def distance_meters(pos1, pos2):
    lat1, lon1 = pos1
    lat2, lon2 = pos2

    earth_radius_m = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    return 2 * earth_radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def move_towards(current, target, step_meters):
    distance = distance_meters(current, target)
    if distance == 0 or distance <= step_meters:
        return list(target)

    fraction = step_meters / distance
    return [
        current[0] + (target[0] - current[0]) * fraction,
        current[1] + (target[1] - current[1]) * fraction,
    ]


class TelemetrySimulator:
    """Updates simulated drone position and battery without changing states."""

    def __init__(self, logic, speed_mps=20.0):
        self.logic = logic
        self.speed_mps = speed_mps
        self.target = None

    def set_target(self, target):
        if not target:
            return

        if isinstance(target, dict):
            lat = target.get("lat")
            lon = target.get("lon")
            if lat is None or lon is None:
                return
            self.target = [float(lat), float(lon)]
        elif isinstance(target, (list, tuple)) and len(target) == 2:
            self.target = [float(target[0]), float(target[1])]

        self.logic.target = self.target

    def tick(self, elapsed_seconds):
        state = self.logic.current_state
        distance_to_target = None
        distance_to_base = None

        if state == "navigating" and self.target is not None:
            self.logic.pos = move_towards(
                self.logic.pos,
                self.target,
                self.speed_mps * elapsed_seconds,
            )
            distance_to_target = distance_meters(self.logic.pos, self.target)
            self._drain_battery(0.35 * elapsed_seconds)

        elif state == "returning":
            self.logic.pos = move_towards(
                self.logic.pos,
                self.logic.base_pos,
                self.speed_mps * elapsed_seconds,
            )
            distance_to_base = distance_meters(self.logic.pos, self.logic.base_pos)
            self._drain_battery(0.3 * elapsed_seconds)

        elif state == "waiting_onsite":
            self._drain_battery(0.05 * elapsed_seconds)

        elif state == "docked":
            self.logic.battery = min(100, self.logic.battery + 1 * elapsed_seconds)

        telemetry = {
            "speed_mps": self.speed_mps if state in ["navigating", "returning"] else 0,
            "distance_to_target_m": self._round_or_none(distance_to_target),
            "distance_to_base_m": self._round_or_none(distance_to_base),
        }

        return telemetry

    def _drain_battery(self, amount):
        self.logic.battery = max(0, self.logic.battery - amount)

    def _round_or_none(self, value):
        if value is None:
            return None
        return round(value, 1)
