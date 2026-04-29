import paho.mqtt.client as mqtt
import time
import json
import argparse
import os
import threading
import stmpy
from droneLogic import DroneLogic
from sense_reader import SenseReader
from sense_hat_display import SenseHatDisplay, mode_for_state
from telemetry import TelemetrySimulator, distance_meters

MIN_DISPATCH_BATTERY = 90
BASE_DOCKED_RADIUS_M = 5
DISPLAY_WARNING_SECONDS = 5
AUTO_RETURN_BATTERY_THRESHOLD = 25

class DroneClient:
    def __init__(
        self,
        broker,
        port,
        drone_id="drone_1",
        telemetry_interval=5.0,
        auto_proximity=False,
        mock_sense_hat=False,
    ):
        self.broker = broker
        self.port = port
        self.drone_id = drone_id
        self.telemetry_interval = telemetry_interval
        self.auto_proximity = auto_proximity
        self.proximity_sent = False
        self.low_battery_return_sent = False
        self.display_warning = None
        self.display_warning_until = 0
        self.lock = threading.Lock()
        self.client = mqtt.Client(client_id=f"team20_{drone_id}")
        self.client.drone_id = drone_id
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.logic = DroneLogic(self.client)
        self.sense_reader = SenseReader()
        self.sense_display = SenseHatDisplay(
            use_mock=mock_sense_hat,
            sense=self.sense_reader.sense,
        )
        self.telemetry = TelemetrySimulator(self.logic)
        self.stm_driver = stmpy.Driver()
        self.stm_driver.add_machine(self.logic.stm)


    def on_connect(self, client, userdata, flags, rc):
        print(f"Drone connected to MQTT Broker: {self.broker}:{self.port}")
        self.client.subscribe("drone/commands")
        print("Subscribed to topic: drone/commands")

    def on_message(self, client, userdata, msg):
        #debugging
        print(f"RAW MESSAGE: topic={msg.topic}, payload={msg.payload}")
        
        
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print("Error with message:", e)
            return
        
        command = payload.get("command")
        current_state = self.logic.current_state
        
        allowed_commands = {
            "docked": ["dispatch"],
            "navigating": ["prox_alert", "nav_abort", "dropoff_complete"],
            "manual_control": ["manual_complete", "manual_abort"],
            "waiting_onsite": ["mission_complete"],
            "returning": ["successfully_docked"],
        }

        if command not in allowed_commands.get(current_state, []):
            print(f"Ignored invalid command '{command}' while in state '{current_state}'")
            return

        if command == "dispatch" and self.logic.battery < MIN_DISPATCH_BATTERY:
            print(
                f"Ignored dispatch: battery {self.logic.battery:.1f}% is below "
                f"{MIN_DISPATCH_BATTERY}%"
            )
            self.logic.publish_status({
                "warning": "battery_too_low_for_dispatch",
                "min_dispatch_battery": MIN_DISPATCH_BATTERY,
            })
            self._set_display_warning("battery_too_low_for_dispatch")
            return

        if command == "successfully_docked":
            distance_to_base = distance_meters(self.logic.pos, self.logic.base_pos)
            if distance_to_base > BASE_DOCKED_RADIUS_M:
                print(
                    "Ignored successfully_docked: drone is "
                    f"{distance_to_base:.1f} m from base"
                )
                self.logic.publish_status({
                    "warning": "not_at_base_for_docked_confirmation",
                    "distance_to_base_m": round(distance_to_base, 1),
                })
                return

        if command == "dispatch":
            self.telemetry.set_target(payload.get("target"))
            self.logic.mission = payload.get("mission")
            self.proximity_sent = False
        elif command == "successfully_docked":
            self.logic.mission = None
            self.low_battery_return_sent = False

        self.stm_driver.send(command, "droneMachine")
        print(f'sent command {command} to the state machine')

    def start(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()
        
        time.sleep(1)
        self.stm_driver.start()

        try:
            last_tick = time.time()
            while True:
                now = time.time()
                elapsed = now - last_tick
                last_tick = now
                self.publish_telemetry(elapsed)
                time.sleep(self.telemetry_interval)
            
        except KeyboardInterrupt:
            print("Stopping drone client...")

        finally:
            self.client.loop_stop()
            self.client.disconnect()
            self.sense_display.clear()
            self.stm_driver.stop()
            print("Drone client stopped.")

    def publish_telemetry(self, elapsed):
        with self.lock:
            telemetry_data = self.telemetry.tick(elapsed)
            sense_hat_data = self.sense_reader.read()
            display_data = self._update_sense_display()

            self.logic.publish_status({
                "telemetry": telemetry_data,
                "sense_hat": sense_hat_data,
                # "sense_hat_display": display_data,
            })

            distance_to_target = telemetry_data.get("distance_to_target_m")
            distance_to_base = telemetry_data.get("distance_to_base_m")

            if self.logic.current_state == "docked":
                self.low_battery_return_sent = False

            if (
                self.logic.current_state in ["navigating", "manual_control", "waiting_onsite"]
                and self.logic.battery <= AUTO_RETURN_BATTERY_THRESHOLD
                and not self.low_battery_return_sent
            ):
                if self.logic.current_state == "navigating":
                    self.stm_driver.send("nav_abort", "droneMachine")
                    print(
                        "Auto nav_abort sent to the state machine "
                        f"(battery {self.logic.battery:.1f}% <= {AUTO_RETURN_BATTERY_THRESHOLD}%)"
                    )
                elif self.logic.current_state == "manual_control":
                    self.stm_driver.send("manual_abort", "droneMachine")
                    print(
                        "Auto manual_abort sent to the state machine "
                        f"(battery {self.logic.battery:.1f}% <= {AUTO_RETURN_BATTERY_THRESHOLD}%)"
                    )
                else:
                    self.stm_driver.send("mission_complete", "droneMachine")
                    print(
                        "Auto mission_complete sent to the state machine "
                        f"(battery {self.logic.battery:.1f}% <= {AUTO_RETURN_BATTERY_THRESHOLD}%)"
                    )

                self.low_battery_return_sent = True

            if (
                self.auto_proximity
                and self.logic.current_state == "navigating"
                and distance_to_target is not None
                and distance_to_target <= 100
                and not self.proximity_sent
            ):
                self.proximity_sent = True
                self.stm_driver.send("prox_alert", "droneMachine")
                print("Auto proximity alert sent to the state machine")

            if (
                self.logic.current_state == "returning"
                and distance_to_base is not None
                and distance_to_base <= 1
            ):
                self.logic.mission = None
                self.stm_driver.send("successfully_docked", "droneMachine")
                print("Auto successfully_docked sent to the state machine")

    def _set_display_warning(self, warning):
        self.display_warning = warning
        self.display_warning_until = time.time() + DISPLAY_WARNING_SECONDS

    def _update_sense_display(self):
        warning = None
        if self.display_warning and time.time() < self.display_warning_until:
            warning = self.display_warning
        else:
            self.display_warning = None

        mode = mode_for_state(
            self.logic.current_state,
            self.logic.battery,
            warning=warning,
        )
        return self.sense_display.show(mode)


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Team 20 drone client.")
    parser.add_argument("--broker", default=os.getenv("MQTT_BROKER", "mqtt20.item.ntnu.no"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--drone-id", default=os.getenv("DRONE_ID", "drone_1"))
    parser.add_argument(
        "--telemetry-interval",
        type=float,
        default=float(os.getenv("TELEMETRY_INTERVAL", "5.0")),
    )
    parser.add_argument(
        "--auto-proximity",
        action="store_true",
        default=os.getenv("DRONE_AUTO_PROXIMITY", "0") == "1",
        help="Automatically sends prox_alert when simulated position is close to target.",
    )
    parser.add_argument(
        "--mock-sense-hat",
        action="store_true",
        default=os.getenv("MOCK_SENSE_HAT", "0") == "1",
        help="Use fake Sense HAT values on Mac/Linux/Windows development machines.",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    drone = DroneClient(
        args.broker,
        args.port,
        drone_id=args.drone_id,
        telemetry_interval=args.telemetry_interval,
        auto_proximity=args.auto_proximity,
        mock_sense_hat=args.mock_sense_hat,
    )
    drone.start()
