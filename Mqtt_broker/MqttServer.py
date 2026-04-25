import paho.mqtt.client as mqtt
import json
import time

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
            self.client.subscribe("drone/status")
            print("Subscribed to topics: drone/status")
        else:
            print(f"connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print("Error parsing JSON:", e)
            return

        if msg.topic == "drone/status":
            self.handle_status(payload)

    def handle_status(self, data):
        state = data.get("state")
        battery = data.get("battery")
        pos = data.get("pos")
        command = {"command": "continue"}
        self.client.publish("server/commands", json.dumps(command))
        # Add actions to be taken based on status data
        
    def send_command(self, command):
        topic = "drone/commands"
        self.client.publish(topic, json.dumps(command))
        print(f"Sent command to drone: {command}")

    def start(self):
        print(f"Starting MQTT Server on {self.broker}:{self.port}")
        self.client.connect(self.broker, self.port)
        self.client.loop_start()
        #TODO add message of where client is located(randint of certain area)
        
        try:
            #TODO make handling based on data, not manual user input, for relevant cases
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
                    time.sleep(5)
                    self.send_command({
                        "command": "prox_alert"
                    })
                
                elif user_input == "abort":
                    self.send_command({
                        "command": "manual_abort"
                    })
                    
                elif user_input == "complete":
                    self.send_command({
                        "command": "manual_complete"
                    })

                elif user_input == "return":
                    self.send_command({
                        "command": "mission_complete"
                    })

                elif user_input == "quit":
                    break

                else:
                    print("Commands: dispatch, manual, complete, return, quit")

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