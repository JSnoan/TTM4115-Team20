import paho.mqtt.client as mqtt
import time
import json
import threading
from droneLogic import DroneLogic

class DroneClient:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.logic = DroneLogic(self.client)


    def on_connect(self, client, userdata, flags, rc):
        print(f"Drone connected to MQTT Broker: {self.broker}:{self.port}")
        self.client.subscribe("drone/commands")
        print("Subscribed to topic: drone/commands")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print("Error with message:", e)
            return
        
        command = payload.get("command")
        current_state = self.logic.stm.current_state.name
        
        allowed_commands = {
            "docked": ["dispatch"],
            "navigating": ["prox_alert", "nav_abort"],
            "manual_control": ["manual_complete", "manual_abort"],
            "waiting_onsite": ["mission_complete"],
            "returning": [],
        }

        if command not in allowed_commands.get(current_state, []):
            print(f"Ignored invalid command '{command}' while in state '{current_state}'")
            return

        self.stm_driver.send(command, "droneMachine")

    def start(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

        while True:
            self.logic.publish_status()
            time.sleep(10)

broker, port = "mqtt20.item.ntnu.no", 1883

drone = DroneClient(broker, port)
drone.start()