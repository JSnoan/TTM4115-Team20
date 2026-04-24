import paho.mqtt.client as mqtt
import json

class MqttServer:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"Connected to MQTT Broker: {self.broker}:{self.port}")
            #Subscribe to drone information
            self.client.subscribe("drone/telemetry")
            self.client.subscribe("drone/status")
            print("Subscribed to topics: drone/telemetry, drone/status")
        else:
            print(f"connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        print(f"Received message on topic {msg.topic}: {msg.payload.decode()}")
        # Actions related to telemetry/status
        if msg.topic == "drone/telemetry":
            self.handle_telemetry(msg.payload.decode())
        elif msg.topic == "drone/status":
            self.handle_status(msg.payload.decode())

    def handle_telemetry(self, data):
        print(
            "Drone telementry:"    
            f"state={data['state']} "
            f"battery={data['battery']}% "
            )
        # Add actions to be taken based on telemetry data

    def handle_status(self, data):
        print(f"Drone Status: {data}")
        # Add actions to be taken based on status data
        
    def send_command(self, command):
        topic = f"drones/commands"
        self.client.publish(topic, json.dumps(command))
        print(f"Sent command to drone: {command}")

    def start(self):
        print(f"Starting MQTT Server on {self.broker}:{self.port}")
        self.client.connect(self.broker, self.port)
        self.client.loop_start()
        
        try:
            while True:
                user_input = input("server> ")

                if user_input == "dispatch":
                    self.send_command({
                        "command": "dispatch",
                        "target": {
                            "lat": 63.425,
                            "lon": 10.395
                        }
                    })

                elif user_input == "return":
                    self.send_command({
                        "command": "return_home"
                    })

                elif user_input == "manual":
                    self.send_command({
                        "command": "manual_control"
                    })

                elif user_input == "land":
                    self.send_command({
                        "command": "land"
                    })

                elif user_input == "quit":
                    break

                else:
                    print("Commands: dispatch, return, manual, land, quit")

        except KeyboardInterrupt:
            pass
        finally:
            self.client.loop_stop()
            self.client.disconnect()

# Define broker and port
broker, port = "mqtt20.item.ntnu.no", 1883

# Start the MQTT server
server = MqttServer(broker, port)
server.start()