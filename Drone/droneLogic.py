import stmpy

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
            'trigger': ''
        }

        prox_alert = {
            'source': 'navigating',
            'target': 'manual_control', 
            'trigger':''
        }

        manual_complete = {
            'source': 'manual_control', 
            'target': 'waiting_onsite', 
            'trigger': ''
        }

        nav_abort = {
            'source': 'navigating',
            'target': 'returning', 
            'trigger': ''
        }

        manual_abort = {
            'source': 'manual_control',
            'target': 'returning',
            'trigger': '' 
        }

        mission_complete = {
            'source': 'waiting_onsite',
            'target': 'returning', 
            'trigger': ''
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