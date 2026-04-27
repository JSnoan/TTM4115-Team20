import paho.mqtt.client as mqtt
import time
import json
import threading
import stmpy
from droneLogic import DroneLogic

class DroneClient:
    def __init__(self, broker, port):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id="team20_drone")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.logic = DroneLogic(self.client)
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
            "navigating": ["prox_alert", "nav_abort"],
            "manual_control": ["manual_complete", "manual_abort"],
            "waiting_onsite": ["mission_complete"],
            "returning": [],
        }

        if command not in allowed_commands.get(current_state, []):
            print(f"Ignored invalid command '{command}' while in state '{current_state}'")
            return

        self.stm_driver.send(command, "droneMachine")
        print(f'sent command {command} to the state machine')

    def start(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()
        
        time.sleep(1)
        self.stm_driver.start()

        try:
            while True:
            #removed while debugging
            #    self.logic.publish_status()
                print("*publish*")
                time.sleep(10)
            
        except KeyboardInterrupt:
            print("Stopping drone client...")

        finally:
            self.client.loop_stop()
            self.client.disconnect()
            self.stm_driver.stop()
            print("Drone client stopped.")

broker, port = "mqtt20.item.ntnu.no", 1883

drone = DroneClient(broker, port)
drone.start()