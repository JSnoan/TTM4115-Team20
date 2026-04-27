import stmpy
import json


class DroneLogic:
    def __init__(self, client):
        self.client = client
        self.pos = [63.42, 10.39]
        self.battery = 85
        self.current_state = "docked"

        # Transitions

        initial = {
            "source": "initial",
            "target": "docked"
        }

        dispatch = {
            "source": "docked",
            "target": "navigating",
            "trigger": "dispatch"
        }

        prox_alert = {
            "source": "navigating",
            "target": "manual_control",
            "trigger": "prox_alert"
        }

        manual_complete = {
            "source": "manual_control",
            "target": "waiting_onsite",
            "trigger": "manual_complete"
        }

        nav_abort = {
            "source": "navigating",
            "target": "returning",
            "trigger": "nav_abort"
        }

        manual_abort = {
            "source": "manual_control",
            "target": "returning",
            "trigger": "manual_abort"
        }

        mission_complete = {
            "source": "waiting_onsite",
            "target": "returning",
            "trigger": "mission_complete"
        }


        # States
        
        docked = {
            "name": "docked",
            "entry": "docked_state"
        }

        navigating = {
            "name": "navigating",
            "entry": "navigating_state"
        }

        manual_control = {
            "name": "manual_control",
            "entry": "manual_state"
        }

        waiting_onsite = {
            "name": "waiting_onsite",
            "entry": "waiting_state"
        }

        returning = {
            "name": "returning",
            "entry": "returning_state"
        }

        self.stm = stmpy.Machine(
            name="droneMachine",
            transitions=[
                initial,
                dispatch,
                prox_alert,
                manual_complete,
                nav_abort,
                manual_abort,
                mission_complete
            ],
            states=[
                docked,
                navigating,
                manual_control,
                waiting_onsite,
                returning
            ],
            obj=self
        )

    # ----------------
    # State methods
    # ----------------

    def docked_state(self):
        self.current_state = "docked"
        print("Entered docked state")
        self.publish_status()

    def navigating_state(self):
        self.current_state = "navigating"
        print("Entered navigating state")
        self.publish_status()

    def manual_state(self):
        self.current_state = "manual_control"
        print("Entered manual control state")
        self.publish_status()

    def waiting_state(self):
        self.current_state = "waiting_onsite"
        print("Entered waiting onsite state")
        self.publish_status()

    def returning_state(self):
        self.current_state = "returning"
        print("Entered returning state")
        self.publish_status()

    # ----------------
    # Helper methods
    # ----------------

    def publish_status(self):
        status_data = {
            "state": self.current_state,
            "pos": self.pos,
            "battery": self.battery
        }

        self.client.publish("drone/status", json.dumps(status_data))
        print(f"Published status: {status_data}")