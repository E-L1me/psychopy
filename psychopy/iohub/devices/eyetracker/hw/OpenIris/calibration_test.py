import sys
import subprocess
import numpy as np
import time
import yaml
import queue
import threading
import os
import json

# def install_keyboard_library():
#     """
#     Checks if the 'keyboard' library is installed and installs it if it isn't.
#     """
#     try:
#         # Attempt to import the library
#         import keyboard
#         print("The 'keyboard' library is already installed.")
#     except ImportError:
#         print("The 'keyboard' library was not found. Installing now...")
#         try:
#             # Use subprocess to run the pip install command
#             subprocess.check_call([sys.executable, "-m", "pip", "install", "keyboard"])
#             print("Successfully installed the 'keyboard' library.")
#             # Now that it's installed, we can import it
#             import keyboard
#         except subprocess.CalledProcessError as e:
#             print(f"Error during installation: {e}")
#             sys.exit("Could not install the 'keyboard' library. Please install it manually.")

        # install_keyboard_library()
import keyboard  # Ensure this is imported after installation

import gevent

from psychopy import visual, layout
from psychopy.iohub.util import convertCamelToSnake, updateSettings, createCustomCalibrationStim
from psychopy.iohub.devices import DeviceEvent, Computer
from psychopy.iohub.constants import EventConstants as EC
from psychopy.iohub.devices.keyboard import KeyboardInputEvent
from psychopy.iohub.errors import print2err
from psychopy.constants import PLAYING
from psychopy.tools.stimulustools import actualize


currentTime = Computer.getTime

target_position_count = dict(THREE_POINTS=3,
                             FIVE_POINTS=5,
                             NINE_POINTS=9,
                             THIRTEEN_POINTS=13)
target_positions = dict()
target_positions[3] = [(0.5, 0.1), (0.1, 0.9), (0.9, 0.9)]
target_positions[5] = [(0.5, 0.5), (0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
target_positions[9] = [(0.5, 0.5), (0.1, 0.5), (0.9, 0.5), (0.1, 0.1), (0.5, 0.1),
                       (0.9, 0.1), (0.9, 0.9), (0.5, 0.9), (0.1, 0.9)]
target_positions[13] = [(0.5, 0.5), (0.1, 0.5), (0.9, 0.5), (0.1, 0.1), (0.5, 0.1),
                        (0.9, 0.1), (0.9, 0.9), (0.5, 0.9), (0.1, 0.9), (0.25, 0.25),
                        (0.25, 0.75), (0.75, 0.75), (0.75, 0.25)]


class DPICalibrationProcedure():
    CALIBRATION_POINT_LIST = target_positions[9]


    def __init__(self, eyetrackerInterface, calibration_args, allow_escape_in_progress=True):
        self.eyetracker = eyetrackerInterface
        self.allow_escape = allow_escape_in_progress
        self.screenSize = [1920, 1080]
        self.height = self.screenSize[1]
        self.targetClassHasPlayPause = False
        self.targetStim = None
        self.targetClassHasPlayPause = False
        self._ioKeyboard = None
        self._msg_queue = None
        self._lastCalibrationOK = False

        self._calibration_args = calibration_args
        unit_type = self.getCalibSetting('unit_type')
        color_type = self.getCalibSetting('color_type')
        cal_type = self.getCalibSetting('type')
        monitor_name = self.getCalibSetting('monitor_name')
        if cal_type in target_position_count:
            num_points = target_position_count[cal_type]
            DPICalibrationProcedure.CALIBRATION_POINT_LIST = target_positions[num_points]
        self.cal_target_list = self.CALIBRATION_POINT_LIST

        self.window = visual.Window(
            self.screenSize,
            monitor=monitor_name,
            units=unit_type,
            fullscr=True,
            allowGUI=False,
            color=self.getCalibSetting(['screen_background_color']),
            colorSpace=color_type)
        self.window.setMouseVisible(True)
        self.window.flip(clearBuffer=True)

        self.createGraphics()
        self._registerEventMonitors()
        self._lastMsgPumpTime = currentTime()

        #dataset
        self.dataset = [] #dataset structured in the form = {'screen_point': eye dataset, ....}

        #output values
        self.cal = None
        self.pupil_area_thresh = {'max': 0.0, 'min': 0.0}
        self.P4_thresh = {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0} #values to check if P4 is within calibrated range
        self.CR_thresh = {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0} #values to check if CR is within calibrated range
        self.screen_thresh = {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0} #values to check if position on screen is within calibrated range
        self.P4_speed_thresh = 0.0 #speed threshold for P4 movement

    def getCalibSetting(self, setting):
        if isinstance(setting, str) and setting is not None and setting in self._calibration_args:
            return self._calibration_args[setting]
        
    def getNextMsg(self):
        if len(self._msg_queue) > 0:
            self._msg_queue.clear()
            while msg is not None:
                try:
                    msg = self._msg_queue.get_nowait()
                except queue.Empty:
                    msg = None
            return msg
        
    def createGraphics(self):
        """
        """
        color_type = self.getCalibSetting('color_type')
        unit_type = self.getCalibSetting('unit_type')

        # get attributes to create target
        targetAttrs = self._calibration_args.get('target_attributes').copy()
        # Remove unsupported keys
        for key in ['outer_diameter', 'inner_diameter', 'outer_fill_color', 'outer_line_color',
                    'outer_stroke_width', 'inner_fill_color', 'inner_line_color', 'inner_stroke_width', 'animate']:
            targetAttrs.pop(key, None)
        # Set required arguments for TargetStim
        targetAttrs['win'] = self.window
        targetAttrs['pos'] = (0, 0)  # or whatever position you want
        targetAttrs['size'] = 60     # or whatever size you want
        targetAttrs['__module__'] = 'psychopy.visual.target'
        targetAttrs['__class__'] = 'TargetStim'

        self.targetStim = actualize(targetAttrs)
        
        self.targetStim = actualize(targetAttrs)

        self.originalTargetSize = self.targetStim.size
        self.targetClassHasPlayPause = hasattr(self.targetStim, 'play') and hasattr(self.targetStim, 'pause')

        self.imagetitlestim = None

        tctype = color_type
        tcolor = self.getCalibSetting(['text_color'])
        if tcolor is None:
            # If no calibration text color provided, base it on the window background color
            from psychopy.iohub.util import complement
            sbcolor = self.getCalibSetting(['screen_background_color'])
            if sbcolor is None:
                sbcolor = self.window.color
            from psychopy.colors import Color
            tcolor_obj = Color(sbcolor, color_type)
            tcolor = complement(*tcolor_obj.rgb255)
            tctype = 'rgb255'

        instuction_text = 'Press SPACE to Start Calibration; ESCAPE to Exit.'
        self.textLineStim = visual.TextStim(self.window, text=instuction_text,
                                            pos=(0, 0), height=36,
                                            color=tcolor, colorSpace=tctype,
                                            units='pix', wrapWidth=self.width * 0.9)

    def runCalibration(self, _msg_queue):
        self._msg_queue = _msg_queue
        """Run Calibration Sequence
        """

        print("Starting Calibration Procedure")

        if self.showIntroScreen() is False:
            print("Calibration Procedure Aborted")
            return False

        target_delay = self.getCalibSetting('target_delay')
        target_duration = self.getCalibSetting('target_duration')
        auto_pace = self.getCalibSetting('auto_pace')
        randomize_points = self.getCalibSetting('randomize')
        if randomize_points is True:
            self.cal_target_list = self.CALIBRATION_POINT_LIST[1:]
            import random
            random.seed(None)
            random.shuffle(self.cal_target_list)
            self.cal_target_list.insert(0, self.CALIBRATION_POINT_LIST[0])

        left, top, right, bottom = self._eyetracker._display_device.getCoordBounds()
        w, h = right - left, top - bottom

        self.clearCalibrationWindow()

        self.startCalibrationHook()

        i = 0
        abort_calibration = False
        for pt in self.cal_target_list:
            if abort_calibration:
                break
            x, y = left + w * pt[0], bottom + h*(1.0-pt[1])
            start_time = currentTime()

            animate_enable = self.getCalibSetting(['target_attributes', 'animate', 'enable'])
            animate_expansion_ratio = self.getCalibSetting(['target_attributes', 'animate', 'expansion_ratio'])
            animate_contract_only = self.getCalibSetting(['target_attributes', 'animate', 'contract_only'])

            self.dataset.append({'x': x, 'y': y, 'data': []})

            while currentTime()-start_time <= target_delay:

                if animate_enable and i > 0:
                    t = (currentTime()-start_time) / target_delay
                    v1 = self.cal_target_list[i-1]
                    v2 = pt
                    t = 60.0 * ((1.0 / 10.0) * t ** 5 - (1.0 / 4.0) * t ** 4 + (1.0 / 6.0) * t ** 3)
                    mx, my = ((1.0 - t) * v1[0] + t * v2[0], (1.0 - t) * v1[1] + t * v2[1])
                    moveTo = left + w * mx, bottom + h * (1.0 - my)
                    self.drawCalibrationTarget(moveTo)
                elif animate_enable is False:
                    if self.targetClassHasPlayPause and self.targetStim.status == PLAYING:
                        self.targetStim.pause()
                    self.window.flip(clearBuffer=True)
            
            gevent.sleep(0.001)
            msg = self.getNextMsg()
            if self.allow_escape and msg == 'q':
                abort_calibration = True
                break

            self.resetTargetProperties()
            if self.targetClassHasPlayPause and self.targetStim.status != PLAYING:
                self.targetStim.play()
            self.drawCalibrationTarget((x,y))

            start_time = currentTime()
            stim_size = self.targetStim.size[0]
            min_stim_size = self.targetStim.size[0] / animate_expansion_ratio
            if hasattr(self.targetStim, 'minSize'):
                min_stim_size = self.targetStim.minSize[0]
            
            while currentTime() - start_time <= target_duration:
                elapsed_time = currentTime() - start_time 
                new_size = t = None
                self.dataset[-1]['data'].append(self.eyetracker._poll_basic(), time.time())

                if animate_contract_only:
                    t = elapsed_time / target_duration
                    new_size = stim_size - t * (stim_size - min_stim_size)
                elif animate_expansion_ratio not in [1, 1.0]:
                    if elapsed_time <= target_duration / 2:
                        t = elapsed_time / (target_duration/2)
                        new_size = stim_size + t * (stim_size * animate_expansion_ratio - stim_size)
                    else: 
                        t = (elapsed_time - target_duration/2) / (target_duration / 2)
                        new_size = stim_size* animate_expansion_ratio - t * (stim_size * animate_expansion_ratio - min_stim_size)
                if new_size:
                    self.targetStim.size = new_size, new_size
                
                
                self.targetStim.draw()
                self.window.flip()
            
            if auto_pace is False:
                while 1: 
                    self.dataset[-1]['data'].append([self.eyetracker._poll_basic(), time.time()])
                    if self.targetClassHasPlayPause and self.targetStim.status == PLAYING:
                        self.targetStim.draw()
                        self.window.flip()
                    gevent.sleep(0.001)
                    msg = self.getNextMsg()
                    if msg == 'space': 
                        break
                    elif self.allow_escape and msg == 'q':
                        abort_calibration = True
                        break
            
            gevent.sleep(0.001)
            msg = self.getNextMsg()
            while msg:
                if self.allow_escape and msg == 'q':
                    abort_calibration = True
                    break
                gevent.sleep(0.001)
                msg = self.getNextMsg()
            
            self.registerCalibrationPointHook(pt)

            self.clearCalibrationWindow()
            i += 1
        
        if self.targetClassHasPlayPause:
            self.targetStim.pause()
        
        if abort_calibration is False:
            self.showFinishedScreen()
        
        self.calculateCalibration()

        self._msg_queue = None  # Clear the message queue reference

        return True

    def calculateCalibration(self):
        X = []
        Y = []
        data_medians = []
        try:
            for point in self.dataset:
                data = [d for d in point['data']]
                data = [[d[0]['Right'], d[1]] for d in data if d[0] is not None]
                if len(data) > 0:
                    CRP4s = [(d[0].CR.x-d[0].P4.x, d[0].CR.y-d[0].P4.y) for d in data if d is not None]
                    median_CRP4x = np.median([d[0] for d in CRP4s])
                    median_CRP4y = np.median([d[1] for d in CRP4s])
                    X.append([median_CRP4x, median_CRP4y])
                    Y.append([point['x'], point['y']])

                    median_P4x = np.median([d[0].P4.x for d in data if d is not None])
                    median_P4y = np.median([d[0].P4.y for d in data if d is not None])
                    median_CRx = np.median([d[0].CR.x for d in data if d is not None])
                    median_CRy = np.median([d[0].CR.y for d in data if d is not None])
                    median_pupil_area = np.median([d[0].pupil_area for d in data if d is not None])
                    dd = np.linalg.norm(np.diff([[d[0].P4.x, d[0].P4.y] for d in data if d is not None], axis=0), axis=1)
                    dt = np.diff([d[1] for d in data if d is not None])
                    speeds = dd / dt
                    median_speed = np.median(speeds) if len(speeds) > 0 else print("ERROR: No speeds calculated")
                    data_medians.append({
                        'screen_point': point,
                        'median_P4': (median_P4x, median_P4y),
                        'median_CR': (median_CRx, median_CRy),
                        'median_pupil_area': median_pupil_area,
                        'median_speed': median_speed,
                    })
                else:
                    print(f"ERROR: failed to collect data for {point['x'], point['y']}")
        
            self.cal = np.linalg.pinv(X) @ Y
            self.pupil_area_thresh = {'max': np.max([d['median_pupil_area'] for d in data_medians]),
                                    'min': np.min([d['median_pupil_area'] for d in data_medians])}
            self.P4_thresh = {'maxx': np.max([d['median_P4'][0] for d in data_medians]),
                            'minx': np.min([d['median_P4'][0] for d in data_medians]),
                            'maxy': np.max([d['median_P4'][1] for d in data_medians]),
                            'miny': np.min([d['median_P4'][1] for d in data_medians])}
            self.CR_thresh = {'maxx': np.max([d['median_CR'][0] for d in data_medians]),
                            'minx': np.min([d['median_CR'][0] for d in data_medians]),
                            'maxy': np.max([d['median_CR'][1] for d in data_medians]),
                            'miny': np.min([d['median_CR'][1] for d in data_medians])}
            self.P4_speed_thresh = np.max([d['median_speed'] for d in data_medians]) + 10 * np.std([d['median_speed'] for d in data_medians])
        
        except Exception as e:
            print2err(f"Error calculating calibration: {e}")
            self.cal = None
            self.pupil_area_thresh = None
            self.P4_thresh = None
            self.CR_thresh = None
            self.P4_speed_thresh = None


    def showIntroScreen(self, text_msg='Press SPACE to Start Calibration; Press ESCAPE to Exit.'):

        while True:
            self.textLineStim.setText(text_msg)
            self.textLineStim.draw()
            self.window.flip()

            msg = self.getNextMsg()
            if msg == 'space':
                return True
            elif msg == 'q':
                return False
            gevent.sleep(0.001)
    
    def showFinishedScreen(self, text_msg="Calibration Complete. Press 'SPACE' key to continue."):
        
        while True:
            self.textLineStim.setText(text_msg)
            self.textLineStim.draw()
            self.window.flip()

            msg = self.getNextMsg()
            if msg in ['space', 'q']:
                return True
            
            gevent.sleep(0.001)
    
    def resetTargetProperties(self):
        self.targetStim.size = self.originalTargetSize

    def drawCalibrationTarget(self, tp):
        self.targetStim.setPos(tp)
        self.targetStim.draw()
        return self.window.flip(clearBuffer=True)
    
    def getCalibMatrix(self):
        return self.cal

    def getThresholdValues(self):
        return {
            'pupil_area': self.pupil_area_thresh,
            'P4': self.P4_thresh,
            'CR': self.CR_thresh,
            'P4_speed': self.P4_speed_thresh
        }

    def saveCalibrationData(self, data, name):
        path_to_self = os.path.abspath(__file__)
        self_dir = os.path.dirname(path_to_self)
        path = os.path.join(self_dir, f"{name}.json")
        with open(path, 'w') as f:
            json.dump(data, f)

class KeyboardListener(threading.Thread):
    def __init__(self, key_queue, _stop_event, key_list= ['esc', 'space', 'q']):
        super().__init__()
        self.key_queue = key_queue
        self._stop_event = _stop_event
        self.key_list = key_list  # Add other keys as needed

    def run(self):
        def on_key(event):
            if event.event_type == 'down' and event.name in self.key_list:
                self.key_queue.put(event.name)
        keyboard.hook(on_key)
        while not self._stop_event.is_set():
            time.sleep(0.1)
            
    def stop(self):
        self._stop_event.set()
        keyboard.unhook_all()