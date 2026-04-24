import paho.mqtt.client as mqtt
import time
import json
import threading

class DroneClient:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message


    def on_connect(self, client, userdata, flags, rc):
        print(f"Drone connected to MQTT Broker: {self.broker}:{self.port}")
        self.client.subscribe("server/commands")
        print("Subscribed to topic: server/commands")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print("Error with message")
        # Add handling off commands here

    def publish_telemetry(self):
        telemetry_data = {
            "gps": [63.42, 10.39],
            "battery": 85
            }
        self.client.publish("drone/telemetry", json.dumps(telemetry_data))
        print(f"Published telemetry: {telemetry_data}")
        

    def publish_status(self):
        status_data = {
            "battery": 85,
            "state": "navigating"
        }
        self.client.publish("drone/status", json.dumps(status_data))
        print(f"Published status: {status_data}")
        

    def start(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

        

        while True:
            threading.Thread(target=self.publish_telemetry, daemon=True).start()
            threading.Thread(target=self.publish_status, daemon=True).start()
            time.sleep(100)

broker, port = "mqtt20.item.ntnu.no", 1883

drone = DroneClient(broker, port)
drone.start()