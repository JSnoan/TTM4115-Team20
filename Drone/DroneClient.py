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
        self.logic = DroneClient(self.client)


    def on_connect(self, client, userdata, flags, rc):
        print(f"Drone connected to MQTT Broker: {self.broker}:{self.port}")
        self.client.subscribe("server/commands")
        print("Subscribed to topic: server/commands")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print("Error with message")
        
        match payload.get("command"):
            case "dispatch":
                self.stm_driver.send("dispatch", "droneMachine")
            case "prox_alert":
                self.stm_driver.send("prox_alert", "droneMachine")
            case "manual_complete":
                self.stm_driver.send("manual_complete", "droneMachine")
            case "nav_abort":
                self.stm_driver.send("nav_abort", "droneMachine")
            case "manual_abort":
                self.stm_driver.send("manual_abort", "droneMachine")
            case "mission_complete":
                self.stm_driver.send("mission_complete", "droneMachine")
        

    def start(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

        while True:
            threading.Thread(target=self.publish_telemetry, daemon=True).start()
            threading.Thread(target=self.publish_status, daemon=True).start()
            time.sleep(10)

broker, port = "mqtt20.item.ntnu.no", 1883

drone = DroneClient(broker, port)
drone.start()