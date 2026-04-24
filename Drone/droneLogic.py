import stmpy
import json
import paho.mqtt.client as mqtt
import time
import threading

broker, port = "mqtt20.item.ntnu.no", 1883

class DroneLogic:
    """
    State Machine for a drone.
    
    """
    def __init__(self, client):

        #Transitions

        initial = {
            'source': 'initial', 
            'target': 'docked'
        }

        dispatch = {
            'source': 'docked', 
            'target': 'navigating', 
            'trigger': 'dispatch',
            'effect': ''
        }

        prox_alert = {
            'source': 'navigating',
            'target': 'manual_control', 
            'trigger':'prox_alert',
            'effect': ''
        }

        manual_complete = {
            'source': 'manual_control', 
            'target': 'waiting_onsite', 
            'trigger': 'manual_control',
            'effect': ''
        }

        nav_abort = {
            'source': 'navigating',
            'target': 'returning', 
            'trigger': 'nav_abort',
            'effect': ''
        }

        manual_abort = {
            'source': 'manual_control',
            'target': 'returning',
            'trigger': 'manual_abort',
            'effect': ''
        }

        mission_complete = {
            'source': 'waiting_onsite',
            'target': 'returning', 
            'trigger': 'mission_complete',
            'effect': ''
        }


        # States
        docked = {
            'name': 'docked',
            'entry': ''
        }

        navigating = {
            'name': 'navigating',
            'entry': '',
        }

        manual_control = {
            'name': 'manual_control',
            'entry': ''
        }

        waiting_onsite = {
            'name': 'waiting_onsite',
            'entry': ''
        }
        
        returning = {
            'name': 'returning',
            'entry': '',
        }
        
        self.stm = stmpy.Machine(name="droneMachine", transitions=[], states=[docked, navigating, manual_control, waiting_onsite, returning], obj=self)
        
        # state methods
        
        def publish_status(self):
            status_data = {
                "state": "navigating",
                "pos": [63.42, 10.39],
                "battery": 85
            }
            self.client.publish("drone/status", json.dumps(status_data))
            print(f"Published status: {status_data}")
        
        
        # transition methods
        