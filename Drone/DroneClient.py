import paho.mqtt.client as mqtt
import time

class DroneClient:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.mqtt_client = mqtt.Client()
        self.setup_callbacks()

    def setup_callbacks(self):
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print(f"Drone connected to MQTT Broker: {self.broker}:{self.port}")
        self.mqtt_client.subscribe("server/commands")
        print("Subscribed to topic: server/commands")

    def on_message(self, client, userdata, msg):
        print(f"Received command: {msg.payload.decode()}")
        # Add handling off commands here

    def publish_telemetry(self):
        while True:
            telemetry_data = "GPS: 63.42, 10.39, Battery: 85%" #Example data
            self.mqtt_client.publish("drone/telemetry", telemetry_data)
            print(f"Published telemetry: {telemetry_data}")
            time.sleep(5)

    def start(self):
        self.mqtt_client.connect(self.broker, self.port)
        self.mqtt_client.loop_start()
        self.publish_telemetry()

broker, port = "mqtt20.item.ntnu.no", 1883

drone = DroneClient(broker, port)
drone.start()