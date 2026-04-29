import argparse
import json
import math
import os
import threading
import time
from collections import deque
from datetime import datetime

import paho.mqtt.client as mqtt


COMMAND_TOPIC = "drone/commands"
DRONE_STATUS_TOPIC = "drone/status"

APP_REQUEST_TOPIC = "team20/app/requests"
SERVER_STATUS_TOPIC = "team20/server/status"
SERVER_EVENTS_TOPIC = "team20/server/events"
SERVER_USECASES_TOPIC = "team20/server/usecases"
SERVER_RESPONSES_TOPIC = "team20/server/responses"

BASE_POSITION = {"lat": 63.42, "lon": 10.39}
MIN_DISPATCH_BATTERY = 90
PROXIMITY_PROGRESS_THRESHOLD = 0.99
MANUAL_DECISION_DELAY_SECONDS = 2.0
ROUTINE_DROPOFF_SECONDS = 5.0
BASE_DESTINATION_MIN_DISTANCE_M = 10
BASE_DOCKED_RADIUS_M = 5
RESTRICTED_ZONE_RADIUS_M = 25
PROCESS_EMERGENCY = "emergency_first_aid"
PROCESS_ROUTINE = "routine_medicine"
RESTRICTED_ZONES = [
    {"lat": 63.440712, "lon": 10.403904},
    {"lat": 63.422439, "lon": 10.442377},
    {"lat": 63.415372, "lon": 10.351003},
]

ALLOWED_COMMANDS = {
    "docked": ["dispatch"],
    "navigating": ["prox_alert", "nav_abort", "dropoff_complete"],
    "manual_control": ["manual_complete", "manual_abort"],
    "waiting_onsite": ["mission_complete"],
    "returning": ["successfully_docked"],
}


class MqttServer:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.lock = threading.RLock()
        self.events = deque(maxlen=160)
        self.connected = False
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
        self.last_status_at = None
        self.last_state = None
        self.next_event_id = 1
        self.next_emergency_id = 1
        self.next_registration_id = 1
        self.next_delivery_id = 1
        self.emergency_requests = []
        self.registrations = []
        self.delivery_requests = []
        self.active_mission = None
        self.proximity_sent = False
        self.manual_decision_timer = None
        self.routine_dropoff_timer = None

        client_id = f"team20_server_{os.getpid()}_{int(time.time())}"
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if not getattr(reason_code, "is_failure", False):
            self.connected = True
            print(f"Connected to MQTT Broker: {self.broker}:{self.port}")
            self.client.subscribe(DRONE_STATUS_TOPIC)
            self.client.subscribe(APP_REQUEST_TOPIC)
            print(f"Subscribed to topics: {DRONE_STATUS_TOPIC}, {APP_REQUEST_TOPIC}")
            self.add_event("mqtt", "Mission server connected to MQTT broker")
            self.publish_all()
        else:
            print(f"Connection failed with code {reason_code}")

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        self.add_event("mqtt", f"Mission server disconnected from broker: {reason_code}")
        self.publish_status()

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as err:
            self.add_event("error", f"Invalid JSON on {msg.topic}: {err}")
            return

        if msg.topic == DRONE_STATUS_TOPIC:
            self.handle_status(payload)
        elif msg.topic == APP_REQUEST_TOPIC:
            self.handle_app_request(payload)

    def handle_status(self, data):
        state = data.get("state", "unknown")
        battery = data.get("battery")
        pos = data.get("pos")

        with self.lock:
            self.latest_status.update(data)
            self.latest_status["connected"] = self.connected
            self.last_status_at = time.time()

        if state != self.last_state:
            self.add_event("status", f"Drone state changed to {state}")
            self._handle_state_change(state)
            self.last_state = state

        print(f"Drone status: state={state}, battery={battery}, pos={pos}")
        self._maybe_trigger_proximity(data)
        self.publish_status()

    def handle_app_request(self, payload):
        request_id = payload.get("request_id")
        action = payload.get("action")
        data = payload.get("data") or {}

        try:
            if action == "command":
                result = self.send_command(data.get("command"), target=data.get("target"))
            elif action == "create_emergency":
                result = self.create_emergency_request(data)
            elif action == "dispatch_order":
                result = self.dispatch_order(data.get("process_type"), data.get("order_id"))
            elif action == "dispatch_emergency":
                result = self.dispatch_emergency_request(data.get("request_id"))
            elif action == "register":
                result = self.register_requester(data)
            elif action == "create_delivery":
                result = self.create_delivery_request(data)
            elif action == "approve_delivery":
                result = self.approve_delivery_request(data.get("delivery_id"))
            elif action == "dispatch_delivery":
                result = self.dispatch_delivery_request(data.get("delivery_id"))
            elif action == "solve_restricted_delivery":
                result = self.solve_restricted_delivery(data.get("decision"))
            else:
                result = {"ok": False, "error": f"Unknown server action: {action}"}
        except Exception as err:
            result = {"ok": False, "error": str(err)}

        self.publish_all()
        self.publish_response(request_id, result)

    def send_command(self, command, target=None, mission=None):
        if not command:
            return {"ok": False, "error": "Missing command"}

        status = self.get_status()
        state = status.get("state", "unknown")
        allowed = ALLOWED_COMMANDS.get(state, [])

        if command not in allowed:
            return {
                "ok": False,
                "error": f"Command {command} is not valid while state is {state}",
                "state": state,
            }

        if command == "successfully_docked":
            distance_to_base = self._distance_to_base_from_status(status)
            if distance_to_base is None or distance_to_base > BASE_DOCKED_RADIUS_M:
                distance_text = "unknown" if distance_to_base is None else f"{distance_to_base:.1f} m"
                return {
                    "ok": False,
                    "error": (
                        "Drone can only be confirmed docked at the base station. "
                        f"Current distance to base: {distance_text}."
                    ),
                    "state": state,
                }

        battery = status.get("battery")
        if command == "dispatch" and battery is not None and battery < MIN_DISPATCH_BATTERY:
            return {
                "ok": False,
                "error": (
                    f"Battery is {battery:.1f}%. Dispatch requires at least "
                    f"{MIN_DISPATCH_BATTERY}%."
                ),
                "state": state,
            }

        command_payload = {"command": command}
        if command == "dispatch":
            command_payload["target"] = target or {"lat": 63.425, "lon": 10.395}
            self.proximity_sent = False
            self._cancel_manual_decision_timer()
            self._cancel_routine_dropoff_timer()

        if mission:
            command_payload["mission"] = mission

        self.client.publish(COMMAND_TOPIC, json.dumps(command_payload))
        print(f"Sent command to drone: {command_payload}")
        self.add_event("command", f"Sent {command}")
        return {"ok": True, "command": command, "payload": command_payload}

    def create_emergency_request(self, data):
        target = self._parse_target(data)
        if target is None:
            return {"ok": False, "error": "Emergency request needs valid latitude and longitude"}
        validation = self._validate_destination(target)
        if not validation["ok"]:
            return validation

        request_record = {
            "id": self.next_emergency_id,
            "process_type": PROCESS_EMERGENCY,
            "requester": data.get("requester") or "Unknown requester",
            "contact": data.get("contact") or "No contact provided",
            "need": data.get("need") or "first_aid",
            "priority": data.get("priority") or "urgent",
            "notes": data.get("notes") or "",
            "origin": dict(BASE_POSITION),
            "target": target,
            "restricted_zone": self._is_restricted_destination(target),
            "status": "created",
            "created_at": datetime.now().strftime("%H:%M:%S"),
        }
        self.next_emergency_id += 1
        self.emergency_requests.append(request_record)
        self.add_event("uc1", f"Emergency request #{request_record['id']} created")
        return {"ok": True, "request": request_record}

    def dispatch_emergency_request(self, request_id):
        result = self.dispatch_order(PROCESS_EMERGENCY, request_id)
        if "order" in result:
            result["request"] = result["order"]
        return result

    def register_requester(self, data):
        target = self._parse_target(data)
        if target is None:
            return {"ok": False, "error": "Registration needs valid drop-off latitude and longitude"}
        validation = self._validate_destination(target)
        if not validation["ok"]:
            return validation

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
            "restricted_zone": self._is_restricted_destination(target),
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
            "process_type": PROCESS_ROUTINE,
            "registration_id": registration_id,
            "requester": registration["requester"],
            "medicine": medicine,
            "order_type": "routine_medicine",
            "priority": data.get("priority") or "standard",
            "target": registration["dropoff"],
            "restricted_zone": bool(registration.get("restricted_zone")),
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
        result = self.dispatch_order(PROCESS_ROUTINE, delivery_id)
        if "order" in result:
            result["delivery"] = result["order"]
        return result

    def dispatch_order(self, process_type, order_id):
        if process_type == PROCESS_EMERGENCY:
            order = self._find_by_id(self.emergency_requests, order_id)
            if order is None:
                return {"ok": False, "error": f"Emergency request #{order_id} not found"}
            valid_statuses = ["created"]
            event_kind = "uc1"
            event_message = f"Emergency request #{order_id} dispatched"
        elif process_type == PROCESS_ROUTINE:
            order = self._find_by_id(self.delivery_requests, order_id)
            if order is None:
                return {"ok": False, "error": f"Routine delivery #{order_id} not found"}
            valid_statuses = ["queued", "approved"]
            event_kind = "uc2"
            event_message = f"Routine delivery #{order_id} dispatched"
        else:
            return {"ok": False, "error": "Unknown process type"}

        if order["status"] not in valid_statuses:
            return {"ok": False, "error": f"Order #{order_id} is {order['status']} and cannot be dispatched"}

        restricted_zone = self._is_restricted_destination(order["target"])
        order["restricted_zone"] = restricted_zone

        mission = {
            "process_type": process_type,
            "order_id": order["id"],
            "restricted_zone": restricted_zone,
        }
        result = self.send_command("dispatch", target=order["target"], mission=mission)
        if result["ok"]:
            order["status"] = "dispatched"
            self.active_mission = {
                **mission,
                "target": order["target"],
                "phase": "navigating",
                "label": self._mission_label(process_type, order),
                "started_at": datetime.now().strftime("%H:%M:%S"),
            }
            zone_note = "restricted destination" if restricted_zone else "standard destination"
            self.add_event("order_dispatched", f"{event_message} ({zone_note})")
            self.add_event(event_kind, event_message)
            self.publish_all()

        return result | {"order": order, "active_mission": self.active_mission}

    def solve_restricted_delivery(self, decision):
        mission = self.active_mission
        if not mission or mission.get("process_type") != PROCESS_ROUTINE:
            return {"ok": False, "error": "No routine restricted delivery is waiting for resolution"}
        if mission.get("phase") != "restricted_alert":
            return {"ok": False, "error": "The active routine delivery is not in restricted alert"}

        delivery = self._find_by_id(self.delivery_requests, mission.get("order_id"))
        if delivery is None:
            return {"ok": False, "error": "Active routine delivery not found"}

        if decision == "abort":
            result = self.send_command("manual_abort")
            if result["ok"]:
                delivery["status"] = "aborted_restricted"
                mission["phase"] = "returning"
                self.add_event("manual_resolution_aborted", "Restricted zone alert aborted. Drone is returning to base.")
                self.publish_all()
            return result | {"delivery": delivery, "active_mission": mission}

        if decision != "complete":
            return {"ok": False, "error": "Decision must be complete or abort"}

        result = self.send_command("manual_complete")
        if not result["ok"]:
            return result | {"delivery": delivery, "active_mission": mission}

        delivery["status"] = "dropping"
        mission["phase"] = "dropping_medicine"
        self.add_event("manual_resolution_completed", "Restricted zone alert completed by operator.")
        self.add_event(
            "dropping_medicine",
            "Dropping medicine package. Drone will return to base in 5 seconds.",
            popup=True,
            title="Dropping medicine",
            duration_ms=int(ROUTINE_DROPOFF_SECONDS * 1000),
        )
        self._schedule_routine_dropoff_completion(command="mission_complete")
        self.publish_all()
        return result | {"delivery": delivery, "active_mission": mission}

    def _maybe_trigger_proximity(self, status):
        if self.proximity_sent or status.get("state") != "navigating":
            return

        pos = self._normalize_coord(status.get("pos"))
        target = self._normalize_coord(status.get("target"))
        if not pos or not target:
            return

        total_distance = self._distance_m(BASE_POSITION, target)
        if total_distance is None or total_distance <= 1:
            return

        travelled = self._distance_m(BASE_POSITION, pos) or 0
        progress = min(max(travelled / total_distance, 0), 1)

        if progress < PROXIMITY_PROGRESS_THRESHOLD:
            return

        self.proximity_sent = True
        restricted_destination = self._is_restricted_destination(target)
        mission = self.active_mission or {
            "process_type": PROCESS_EMERGENCY,
            "order_id": None,
            "target": target,
            "phase": "navigating",
            "label": "Direct drone mission",
        }
        mission["restricted_zone"] = bool(mission.get("restricted_zone")) or restricted_destination
        mission["target"] = mission.get("target") or target

        if mission.get("restricted_zone"):
            self.add_event(
                "restricted_zone_detected",
                "Restricted zone detected at the final delivery destination.",
                popup=True,
                title="Restricted zone",
                duration_ms=5000,
            )

        if mission.get("process_type") == PROCESS_ROUTINE and not mission.get("restricted_zone"):
            mission["phase"] = "delivering_medicine"
            self._set_active_order_status("delivering")
            self.add_event(
                "routine_delivery_started",
                "Delivering medicine package. Drone will return to base in 5 seconds.",
                popup=True,
                title="Delivering medicine",
                duration_ms=int(ROUTINE_DROPOFF_SECONDS * 1000),
            )
            self._schedule_routine_dropoff_completion(command="dropoff_complete")
            self.publish_all()
            return

        result = self.send_command("prox_alert")
        if not result["ok"]:
            self.add_event("warning", f"Could not trigger proximity alert: {result['error']}")
            return

        if mission.get("process_type") == PROCESS_ROUTINE:
            mission["phase"] = "restricted_alert"
            self._set_active_order_status("restricted_alert")
            self.add_event(
                "manual_resolution_required",
                "Routine medicine delivery needs operator resolution before returning.",
            )
        else:
            mission["phase"] = "manual_guidance"
            if not mission.get("restricted_zone"):
                self.add_event(
                    "manual_guidance_required",
                    "Drone reached final approach. Mission server is completing guidance.",
                    popup=True,
                    title="Final approach reached",
                    duration_ms=int(MANUAL_DECISION_DELAY_SECONDS * 1000),
                )
            self._schedule_manual_decision()

        self.active_mission = mission
        self.publish_all()

    def _schedule_manual_decision(self):
        self._cancel_manual_decision_timer()
        self.manual_decision_timer = threading.Timer(
            MANUAL_DECISION_DELAY_SECONDS,
            self._auto_complete_manual_guidance,
        )
        self.manual_decision_timer.daemon = True
        self.manual_decision_timer.start()

    def _cancel_manual_decision_timer(self):
        if self.manual_decision_timer is not None:
            self.manual_decision_timer.cancel()
            self.manual_decision_timer = None

    def _schedule_routine_dropoff_completion(self, command):
        self._cancel_routine_dropoff_timer()
        self.routine_dropoff_timer = threading.Timer(
            ROUTINE_DROPOFF_SECONDS,
            self._complete_routine_dropoff,
            kwargs={"command": command},
        )
        self.routine_dropoff_timer.daemon = True
        self.routine_dropoff_timer.start()

    def _cancel_routine_dropoff_timer(self):
        if self.routine_dropoff_timer is not None:
            self.routine_dropoff_timer.cancel()
            self.routine_dropoff_timer = None

    def _auto_complete_manual_guidance(self):
        if self.get_status().get("state") != "manual_control":
            return

        result = self.send_command("manual_complete")
        if result["ok"]:
            self.add_event("auto_decision", "Manual guidance completed automatically by mission server")

    def _complete_routine_dropoff(self, command):
        result = self.send_command(command)
        if result["ok"]:
            self._set_active_order_status("returning")
            if self.active_mission:
                self.active_mission["phase"] = "returning"
            self.add_event("routine_delivery_completed", "Medicine delivery completed. Drone is returning to base.")
            self.publish_all()

    def _handle_state_change(self, state):
        if not self.active_mission:
            return

        if state == "returning":
            self.active_mission["phase"] = "returning"
            self._set_active_order_status("returning")
            self.add_event("returning_to_base", "Drone is returning to base.")

        if state == "docked" and self.last_state == "returning":
            self._set_active_order_status("completed")
            self.active_mission["phase"] = "completed"
            self.add_event("mission_completed", "Mission completed and drone docked at base.")
            self.active_mission = None
            self.proximity_sent = False

    def get_usecases(self):
        return {
            "emergency_requests": list(self.emergency_requests),
            "registrations": list(self.registrations),
            "delivery_requests": list(self.delivery_requests),
        }

    def get_status(self):
        with self.lock:
            status = dict(self.latest_status)
            status["connected"] = self.connected
            status["last_status_age_s"] = self.status_age()
            status["allowed_commands"] = ALLOWED_COMMANDS.get(
                status.get("state", "unknown"),
                [],
            )
            status["server_online"] = True
            status["active_mission"] = dict(self.active_mission) if self.active_mission else None
            status["restricted_zones"] = RESTRICTED_ZONES
            return status

    def status_age(self):
        if self.last_status_at is None:
            return None
        return round(time.time() - self.last_status_at, 1)

    def add_event(self, kind, message, popup=False, title=None, duration_ms=None):
        with self.lock:
            event = {
                "id": self.next_event_id,
                "time": datetime.now().strftime("%H:%M:%S"),
                "timestamp": time.time(),
                "kind": kind,
                "message": message,
            }
            self.next_event_id += 1
            if popup:
                event["popup"] = True
                event["title"] = title or message
                event["duration_ms"] = duration_ms or 2000
            self.events.appendleft(event)

        self.publish_events()

    def publish_response(self, request_id, result):
        if not request_id:
            return
        payload = {
            "request_id": request_id,
            "result": result,
            "timestamp": time.time(),
        }
        self.client.publish(SERVER_RESPONSES_TOPIC, json.dumps(payload))

    def publish_status(self):
        self.client.publish(SERVER_STATUS_TOPIC, json.dumps(self.get_status()), retain=True)

    def publish_events(self):
        with self.lock:
            payload = {"events": list(self.events)}
        self.client.publish(SERVER_EVENTS_TOPIC, json.dumps(payload), retain=True)

    def publish_usecases(self):
        self.client.publish(SERVER_USECASES_TOPIC, json.dumps(self.get_usecases()), retain=True)

    def publish_all(self):
        self.publish_status()
        self.publish_events()
        self.publish_usecases()

    def publish_offline(self):
        payload = self.get_status()
        payload["connected"] = False
        payload["server_online"] = False
        self.client.publish(SERVER_STATUS_TOPIC, json.dumps(payload), retain=True)

    def _parse_target(self, data):
        try:
            lat = float(data.get("lat"))
            lon = float(data.get("lon"))
        except (TypeError, ValueError):
            return None
        return {"lat": lat, "lon": lon}

    def _validate_destination(self, target):
        distance_to_base = self._distance_m(BASE_POSITION, target)
        if distance_to_base is not None and distance_to_base < BASE_DESTINATION_MIN_DISTANCE_M:
            return {
                "ok": False,
                "error": "Delivery destination cannot be the same as the base station.",
            }
        return {"ok": True}

    def _is_restricted_destination(self, target):
        for zone in RESTRICTED_ZONES:
            distance = self._distance_m(target, zone)
            if distance is not None and distance <= RESTRICTED_ZONE_RADIUS_M:
                return True
        return False

    def _distance_to_base_from_status(self, status):
        telemetry = status.get("telemetry") or {}
        telemetry_distance = telemetry.get("distance_to_base_m")
        try:
            if telemetry_distance is not None:
                return float(telemetry_distance)
        except (TypeError, ValueError):
            pass

        pos = self._normalize_coord(status.get("pos"))
        if not pos:
            return None
        return self._distance_m(pos, BASE_POSITION)

    def _set_active_order_status(self, status):
        if not self.active_mission:
            return

        records = (
            self.emergency_requests
            if self.active_mission.get("process_type") == PROCESS_EMERGENCY
            else self.delivery_requests
        )
        order = self._find_by_id(records, self.active_mission.get("order_id"))
        if order is not None:
            order["status"] = status

    def _mission_label(self, process_type, order):
        if process_type == PROCESS_EMERGENCY:
            return f"Emergency #{order['id']} · {order.get('requester', 'Unknown requester')}"
        return f"Routine #{order['id']} · {order.get('requester', 'Unknown requester')} · {order.get('medicine', 'medicine')}"

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

    def _normalize_coord(self, value):
        if isinstance(value, list) and len(value) >= 2:
            try:
                return {"lat": float(value[0]), "lon": float(value[1])}
            except (TypeError, ValueError):
                return None

        if isinstance(value, dict):
            try:
                return {"lat": float(value["lat"]), "lon": float(value["lon"])}
            except (KeyError, TypeError, ValueError):
                return None

        return None

    def _distance_m(self, first, second):
        first = self._normalize_coord(first)
        second = self._normalize_coord(second)
        if not first or not second:
            return None

        earth_radius_m = 6371000
        lat1 = math.radians(first["lat"])
        lat2 = math.radians(second["lat"])
        delta_lat = math.radians(second["lat"] - first["lat"])
        delta_lon = math.radians(second["lon"] - first["lon"])
        haversine = (
            (math.sin(delta_lat / 2) ** 2)
            + math.cos(lat1) * math.cos(lat2) * (math.sin(delta_lon / 2) ** 2)
        )
        return 2 * earth_radius_m * math.atan2(haversine ** 0.5, (1 - haversine) ** 0.5)

    def start(self):
        print(f"Starting MQTT Server on {self.broker}:{self.port}")
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

        try:
            while True:
                user_input = input("server> ").strip()

                if user_input == "dispatch":
                    self.send_command("dispatch", target={"lat": 63.425, "lon": 10.395})

                elif user_input == "abort":
                    state = self.get_status().get("state")
                    command = "nav_abort" if state == "navigating" else "manual_abort"
                    result = self.send_command(command)
                    if not result["ok"]:
                        print(result["error"])

                elif user_input == "complete":
                    result = self.send_command("manual_complete")
                    if not result["ok"]:
                        print(result["error"])

                elif user_input == "return":
                    result = self.send_command("mission_complete")
                    if not result["ok"]:
                        print(result["error"])

                elif user_input == "dock":
                    result = self.send_command("successfully_docked")
                    if not result["ok"]:
                        print(result["error"])

                elif user_input == "status":
                    print(json.dumps(self.get_status(), indent=2))

                elif user_input == "events":
                    print(json.dumps(list(self.events), indent=2))

                elif user_input == "quit":
                    break

                else:
                    print("Commands: dispatch, abort, complete, return, dock, status, events, quit")

        except KeyboardInterrupt:
            pass
        finally:
            self._cancel_manual_decision_timer()
            self._cancel_routine_dropoff_timer()
            self.publish_offline()
            self.client.loop_stop()
            self.client.disconnect()


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Team 20 MQTT mission server.")
    parser.add_argument("--broker", default=os.getenv("MQTT_BROKER", "mqtt20.item.ntnu.no"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    server = MqttServer(args.broker, args.port)
    server.start()
