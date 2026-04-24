import paho.mqtt.client as mqtt
import json

class MqttServer:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.mqtt_client = mqtt.Client()
        self.setup_callbacks()

    def setup_callbacks(self):
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print(f"Connected to MQTT Broker: {self.broker}:{self.port}")
        #Subscribe to drone information
        self.mqtt_client.subscribe("drone/telemetry")
        self.mqtt_client.subscribe("drone/status")
        print("Subscribed to topics: drone/telemetry, drone/status")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print("Error parsing JSON:", e)
            return

        if msg.topic == "drone/telemetry":
            self.handle_telemetry(payload)
        elif msg.topic == "drone/status":
            self.handle_status(payload)

    def handle_telemetry(self, data):
        gps = data.get("gps")
        print(gps)
        command = {"command": "continue"}
        self.mqtt_client.publish("server/commands", json.dumps(command))
        # Add actions to be taken based on telemetry data

    def handle_status(self, data):
        battery = data.get("battery")
        state = data.get("state")
        print(battery, state)
        command = {"command": "continue"}
        self.mqtt_client.publish("server/commands", json.dumps(command))
        # Add actions to be taken based on status data

    def start(self):
        print(f"Starting MQTT Server on {self.broker}:{self.port}")
        self.mqtt_client.connect(self.broker, self.port)
        self.mqtt_client.loop_forever()

# Define broker and port    
broker, port = "mqtt20.item.ntnu.no", 1883

# Start the MQTT server
server = MqttServer(broker, port)
server.start()