import argparse
import json
import os
import threading
import time
from collections import deque
from datetime import datetime

from flask import Flask, jsonify, render_template, request
import paho.mqtt.client as mqtt


COMMAND_TOPIC = "drone/commands"
STATUS_TOPIC = "drone/status"
MIN_DISPATCH_BATTERY = 90

ALLOWED_COMMANDS = {
    "docked": ["dispatch"],
    "navigating": ["prox_alert", "nav_abort"],
    "manual_control": ["manual_complete", "manual_abort"],
    "waiting_onsite": ["mission_complete"],
    "returning": ["successfully_docked"],
}


class MissionBridge:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.lock = threading.Lock()
        self.events = deque(maxlen=120)
        self.latest_status = {
            "connected": False,
            "state": "unknown",
            "battery": None,
            "pos": None,
            "target": None,
            "telemetry": {},
            "sense_hat": {},
            "sense_hat_display": {},
        }
        self.last_state = None
        self.last_status_at = None
        self.next_emergency_id = 1
        self.next_registration_id = 1
        self.next_delivery_id = 1
        self.emergency_requests = []
        self.registrations = []
        self.delivery_requests = []

        client_id = f"team20_webapp_{os.getpid()}_{int(time.time())}"
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def start(self):
        self.add_event("system", f"Connecting to MQTT broker {self.broker}:{self.port}")
        try:
            self.client.connect(self.broker, self.port)
            self.client.loop_start()
        except Exception as err:
            with self.lock:
                self.latest_status["connected"] = False
            self.add_event("error", f"MQTT connection failed: {err}")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if not getattr(reason_code, "is_failure", False):
            with self.lock:
                self.latest_status["connected"] = True
            client.subscribe(STATUS_TOPIC)
            self.add_event("mqtt", f"Subscribed to {STATUS_TOPIC}")
        else:
            self.add_event("error", f"MQTT connect failed: {reason_code}")

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        with self.lock:
            self.latest_status["connected"] = False
        self.add_event("mqtt", f"Disconnected from broker: {reason_code}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as err:
            self.add_event("error", f"Invalid JSON on {msg.topic}: {err}")
            return

        if msg.topic == STATUS_TOPIC:
            self.handle_status(payload)

    def handle_status(self, payload):
        state = payload.get("state", "unknown")
        with self.lock:
            self.latest_status.update(payload)
            self.latest_status["connected"] = True
            self.last_status_at = time.time()

        if state != self.last_state:
            self.add_event("status", f"Drone state changed to {state}")
            self.last_state = state

    def send_command(self, command, target=None):
        state = self.get_status().get("state", "unknown")
        allowed = ALLOWED_COMMANDS.get(state, [])

        if command not in allowed:
            return {
                "ok": False,
                "error": f"Command {command} is not valid while state is {state}",
                "state": state,
            }

        battery = self.get_status().get("battery")
        if command == "dispatch" and battery is not None and battery < MIN_DISPATCH_BATTERY:
            return {
                "ok": False,
                "error": (
                    f"Battery is {battery:.1f}%. Dispatch requires at least "
                    f"{MIN_DISPATCH_BATTERY}%."
                ),
                "state": state,
            }

        payload = {"command": command}
        if command == "dispatch":
            payload["target"] = target or {"lat": 63.425, "lon": 10.395}

        try:
            self.client.publish(COMMAND_TOPIC, json.dumps(payload))
        except Exception as err:
            self.add_event("error", f"Failed to publish {command}: {err}")
            return {"ok": False, "error": str(err), "state": state}

        self.add_event("command", f"Sent {command}")
        return {"ok": True, "command": command, "payload": payload}

    def create_emergency_request(self, data):
        target = self._parse_target(data)
        if target is None:
            return {"ok": False, "error": "Emergency request needs valid latitude and longitude"}
        origin = self._parse_named_target(data, "origin_lat", "origin_lon") or {
            "lat": 63.42,
            "lon": 10.39,
        }

        request_record = {
            "id": self.next_emergency_id,
            "requester": data.get("requester") or "Unknown requester",
            "contact": data.get("contact") or "No contact provided",
            "need": data.get("need") or "first_aid",
            "priority": data.get("priority") or "urgent",
            "notes": data.get("notes") or "",
            "origin": origin,
            "target": target,
            "status": "created",
            "created_at": datetime.now().strftime("%H:%M:%S"),
        }
        self.next_emergency_id += 1
        self.emergency_requests.append(request_record)
        self.add_event("uc1", f"Emergency request #{request_record['id']} created")
        return {"ok": True, "request": request_record}

    def dispatch_emergency_request(self, request_id):
        request_record = self._find_by_id(self.emergency_requests, request_id)
        if request_record is None:
            return {"ok": False, "error": f"Emergency request #{request_id} not found"}

        result = self.send_command("dispatch", target=request_record["target"])
        if result["ok"]:
            request_record["status"] = "dispatched"
            self.add_event("uc1", f"Emergency request #{request_id} dispatched")
        return result | {"request": request_record}

    def register_requester(self, data):
        target = self._parse_target(data)
        if target is None:
            return {"ok": False, "error": "Registration needs valid drop-off latitude and longitude"}

        medicines = self._parse_medicines(data.get("medicines"))
        approved_medicines = [
            med for med in medicines
            if "morphine" not in med.lower() and "opioid" not in med.lower()
        ]
        declined_medicines = [med for med in medicines if med not in approved_medicines]
        patient_id = data.get("patient_id") or ""
        approved = bool(patient_id.strip()) and not patient_id.lower().startswith("invalid")

        registration = {
            "id": self.next_registration_id,
            "requester": data.get("requester") or "Unknown requester",
            "contact": data.get("contact") or "No contact provided",
            "patient_id": patient_id or "missing",
            "address": data.get("address") or "No address provided",
            "dropoff": target,
            "dropoff_notes": data.get("dropoff_notes") or "No drop-off note",
            "container": data.get("container") or "standard drop-off point",
            "approved_medicines": approved_medicines if approved else [],
            "declined_medicines": declined_medicines if approved else medicines,
            "status": "registered" if approved and approved_medicines else "denied",
            "created_at": datetime.now().strftime("%H:%M:%S"),
        }
        self.next_registration_id += 1
        self.registrations.append(registration)

        if registration["status"] == "registered":
            self.add_event("uc3", f"Requester #{registration['id']} registered")
        else:
            self.add_event("uc3", f"Requester #{registration['id']} denied")

        return {"ok": True, "registration": registration}

    def create_delivery_request(self, data):
        registration_id = int(data.get("registration_id") or 0)
        registration = self._find_by_id(self.registrations, registration_id)
        if registration is None or registration.get("status") != "registered":
            return {"ok": False, "error": "Select a registered requester first"}

        medicine = data.get("medicine") or ""
        if medicine not in registration.get("approved_medicines", []):
            return {"ok": False, "error": "Medicine is not approved for this requester"}

        delivery = {
            "id": self.next_delivery_id,
            "registration_id": registration_id,
            "requester": registration["requester"],
            "medicine": medicine,
            "order_type": "routine_medicine",
            "priority": data.get("priority") or "standard",
            "target": registration["dropoff"],
            "status": "queued",
            "created_at": datetime.now().strftime("%H:%M:%S"),
        }
        self.next_delivery_id += 1
        self.delivery_requests.append(delivery)
        self.add_event("uc2", f"Routine delivery #{delivery['id']} queued")
        return {"ok": True, "delivery": delivery}

    def approve_delivery_request(self, delivery_id):
        delivery = self._find_by_id(self.delivery_requests, delivery_id)
        if delivery is None:
            return {"ok": False, "error": f"Delivery #{delivery_id} not found"}

        delivery["status"] = "approved"
        self.add_event("uc2", f"Routine delivery #{delivery_id} approved")
        return {"ok": True, "delivery": delivery}

    def dispatch_delivery_request(self, delivery_id):
        delivery = self._find_by_id(self.delivery_requests, delivery_id)
        if delivery is None:
            return {"ok": False, "error": f"Delivery #{delivery_id} not found"}
        if delivery["status"] not in ["approved", "queued"]:
            return {"ok": False, "error": f"Delivery #{delivery_id} is already {delivery['status']}"}

        result = self.send_command("dispatch", target=delivery["target"])
        if result["ok"]:
            delivery["status"] = "dispatched"
            self.add_event("uc2", f"Routine delivery #{delivery_id} dispatched")
        return result | {"delivery": delivery}

    def get_usecases(self):
        return {
            "emergency_requests": list(self.emergency_requests),
            "registrations": list(self.registrations),
            "delivery_requests": list(self.delivery_requests),
        }

    def get_status(self):
        with self.lock:
            status = dict(self.latest_status)
            status["last_status_age_s"] = self.status_age()
            status["allowed_commands"] = ALLOWED_COMMANDS.get(
                status.get("state", "unknown"),
                [],
            )
            return status

    def status_age(self):
        if self.last_status_at is None:
            return None
        return round(time.time() - self.last_status_at, 1)

    def get_events(self):
        with self.lock:
            return list(self.events)

    def add_event(self, kind, message):
        event = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "kind": kind,
            "message": message,
        }
        with self.lock:
            self.events.appendleft(event)

    def _parse_target(self, data):
        try:
            lat = float(data.get("lat"))
            lon = float(data.get("lon"))
        except (TypeError, ValueError):
            return None
        return {"lat": lat, "lon": lon}

    def _parse_named_target(self, data, lat_key, lon_key):
        try:
            lat = float(data.get(lat_key))
            lon = float(data.get(lon_key))
        except (TypeError, ValueError):
            return None
        return {"lat": lat, "lon": lon}

    def _parse_medicines(self, value):
        if isinstance(value, list):
            medicines = value
        else:
            medicines = str(value or "").split(",")
        return [medicine.strip() for medicine in medicines if medicine.strip()]

    def _find_by_id(self, records, record_id):
        try:
            wanted_id = int(record_id)
        except (TypeError, ValueError):
            return None
        for record in records:
            if record["id"] == wanted_id:
                return record
        return None


def create_app(bridge):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/status")
    def api_status():
        return jsonify(bridge.get_status())

    @app.route("/api/events")
    def api_events():
        return jsonify({"events": bridge.get_events()})

    @app.route("/api/usecases")
    def api_usecases():
        return jsonify(bridge.get_usecases())

    @app.route("/api/command", methods=["POST"])
    def api_command():
        data = request.get_json(silent=True) or {}
        command = data.get("command")
        target = data.get("target")

        if not command:
            return jsonify({"ok": False, "error": "Missing command"}), 400

        result = bridge.send_command(command, target=target)
        status_code = 200 if result["ok"] else 409
        return jsonify(result), status_code

    @app.route("/api/emergency", methods=["POST"])
    def api_create_emergency():
        result = bridge.create_emergency_request(request.get_json(silent=True) or {})
        return jsonify(result), 200 if result["ok"] else 400

    @app.route("/api/emergency/<int:request_id>/dispatch", methods=["POST"])
    def api_dispatch_emergency(request_id):
        result = bridge.dispatch_emergency_request(request_id)
        return jsonify(result), 200 if result["ok"] else 409

    @app.route("/api/register", methods=["POST"])
    def api_register():
        result = bridge.register_requester(request.get_json(silent=True) or {})
        return jsonify(result), 200 if result["ok"] else 400

    @app.route("/api/delivery", methods=["POST"])
    def api_create_delivery():
        result = bridge.create_delivery_request(request.get_json(silent=True) or {})
        return jsonify(result), 200 if result["ok"] else 400

    @app.route("/api/delivery/<int:delivery_id>/approve", methods=["POST"])
    def api_approve_delivery(delivery_id):
        result = bridge.approve_delivery_request(delivery_id)
        return jsonify(result), 200 if result["ok"] else 404

    @app.route("/api/delivery/<int:delivery_id>/dispatch", methods=["POST"])
    def api_dispatch_delivery(delivery_id):
        result = bridge.dispatch_delivery_request(delivery_id)
        return jsonify(result), 200 if result["ok"] else 409

    return app


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Team 20 web control app.")
    parser.add_argument("--broker", default=os.getenv("MQTT_BROKER", "mqtt20.item.ntnu.no"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--host", default=os.getenv("WEBAPP_HOST", "127.0.0.1"))
    parser.add_argument("--web-port", type=int, default=int(os.getenv("WEBAPP_PORT", "5000")))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    bridge = MissionBridge(args.broker, args.port)
    bridge.start()
    app = create_app(bridge)

    try:
        app.run(host=args.host, port=args.web_port, debug=False)
    finally:
        bridge.stop()
