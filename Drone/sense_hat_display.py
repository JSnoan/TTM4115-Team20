"""Sense HAT 8x8 LED status display for the drone lifecycle."""

PALETTE = {
    ".": [0, 0, 0],
    "G": [0, 255, 90],
    "g": [0, 95, 45],
    "B": [40, 120, 255],
    "C": [0, 220, 220],
    "T": [0, 190, 165],
    "Y": [255, 205, 40],
    "O": [255, 120, 0],
    "R": [255, 25, 25],
    "P": [165, 90, 255],
    "W": [245, 250, 255],
}

PATTERN_ROWS = {
    "charging": [
        "W...Y..W",
        "...YY...",
        "..YYY...",
        ".YYYYY..",
        "...YY...",
        "..YY....",
        ".Y...W..",
        "Y.......",
    ],
    "ready": [
        "........",
        ".WWWWW..",
        "WGGGGGW.",
        "WGGGGGWW",
        "WGGGGGWW",
        "WGGGGGW.",
        ".WWWWW..",
        "........",
    ],
    "outbound": [
        "....B...",
        "...BBB..",
        "..CCB...",
        ".CCCB...",
        "..CCB...",
        "...BBB..",
        "....B...",
        "........",
    ],
    "manual": [
        "...Y....",
        "..YYY...",
        "...Y....",
        "...O....",
        "..OOO...",
        ".OOOOO..",
        ".O.O.O..",
        "........",
    ],
    "arrived": [
        "..PPPP..",
        ".PYYYYP.",
        ".PYYYYP.",
        ".PYYYYP.",
        "..PPPP..",
        "....G...",
        "...GG...",
        "GGGG....",
    ],
    "returning": [
        "...T....",
        "..TTT...",
        ".TTTTT..",
        "TTTTTTT.",
        ".B...B..",
        ".BBBBB..",
        ".BGGGB..",
        "BBBBBBB.",
    ],
    "low_battery": [
        "........",
        ".WWWWW..",
        "WR....W.",
        "WR....WW",
        "WR....WW",
        "WR....W.",
        ".WWWWW..",
        "........",
    ],
    "error": [
        "R......R",
        ".R....R.",
        "..R..R..",
        "...RR...",
        "...RR...",
        "..R..R..",
        ".R....R.",
        "R......R",
    ],
}

DISPLAY_LABELS = {
    "charging": "Docked charging",
    "ready": "Docked fully charged",
    "outbound": "Outbound flight",
    "manual": "Operator control",
    "arrived": "Arrived onsite",
    "returning": "Returning to dock",
    "low_battery": "Low battery warning",
    "error": "Fault or unknown state",
}


def _build_pattern(rows):
    if len(rows) != 8 or any(len(row) != 8 for row in rows):
        raise ValueError("Sense HAT patterns must be exactly 8x8.")

    return [PALETTE[pixel] for row in rows for pixel in row]


PATTERNS = {
    name: _build_pattern(rows)
    for name, rows in PATTERN_ROWS.items()
}


def mode_for_state(state, battery, warning=None):
    """Select the LED pattern without adding new drone states."""
    if warning == "battery_too_low_for_dispatch":
        return "low_battery"

    if battery is not None and battery <= 5:
        return "error"

    if state != "docked" and battery is not None and battery <= 15:
        return "low_battery"

    if state == "docked":
        if battery is not None and battery >= 99:
            return "ready"
        return "charging"

    if state == "navigating":
        return "outbound"

    if state == "manual_control":
        return "manual"

    if state == "waiting_onsite":
        return "arrived"

    if state == "returning":
        return "returning"

    return "error"


class SenseHatDisplay:
    """Shows lifecycle patterns on the Sense HAT matrix when available."""

    def __init__(self, use_mock=False, sense=None):
        self.use_mock = use_mock
        self.sense = sense
        self.error = None
        self.last_mode = None
        self.source = "mock" if use_mock else "fallback"

        if self.use_mock:
            return

        if self.sense is None:
            try:
                from sense_hat import SenseHat

                self.sense = SenseHat()
            except Exception as err:
                self.error = str(err)

        if self.sense is not None:
            self.source = "sense_hat"
            try:
                self.sense.low_light = True
            except Exception:
                pass

    def show(self, mode):
        if mode not in PATTERNS:
            mode = "error"

        status = {
            "available": self.sense is not None,
            "source": self.source,
            "mode": mode,
            "label": DISPLAY_LABELS[mode],
        }

        if self.error:
            status["error"] = self.error

        if self.sense is None:
            if self.use_mock and mode != self.last_mode:
                print(f"Mock Sense HAT display mode: {mode}")
            self.last_mode = mode
            return status

        if mode == self.last_mode:
            return status

        try:
            self.sense.set_pixels(PATTERNS[mode])
            self.last_mode = mode
        except Exception as err:
            self.error = str(err)
            status.update({
                "available": False,
                "source": "sense_hat",
                "error": self.error,
            })

        return status

    def clear(self):
        if self.sense is None:
            return

        try:
            self.sense.clear()
        except Exception:
            pass
