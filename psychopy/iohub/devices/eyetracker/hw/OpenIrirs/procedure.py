import threading
import time
import queue
import random # For simulating data collection
from psychopy.iohub.devices.eyetracker.hw.OpenIrirs.eyetracker import DPIEyeTracker
import os
import json

# --- Shared Resources ---
# Queue for filtered data from collector to storer
filtered_data_queue = queue.Queue()
screen_position_queue = queue.Queue()


# Current filtering values, protected by a lock
# Structure: {'min_val': 0, 'max_val': 100}
current_filtering_values = {'min_val': 0, 'max_val': 100}
filtering_values_lock = threading.Lock()


# Event to signal threads to stop
stop_event = threading.Event()

# --- Thread 1: Data Collector and Filterer ---
class DataCollector(threading.Thread):
    """Thread to collect and filter data
    Functionality:
    - Collect eye data
    - send eye data to queues
    """
    def __init__(self, name, data_queue, screen_queue, filtering_values_lock, stop_event):
        super().__init__(name=name)
        self.data_queue = data_queue
        self.screen_queue = screen_queue 
        self.filtering_values_lock = filtering_values_lock
        self.stop_event = stop_event
        self.collected_count = 0

    def run(self):
        print(f"{self.name} started.")
        while not self.stop_event.is_set():
            # Simulate data collection
            raw_data, raw_time = random.randint(-50, 150)
            
            # Get current filtering values safely
            with self.filtering_values_lock:
                min_val = current_filtering_values['min_val']
                max_val = current_filtering_values['max_val']

            # Apply filter
            if min_val <= raw_data <= max_val:
                filtered_data = raw_data
                self.data_queue.put(filtered_data)
                self.collected_count += 1
                # print(f"{self.name}: Collected and filtered {filtered_data} (count: {self.collected_count})")
            else:
                pass
                # print(f"{self.name}: Discarded {raw_data} (outside filter {min_val}-{max_val})")
            
            # Simulate some processing time
            time.sleep(0.01) # Collect data every 10ms

        print(f"{self.name} stopped. Collected {self.collected_count} items.")

class Rendering(threading.Thread):
    def __init__(self, name, data_queue, filtering_values_lock, stop_event):
        super().__init__(name=name)
        self.data_queue = data_queue
        self.filtering_values_lock = filtering_values_lock
        self.stop_event = stop_event
        self.collected_count = 0

    def run(self):
        print(f"{self.name} started.")
        while not self.stop_event.is_set():
            # Simulate data collection
            raw_data = random.randint(-50, 150)
            
            # Get current filtering values safely
            with self.filtering_values_lock:
                min_val = current_filtering_values['min_val']
                max_val = current_filtering_values['max_val']

            # Apply filter
            if min_val <= raw_data <= max_val:
                filtered_data = raw_data
                self.data_queue.put(filtered_data)
                self.collected_count += 1
                # print(f"{self.name}: Collected and filtered {filtered_data} (count: {self.collected_count})")
            else:
                pass
                # print(f"{self.name}: Discarded {raw_data} (outside filter {min_val}-{max_val})")
            
            # Simulate some processing time
            time.sleep(0.01) # Collect data every 10ms

        print(f"{self.name} stopped. Collected {self.collected_count} items.")


class DataProcessor(threading.Thread):
    def __init__(self,name, data_queue, filtering_values_lock, stop_event, calculation_period_ms=100):
        super().__init__(name=name)
        self.data_queue = data_queue
        self.filtering_values_lock = filtering_values_lock
        self.stop_event = stop_event
        self.stored_data = []
        self.calculation_period_s = calculation_period_ms / 1000.0
        self.last_calculation_time = time.monotonic()
        self.processing_count = 0

        # Data storgage
        self.logfolder = None #path to logfolder
        self.logfile = None #path to logfile
        self.filename = None 
        self.lastDataset = None
        self.currentDataset = [] 

    def run(self):
        while not self.stop_event.is_set() or not self.data_queue.empty():
            try:
                data = self.data_queue.get(timeout=0.01) # Small timeout to allow checking stop_event
                self.stored_data.append(data)
                self.processing_count += 1
                # print(f"{self.name}: Stored data: {data}")
            except queue.Empty:
                pass # No data in queue, continue to check for updates/stop_event

            # Check if it's time to recalculate filtering values
            current_time = time.monotonic()
            if current_time - self.last_calculation_time >= self.calculation_period_s:
                self.calculate_and_update_filters()
                self.last_calculation_time = current_time

            # Avoid busy-waiting if queue is empty and not time for calculation
            if self.data_queue.empty() and (current_time - self.last_calculation_time < self.calculation_period_s):
                time.sleep(0.005) # Short sleep to yield control

        # Final calculation if there's any remaining data after stopping
        if self.stored_data:
            self.calculate_and_update_filters()

        print(f"{self.name} stopped. Processed {self.processing_count} items. Final stored data count: {len(self.stored_data)}")

    def calculate_and_update_filters(self):
        # Implement your logic to calculate filtering values based on stored_data
        # For this example, let's use a simple moving average/range from the last N data points
        window_size = 50 # Consider the last 50 data points for calculation
        data_for_calculation = self.stored_data[-window_size:]

        if data_for_calculation:
            new_min_val = min(data_for_calculation) - 5
            new_max_val = max(data_for_calculation) + 5
        else:
            # If no data yet, use default values or some intelligent starting point
            new_min_val = 0
            new_max_val = 100

        # Update global filtering values safely
        with self.filtering_values_lock:
            current_filtering_values['min_val'] = new_min_val
            current_filtering_values['max_val'] = new_max_val
            # print(f"--- Filters updated to: min={new_min_val}, max={new_max_val} ---")
    
    def createDataLog(self, filename):
        self.logfile = self.logfolder + "/" + filename
        self.filename = filename
        if not os.path.exists(self.logfile ):
            with open(self.logfile, 'w') as f:
                pass

    def logData(self, data):
        try: 
            with open(self.logfile, 'a') as f:
                json_string = json.dumps(data)
                f.write(json_string + '\n')
        except IOError as e:
            print(f"Error appending to file '{self.logfile}': {e}")
        except TypeError as e:
            print(f"Error serializing data: {e}. Please provide JSON-serializable data.")

    def readLastLine(self):
        try:
            with open(self.logfile, 'r') as f:
                line = f.readlines().strip()
                if not line:
                    print(f"File '{self.filename}' is empty.")
                    return None
                return json.loads(line)
        except:
            pass

    def readLastLines(self, n):
        if not os.path.exists(self.logfile):
            print(f"File not found: {self.logfile}")
            return []

        try:
            with open(self.logfile, 'r') as f:
                lines = f.readlines()
                last_n_lines = lines[-n:]
                
                json_objects = []
                for line in last_n_lines:
                    try:
                        json_objects.append(json.loads(line.strip()))
                    except json.JSONDecodeError as e:
                        print(f"Warning: Could not decode JSON from line: '{line.strip()}' - {e}")
                return json_objects
        except Exception as e:
            print(f"An error occurred while reading the file: {e}")
            return []



# --- Main execution ---
if __name__ == "__main__":
    collector_thread = DataCollector(
        "CollectorThread", filtered_data_queue, filtering_values_lock, stop_event
    )
    processor_thread = DataProcessor(
        "ProcessorThread", filtered_data_queue, filtering_values_lock, stop_event, calculation_period_ms=100
    )

    collector_thread.start()
    processor_thread.start()

    try:
        # Let the threads run for a while
        run_duration_seconds = 10
        print(f"Running for {run_duration_seconds} seconds...")
        for i in range(run_duration_seconds * 10): # Check every 100ms
            time.sleep(0.1)
            with filtering_values_lock:
                print(f"Main thread: Current filters: {current_filtering_values}. Queue size: {filtered_data_queue.qsize()}")
        
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Signaling threads to stop...")
    finally:
        stop_event.set() # Signal both threads to stop
        collector_thread.join() # Wait for collector to finish
        processor_thread.join() # Wait for processor to finish

    print("All threads finished.")
    print(f"Final stored data sample (last 20 items): {processor_thread.stored_data[-20:]}")