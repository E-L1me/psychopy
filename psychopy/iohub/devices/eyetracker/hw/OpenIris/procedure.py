import threading
import time
import queue
import os
import json
import numpy as np
import gevent
import yaml

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


#custom imports
from psychopy.iohub.devices.eyetracker.hw.OpenIris.eyetracker import DPIEyeTracker

# psychopy rendering libraries
from psychopy import visual, layout
from psychopy.constants import PLAYING
from psychopy.iohub.errors import print2err
from psychopy.iohub.devices import DeviceEvent, Computer
from psychopy.iohub.constants import EventConstants as EC
from psychopy.iohub.devices.keyboard import KeyboardInputEvent
from psychopy.iohub.util import convertCamelToSnake, updateSettings, createCustomCalibrationStim




# --- Shared Resources ---
filtered_data_queue = queue.Queue()
screen_position_queue = queue.Queue()

# Global variable to hold current filtering values
filtering_values = {'pupil_area': {'max': 0.0, 'min': 0.0},
                    'P4': {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0},
                    'CR': {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0},
                    'screen_position': {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0},
                    'P4_speed': 0.0}
# Lock for safely accessing filtering values across threads
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
    def __init__(self, name, eyetracker, data_queue, screen_queue, filtering_values_lock, stop_event, collect_delay=0.005):
        super().__init__(name=name)
        self.eyetracker = eyetracker
        self.data_queue = data_queue
        self.screen_queue = screen_queue 
        self.filtering_values_lock = filtering_values_lock
        self.stop_event = stop_event
        self.collected_count = 0
        self.collect_delay = collect_delay  # Collect data every 5ms + processing time

    def run(self):
        print(f"{self.name} started.")

        while not self.stop_event.is_set():
            # Get current filtering values safely
            with self.filtering_values_lock:
                self.eyetracker.updateFilteringValues(
                    pupil_area_thresh=filtering_values['pupil_area'],
                    P4_speed_thresh=filtering_values['P4_speed']
                )
            
            data = self.eyetracker._poll()
            if data[3] == 0 or data[3] == 1:
                self.data_queue.put(data)
                self.screen_queue.put(data[0])
                self.collected_count += 1
            elif data[3] == 2 or data[3] == 3:
                # Handle error data
                print(f"{self.name}: Error data received: {data}")
                   
            time.sleep(self.collect_delay)

        print(f"{self.name} stopped. Collected {self.collected_count} items.")

# --- Thread 2: Data Renderer ---
class Renderer(threading.Thread):
    """Thread to render data on screen
    RENDERING NOT COMPLETE, PLACEHOLDERS FOR METHODS
    """
    def __init__(self,name, screen_queue, stop_event):
        super().__init__(name=name)
        self.screen_queue = screen_queue
        self.stop_event = stop_event
        self.last_data = None
        self.processing_count = 0

        self.currentTime = Computer.getTime

    def run(self, logname='DPIDataLog.json'):
        #create window for rendering with psychopy stuff

        while not self.stop_event.is_set() or not self.screen_queue.empty():
            # loop rendering image to point on screen provided by data_queue
            # also define stop_event when space or escape is pressed and during loop check    

            try:
                pos = self.screen_queue.get() # Small timeout to allow checking stop_event
                #render image at position pos
                print(pos)  # placeholder for rendering logic
                self.processing_count += 1
            except queue.Empty:
                pass # No data in queue, continue to check for updates/stop_event
           
        # kill windows and end psychopy stuff

        print(f"{self.name} stopped. Processed {self.processing_count} renders.")

    # def showIntroScreen(self, text_msg='Press SPACE to Start Calibration; Press ESCAPE to Exit.'):

    #     self.clearAllEventBuffers()

    #     while True:
    #         self.textLineStim.setText(text_msg)
    #         self.textLineStim.draw()
    #         self.window.flip()

    #         msg = self.getNextMsg()
    #         if msg == 'SPACE_KEY_ACTION':
    #             self.clearAllEventBuffers()
    #             return True
    #         elif msg == 'QUIT':
    #             self.clearAllEventBuffers()
    #             return False
    #         self.MsgPump()
    #         gevent.sleep(0.001)
    
    # def showFinishedScreen(self, text_msg="Calibration Complete. Press 'SPACE' key to continue."):
        
    #     self.clearAllEventBuffers()

    #     while True:
    #         self.textLineStim.setText(text_msg)
    #         self.textLineStim.draw()
    #         self.window.flip()

    #         msg = self.getNextMsg()
    #         if msg in ['SPACE_KEY_ACTION', 'QUIT']:
    #             self.clearAllEventBuffers()
    #             return True
            
    #         self.MsgPump()
    #         gevent.sleep(0.001)
    
    # def createGraphics(self):
    #     """
    #     """
    #     color_type = self.getCalibSetting('color_type')
    #     unit_type = self.getCalibSetting('unit_type')

    #     def setDefaultCalibrationTarget():
    #         # convert sizes to stimulus units
    #         radiusPix = self.getCalibSetting(['target_attributes', 'outer_diameter']) / 2
    #         radiusObj = layout.Size(radiusPix, units=unit_type, win=self.window)
    #         radius = getattr(radiusObj, unit_type)[1]
    #         innerRadiusPix = self.getCalibSetting(['target_attributes', 'inner_diameter']) / 2
    #         innerRadiusObj = layout.Size(innerRadiusPix, units=unit_type, win=self.window)
    #         innerRadius = getattr(innerRadiusObj, unit_type)[1]
    #         # make target
    #         self.targetStim = visual.TargetStim(
    #             self.window, name="CP", style="circles",
    #             radius=radius,
    #             fillColor=self.getCalibSetting(['target_attributes', 'outer_fill_color']),
    #             borderColor=self.getCalibSetting(['target_attributes', 'outer_line_color']),
    #             lineWidth=self.getCalibSetting(['target_attributes', 'outer_stroke_width']),
    #             innerRadius=innerRadius,
    #             innerFillColor=self.getCalibSetting(['target_attributes', 'inner_fill_color']),
    #             innerBorderColor=self.getCalibSetting(['target_attributes', 'inner_line_color']),
    #             innerLineWidth=self.getCalibSetting(['target_attributes', 'inner_stroke_width']),
    #             pos=(0, 0),
    #             units=unit_type,
    #             colorSpace=color_type,
    #             autoLog=False
    #         )

    #     if self._calibration_args.get('target_type') == 'CIRCLE_TARGET':
    #         setDefaultCalibrationTarget()
    #     else:
    #         self.targetStim = createCustomCalibrationStim(self.window, self._calibration_args)
    #         if self.targetStim is None:
    #             # Error creating custom stim, so use default target stim type
    #             setDefaultCalibrationTarget()

    #     self.originalTargetSize = self.targetStim.size
    #     self.targetClassHasPlayPause = hasattr(self.targetStim, 'play') and hasattr(self.targetStim, 'pause')

    #     self.imagetitlestim = None

    #     tctype = color_type
    #     tcolor = self.getCalibSetting(['text_color'])
    #     if tcolor is None:
    #         # If no calibration text color provided, base it on the window background color
    #         from psychopy.iohub.util import complement
    #         sbcolor = self.getCalibSetting(['screen_background_color'])
    #         if sbcolor is None:
    #             sbcolor = self.window.color
    #         from psychopy.colors import Color
    #         tcolor_obj = Color(sbcolor, color_type)
    #         tcolor = complement(*tcolor_obj.rgb255)
    #         tctype = 'rgb255'

    #     instuction_text = 'Press SPACE to Start Calibration; ESCAPE to Exit.'
    #     self.textLineStim = visual.TextStim(self.window, text=instuction_text,
    #                                         pos=(0, 0), height=36,
    #                                         color=tcolor, colorSpace=tctype,
    #                                         units='pix', wrapWidth=self.width * 0.9)
    
    # def getCalibSetting(self, setting):
    #     if isinstance(setting, str):
    #         setting = [setting, ]
    #     calibration_args = self._calibration_args
    #     if setting:
    #         for s in setting[:-1]:
    #             calibration_args = calibration_args.get(s)
    #         return calibration_args.get(setting[-1])

    # def clearAllEventBuffers(self):
    #     self._eyetracker._iohub_server.eventBuffer.clear()
    #     for d in self._eyetracker._iohub_server.devices:
    #         d.clearEvents()

    # def _registerEventMonitors(self):
    #     kbDevice = None
    #     if self._eyetracker._iohub_server:
    #         for dev in self._eyetracker._iohub_server.devices:
    #             if dev.__class__.__name__ == 'Keyboard':
    #                 kbDevice = dev

    #     if kbDevice:
    #         eventIDs = []
    #         for event_class_name in kbDevice.__class__.EVENT_CLASS_NAMES:
    #             eventIDs.append(getattr(EC, convertCamelToSnake(event_class_name[:-5], False)))

    #         self._ioKeyboard = kbDevice
    #         self._ioKeyboard._addEventListener(self, eventIDs)
    #     else:
    #         print2err('Warning: %s could not connect to Keyboard device for events.' % self.__class__.__name__)

    # def _unregisterEventMonitors(self):
    #     if self._ioKeyboard:
    #         self._ioKeyboard._removeEventListener(self)

    # def _handleEvent(self, event):
    #     event_type_index = DeviceEvent.EVENT_TYPE_ID_INDEX
    #     if event[event_type_index] == EC.KEYBOARD_RELEASE:
    #         ek = event[self._keyboard_key_index]
    #         if isinstance(ek, bytes):
    #             ek = ek.decode('utf-8')
    #         if ek == ' ' or ek == 'space':
    #             self._msg_queue.append('SPACE_KEY_ACTION')
    #             self.clearAllEventBuffers()
    #         elif ek == 'escape':
    #             self._msg_queue.append('QUIT')
    #             self.clearAllEventBuffers()

    # def MsgPump(self):
    #     # keep the psychopy window happy ;)
    #     if self.currentTime() - self._lastMsgPumpTime > self.IOHUB_HEARTBEAT_INTERVAL:
    #         # try to keep ioHub from being blocked. ;(
    #         if self._eyetracker._iohub_server:
    #             for dm in self._eyetracker._iohub_server.deviceMonitors:
    #                 dm.device._poll()
    #             self._eyetracker._iohub_server.processDeviceEvents()
    #         self._lastMsgPumpTime = self.currentTime()

    # def getNextMsg(self):
    #     if len(self._msg_queue) > 0:
    #         msg = self._msg_queue[0]
    #         self._msg_queue = self._msg_queue[1:]
    #         return msg
    
    # def clearCalibrationWindow(self):
    #     self.window.flip(clearBuffer=True)

    # def showIntroScreen(self, text_msg='Press SPACE to Start Calibration; ESCAPE to Exit.'):

    #     self.clearAllEventBuffers()

    #     while True:
    #         self.textLineStim.setText(text_msg)
    #         self.textLineStim.draw()
    #         self.window.flip()

    #         msg = self.getNextMsg()
    #         if msg == 'SPACE_KEY_ACTION':
    #             self.clearAllEventBuffers()
    #             return True
    #         elif msg == 'QUIT':
    #             self.clearAllEventBuffers()
    #             return False
    #         self.MsgPump()
    #         gevent.sleep(0.001)

    # def showFinishedScreen(self, text_msg="Calibration Complete. Press 'SPACE' key to continue."):

    #     self.clearAllEventBuffers()

    #     while True:
    #         self.textLineStim.setText(text_msg)
    #         self.textLineStim.draw()
    #         self.window.flip()

    #         msg = self.getNextMsg()
    #         if msg in ['SPACE_KEY_ACTION', 'QUIT']:
    #             self.clearAllEventBuffers()
    #             return True

    #         self.MsgPump()
    #         gevent.sleep(0.001)


    # def resetTargetProperties(self):
    #     self.targetStim.size = self.originalTargetSize

    # def drawCalibrationTarget(self, tp):
    #     self.targetStim.setPos(tp)
    #     self.targetStim.draw()
    #     return self.window.flip(clearBuffer=True)




# --- Thread 3: Data Processor ---
class DataProcessor(threading.Thread):
    def __init__(self,name, data_queue, filtering_values_lock, stop_event, calculation_period_ms=100, logfolder=None):
        super().__init__(name=name)
        self.data_queue = data_queue
        self.filtering_values_lock = filtering_values_lock
        self.stop_event = stop_event
        self.stored_data = []
        self.calculation_period_s = calculation_period_ms / 1000.0
        self.last_calculation_time = time.monotonic()
        self.processing_count = 0
        self.window_size = 100  # Number of samples to consider for filtering calculations

        # Data storgage
        if logfolder is None:
            self.logfolder = os.getcwd() + "/data_logs"
        else:
            self.logfolder = logfolder #path to logfolder
        self.logfile = None #path to logfile

    def run(self, logname='DPIDataLog.json'):
        self.createDataLog(logname) # Create a log file for data storage
        while not self.stop_event.is_set() or not self.data_queue.empty():
            try:
                data = self.data_queue.get() # Small timeout to allow checking stop_event
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
                # Log data to file
                if self.logfile is not None:
                    self.logData(self.stored_data[:-self.window_size]) # Log all but the last window_size items
                    self.stored_data = self.stored_data[-self.window_size:]  # Keep only the last window_size items

            # Avoid busy-waiting if queue is empty and not time for calculation
            if self.data_queue.empty() and (current_time - self.last_calculation_time < self.calculation_period_s):
                time.sleep(0.005) # Short sleep to yield control

        # Final calculation if there's any remaining data after stopping
        if self.stored_data:
            self.calculate_and_update_filters()
        # Log final data
        if self.logfile is not None:
            self.logData(self.stored_data)
            self.stored_data = []  # Clear stored data after logging

        print(f"{self.name} stopped. Processed {self.processing_count} items. Final stored data count: {len(self.stored_data)}. Location: {self.logfile}")

    def calculate_and_update_filters(self):
        try:
            try:
                pupil_areas = [data[1].pupil_area for data in self.stored_data[-self.window_size:] if data is not None]
                pupil_positions = np.array([[data[0][0], data[0][1]] for data in self.stored_data[-self.window_size:] if data is not None])
                pupil_pos_times = np.array([data[2] for data in self.stored_data[-self.window_size:] if data is not None])
                pupil_speeds = np.linalg.norm(np.diff(pupil_positions, axis=0), axis=1)/ np.diff(pupil_pos_times)
            except IndexError:
                print("Not enough data to calculate filters.")
                return False
            except TypeError:
                print("Data format error, expected structured data.")
                return False
            except Exception as e:
                print(f"Unexpected error: {e}")
                return False

            if pupil_areas:
                new_pupil_min = np.mean(pupil_areas) - np.std(pupil_areas) * 3
                new_pupil_max = np.mean(pupil_areas) + np.std(pupil_areas) * 3
                new_P4_speed = np.mean(pupil_speeds) + np.std(pupil_speeds) * 10 #This might need to be a constant value to account for saccades or have a singificantly larger sd multiplier
            else:
                return False

            # Update global filtering values safely
            with self.filtering_values_lock:
                filtering_values['pupil_area']['min'] = new_pupil_min
                filtering_values['pupil_area']['max'] = new_pupil_max
                filtering_values['P4_speed'] = new_P4_speed
            
            return True
        except Exception as e:
            print(f"Error calculating filters: {e}")
            return False
    
    def createDataLog(self, filename):
        os.makedirs(self.logfolder, exist_ok=True)
        self.logfile = self.logfolder + "/" + filename
        if not os.path.exists(self.logfile ):
            with open(self.logfile, 'w') as f:
                pass

    def logData(self, data):
        try:
            with open(self.logfile, 'a') as f:
                json_string = json.dumps(data, cls=NumpyEncoder)
                f.write(json_string + '\n')
        except IOError as e:
            print(f"Error appending to file '{self.logfile}': {e}")
        except TypeError as e:
            print(f"Error serializing data: {e}. Please provide JSON-serializable data.")



# --- Main execution ---
if __name__ == "__main__":
    with open('calibration_settings.yaml', 'r') as f:
        calibration_args = yaml.safe_load(f)
    
    eyetracker = DPIEyeTracker()
    eyetracker.runSetupProcedure(calibration_args=calibration_args)
    
    collector_thread = DataCollector(
        "CollectorThread", eyetracker, filtered_data_queue, screen_position_queue, filtering_values_lock, stop_event
    )
    renderer_thread = Renderer(
        "RendererThread", screen_position_queue, stop_event
    )     
    processor_thread = DataProcessor(
        "ProcessorThread", filtered_data_queue, filtering_values_lock, stop_event, calculation_period_ms=100
    )

    collector_thread.start()
    processor_thread.start()
    renderer_thread.start()

    try:
        # Let the threads run for a while
        run_duration_seconds = 10
        print(f"Running for {run_duration_seconds} seconds...")
        for i in range(run_duration_seconds * 10): # Check every 100ms
            time.sleep(0.1)
            with filtering_values_lock:
                print(f"Main thread: Current filters: {filtering_values}. Filter queue size: {filtered_data_queue.qsize()}. Screen queue size: {screen_position_queue.qsize()}")

    except KeyboardInterrupt:
        print("\nCtrl+C detected. Signaling threads to stop...")
    
    finally:
        stop_event.set() # Signal both threads to stop
        collector_thread.join() # Wait for collector to finish
        processor_thread.join() # Wait for processor to finish

    print("All threads finished.")
    print(f"Final stored data sample (last 20 items): {processor_thread.stored_data[-20:]}")