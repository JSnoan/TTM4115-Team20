import paho.mqtt.client as mqtt
import json
import time
import argparse
import os

class MqttServer:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id="team20_server")
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
        print(f"Drone status: state={state}, battery={battery}, pos={pos}")
        
        #removed while debugging
        #command = {"command": "continue"}
        #self.client.publish("drone/commands", json.dumps(command))
        
        #TODO Add actions to be taken based on status data
        
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
                    
                    #for simulating arrivng at the target after 5 seconds. 
                    #consider moving to a drone simulator / rely on sensor data
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
                    print("Commands: dispatch, abort, complete, return, quit")

        except KeyboardInterrupt:
            pass
        finally:
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
