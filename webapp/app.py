import argparse
import json
import logging
import os
import threading
import time
import uuid

from flask import Flask, jsonify, render_template, request
import paho.mqtt.client as mqtt


APP_REQUEST_TOPIC = "team20/app/requests"
SERVER_STATUS_TOPIC = "team20/server/status"
SERVER_EVENTS_TOPIC = "team20/server/events"
SERVER_USECASES_TOPIC = "team20/server/usecases"
SERVER_RESPONSES_TOPIC = "team20/server/responses"


class WebMqttBridge:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.lock = threading.RLock()
        self.pending_requests = {}
        self.latest_status = {
            "connected": False,
            "server_online": False,
            "state": "unknown",
            "battery": None,
            "pos": None,
            "target": None,
            "telemetry": {},
            "sense_hat": {},
            "sense_hat_display": {},
            "allowed_commands": [],
            "last_status_age_s": None,
        }
        self.events = []
        self.usecases = {
            "emergency_requests": [],
            "registrations": [],
            "delivery_requests": [],
        }
        self.last_status_received_at = None

        client_id = f"team20_webapp_{os.getpid()}_{int(time.time())}"
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def start(self):
        try:
            self.client.connect(self.broker, self.port)
            self.client.loop_start()
        except Exception as err:
            with self.lock:
                self.latest_status["connected"] = False
                self.latest_status["server_online"] = False
            self._add_local_event("error", f"Web app could not connect to MQTT broker: {err}")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if getattr(reason_code, "is_failure", False):
            self._add_local_event("error", f"Web app MQTT connection failed: {reason_code}")
            return

        client.subscribe(SERVER_STATUS_TOPIC)
        client.subscribe(SERVER_EVENTS_TOPIC)
        client.subscribe(SERVER_USECASES_TOPIC)
        client.subscribe(SERVER_RESPONSES_TOPIC)
        self._add_local_event("mqtt", "Web app connected to MQTT and subscribed to mission server topics")

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        with self.lock:
            self.latest_status["connected"] = False
            self.latest_status["server_online"] = False
        self._add_local_event("mqtt", f"Web app disconnected from MQTT broker: {reason_code}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as err:
            self._add_local_event("error", f"Invalid JSON on {msg.topic}: {err}")
            return

        if msg.topic == SERVER_STATUS_TOPIC:
            with self.lock:
                self.latest_status.update(payload)
                self.last_status_received_at = time.time()
            return

        if msg.topic == SERVER_EVENTS_TOPIC:
            events = payload.get("events", [])
            with self.lock:
                self.events = events
            return

        if msg.topic == SERVER_USECASES_TOPIC:
            with self.lock:
                self.usecases = {
                    "emergency_requests": payload.get("emergency_requests", []),
                    "registrations": payload.get("registrations", []),
                    "delivery_requests": payload.get("delivery_requests", []),
                }
            return

        if msg.topic == SERVER_RESPONSES_TOPIC:
            request_id = payload.get("request_id")
            with self.lock:
                pending = self.pending_requests.get(request_id)
                if pending:
                    pending["result"] = payload.get("result", {"ok": False, "error": "Empty server response"})
                    pending["event"].set()

    def send_request(self, action, data=None, timeout_s=5.0):
        request_id = f"req-{os.getpid()}-{uuid.uuid4().hex[:10]}"
        waiter = {"event": threading.Event(), "result": None}

        with self.lock:
            self.pending_requests[request_id] = waiter

        payload = {
            "request_id": request_id,
            "action": action,
            "data": data or {},
            "timestamp": time.time(),
        }

        try:
            self.client.publish(APP_REQUEST_TOPIC, json.dumps(payload))
        except Exception as err:
            with self.lock:
                self.pending_requests.pop(request_id, None)
            return {"ok": False, "error": f"Could not publish request to mission server: {err}"}

        if not waiter["event"].wait(timeout_s):
            with self.lock:
                self.pending_requests.pop(request_id, None)
            return {
                "ok": False,
                "error": "Mission server did not reply. Start MqttServer.py and try again.",
                "timeout": True,
            }

        with self.lock:
            self.pending_requests.pop(request_id, None)
            return waiter["result"] or {"ok": False, "error": "Mission server returned no result"}

    def get_status(self):
        with self.lock:
            status = dict(self.latest_status)
            if self.last_status_received_at is not None and status.get("server_online"):
                status["web_bridge_age_s"] = round(time.time() - self.last_status_received_at, 1)
            return status

    def get_events(self):
        with self.lock:
            return list(self.events)

    def get_usecases(self):
        with self.lock:
            return {
                "emergency_requests": list(self.usecases["emergency_requests"]),
                "registrations": list(self.usecases["registrations"]),
                "delivery_requests": list(self.usecases["delivery_requests"]),
            }

    def _add_local_event(self, kind, message):
        event = {
            "id": f"web-{int(time.time() * 1000)}",
            "time": time.strftime("%H:%M:%S"),
            "timestamp": time.time(),
            "kind": kind,
            "message": message,
        }
        with self.lock:
            self.events.insert(0, event)
            self.events = self.events[:40]


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

        result = bridge.send_request("command", {"command": command, "target": target})
        return jsonify(result), status_code_for(result)

    @app.route("/api/emergency", methods=["POST"])
    def api_create_emergency():
        result = bridge.send_request("create_emergency", request.get_json(silent=True) or {})
        return jsonify(result), status_code_for(result)

    @app.route("/api/emergency/<int:request_id>/dispatch", methods=["POST"])
    def api_dispatch_emergency(request_id):
        result = bridge.send_request("dispatch_emergency", {"request_id": request_id})
        return jsonify(result), status_code_for(result)

    @app.route("/api/orders/dispatch", methods=["POST"])
    def api_dispatch_order():
        result = bridge.send_request("dispatch_order", request.get_json(silent=True) or {})
        return jsonify(result), status_code_for(result)

    @app.route("/api/register", methods=["POST"])
    def api_register():
        result = bridge.send_request("register", request.get_json(silent=True) or {})
        return jsonify(result), status_code_for(result)

    @app.route("/api/delivery", methods=["POST"])
    def api_create_delivery():
        result = bridge.send_request("create_delivery", request.get_json(silent=True) or {})
        return jsonify(result), status_code_for(result)

    @app.route("/api/delivery/<int:delivery_id>/approve", methods=["POST"])
    def api_approve_delivery(delivery_id):
        result = bridge.send_request("approve_delivery", {"delivery_id": delivery_id})
        return jsonify(result), status_code_for(result)

    @app.route("/api/delivery/<int:delivery_id>/dispatch", methods=["POST"])
    def api_dispatch_delivery(delivery_id):
        result = bridge.send_request("dispatch_delivery", {"delivery_id": delivery_id})
        return jsonify(result), status_code_for(result)

    @app.route("/api/restricted/solve", methods=["POST"])
    def api_solve_restricted():
        result = bridge.send_request("solve_restricted_delivery", request.get_json(silent=True) or {})
        return jsonify(result), status_code_for(result)

    return app


def status_code_for(result):
    if result.get("ok"):
        return 200
    if result.get("timeout"):
        return 504
    return 409


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Team 20 web control app.")
    parser.add_argument("--broker", default=os.getenv("MQTT_BROKER", "mqtt20.item.ntnu.no"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--host", default=os.getenv("WEBAPP_HOST", "127.0.0.1"))
    parser.add_argument("--web-port", type=int, default=int(os.getenv("WEBAPP_PORT", "5000")))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    bridge = WebMqttBridge(args.broker, args.port)
    bridge.start()
    app = create_app(bridge)

    try:
        app.run(host=args.host, port=args.web_port, debug=False)
    finally:
        bridge.stop()
