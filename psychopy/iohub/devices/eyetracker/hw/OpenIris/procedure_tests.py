import threading
import time
import queue
import os
import json
import numpy as np
import gevent
import yaml



#custom imports
from psychopy.iohub.devices.eyetracker.hw.OpenIris.eyetracker_test import DPIEyeTracker
from psychopy.iohub.devices.eyetracker.hw.OpenIris.calibration_test import KeyboardListener 
from psychopy.iohub.devices.eyetracker.hw.OpenIris.client_test import OpenIrisClient

# psychopy rendering libraries
from psychopy import visual, layout
from psychopy.constants import PLAYING
from psychopy.iohub.errors import print2err
from psychopy.iohub.devices import DeviceEvent, Computer
from psychopy.iohub.constants import EventConstants as EC
from psychopy.iohub.devices.keyboard import KeyboardInputEvent
from psychopy.iohub.util import convertCamelToSnake, updateSettings, createCustomCalibrationStim

# Custom JSON encoder for numpy data types
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        return super(NumpyEncoder, self).default(obj)

# --- Shared Resources ---
screen_position_queue = queue.Queue()
key_queue = queue.Queue()

# Event to signal threads to stop
stop_event = threading.Event()

# --- Thread 1: Data Collector and Filterer ---
class DataCollector(threading.Thread):
    """Thread to collect and filter data
    Functionality:
    - Collect eye data
    - send eye data to queues
    """
    def __init__(self, name, eyetracker, screen_queue, stop_event, collect_delay=0.005):
        super().__init__(name=name)
        self.eyetracker = eyetracker
        self.screen_queue = screen_queue 
        self.stop_event = stop_event
        self.collected_count = 0
        self.collect_delay = collect_delay  # Collect data every 5ms + processing time

    def run(self):
        print(f"{self.name} started.")            
        if not eyetracker.isConnected():
            print2err("OpenIris client is not connected. Exiting collector thread.")

        else:
            while not self.stop_event.is_set():
                data = eyetracker._poll_basic()
                if data is not None:
                    self.screen_queue.put(data[0])
                else:
                    self.screen_queue.put("None")
                self.collected_count += 1
                time.sleep(self.collect_delay)

        print(f"{self.name} stopped. Collected {self.collected_count} items.")

    def get_collected_count(self):
        return self.collected_count


# --- Thread 2: Data Renderer ---
class Renderer(threading.Thread):
    """Thread to render data on screen
    RENDERING NOT COMPLETE, PLACEHOLDERS FOR METHODS
    """
    def __init__(self,name, screen_queue, stop_event):
        super().__init__(name=name)
        self.screen_queue = screen_queue
        self.stop_event = stop_event
        self.rendered_count = 0
        self.check_delay = 0.005

    def run(self):
        #create window for rendering with psychopy stuff

        while not self.stop_event.is_set():
            # loop rendering image to point on screen provided by data_queue
            # also define stop_event when space or escape is pressed and during loop check    

            try:
                pos = self.screen_queue.get() 
                # Small timeout to allow checking stop_event
                #render image at position pos
                # print(f"Rendering: {pos}")
                self.rendered_count += 1
            except queue.Empty:
                print("queue empty") # No data in queue, continue to check for updates/stop_event
            time.sleep(self.check_delay)

        # kill windows and end psychopy stuff

        print(f"{self.name} stopped. Processed {self.rendered_count} renders.")

    def get_rendered_count(self):
        return self.rendered_count


# --- Main execution ---
if __name__ == "__main__":
    with OpenIrisClient() as client:
        eyetracker = DPIEyeTracker(client)
        
        keyboard_listener = KeyboardListener(key_queue, stop_event, key_list=['esc', 'space', 'q'])
        try:
            keyboard_listener.start()
        except Exception as e:
            print(f"Error starting keyboard listener: {e}")

        # Read calibration args
        calibrationargs = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), 'calibration_settings.yaml'), 'r'))   

        print(f"calibration: {eyetracker.runSetupProcedure(key_queue, calibrationargs)}")

        collector_thread = DataCollector(
            "CollectorThread", eyetracker, screen_position_queue, stop_event
        )
        renderer_thread = Renderer(
            "RendererThread", screen_position_queue, stop_event
        )

        try:
            collector_thread.start()
            renderer_thread.start()
            

            # Let the threads run for a while
            run_duration_seconds = 1
            print(f"Running for {run_duration_seconds} seconds...")
            for i in range(run_duration_seconds * 10): # Check every 100ms
                time.sleep(0.1)
                print(f"Time: {i * 0.1} seconds")
                print(f"Collected Count: {collector_thread.get_collected_count()}")
                print(f"Rendered Count: {renderer_thread.get_rendered_count()}")
                print(f"Queue Polled: {screen_position_queue.get()}")
        
            print("Stopping threads...")

        except KeyboardInterrupt:
            print("\nCtrl+C detected. Signaling threads to stop...")

        except Exception as e:
            print(f"Error: {e}")
        
        finally:
            stop_event.set() # Signal both threads to stop
            renderer_thread.join() # Wait for renderer to finish
            collector_thread.join() # Wait for collector to finish
        
        client.__exit__("End", 0, "procedure_tests.py conclusion")

    print("All threads finished.")