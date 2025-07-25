import numpy as np
import time
from psychopy.iohub.devices.eyetracker.calibration import BaseCalibrationProcedure

from psychopy import visual, layout
import gevent
from psychopy.iohub.util import convertCamelToSnake, updateSettings, createCustomCalibrationStim
from psychopy.iohub.devices import DeviceEvent, Computer
from psychopy.iohub.constants import EventConstants as EC
from psychopy.iohub.devices.keyboard import KeyboardInputEvent
from psychopy.iohub.errors import print2err
from psychopy.constants import PLAYING

currentTime = Computer.getTime



class DPICalibrationProcedure(BaseCalibrationProcedure):

    def __init__(self, eyetrackerInterface, calibration_args):
        BaseCalibrationProcedure.__init(self, eyetrackerInterface, calibration_args, allow_escape_in_progress=True)
        self.eyetracker = eyetrackerInterface
        
        #dataset
        self.dataset = [] #dataset structured in the form = {'screen_point': eye dataset, ....}

        #output values
        self.cal = None
        self.pupil_area_thresh = {'max': 0.0, 'min': 0.0}
        self.P4_thresh = {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0} #values to check if P4 is within calibrated range
        self.CR_thresh = {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0} #values to check if CR is within calibrated range
        self.screen_thresh = {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0} #values to check if position on screen is within calibrated range
        self.P4_speed_thresh = 0.0 #speed threshold for P4 movement

    def runCalibration(self):
        """Run Calibration Sequence
        """

        if self.showIntroScreen() is False:
            return False
        
        target_delay = super().getCalibSetting('target_delay')
        target_duration = super().getCalibSetting('target_duration')
        auto_pace =  super().getCalibSetting('auto_pace')
        randomize_points =  super().getCalibSetting('randomize')
        if randomize_points is True:
            super().cal_target_list = super().CALIBRATION_POINT_LIST[1:]
            import random
            random.seed(None)
            random.shuffle(self.cal_target_list)
            self.cal_target_list.insert(0, self.CALIBRATION_POINT_LIST[0])

        left, top, right, bottom = self._eyetracker.display_device.getCoordBounds()
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

            self.clearAllEventBuffers()

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
            self.MsgPump()
            msg = self.getNextMsg()
            if self.allow_escape and msg == 'QUIT':
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
                self.dataset[-1]['data'].append(self.eyetracker._poll())

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
                    self.dataset[-1]['data'].append([self.eyetracker._poll(), time.time()])
                    if self.targetClassHasPlayPause and self.targetStim.status == PLAYING:
                        self.targetStim.draw()
                        self.window.flip()
                    gevent.sleep(0.001)
                    self.MsgPump()
                    msg = self.getNextMsg()
                    if msg == 'SPACE_KEY_ACTION': 
                        break
                    elif self.allow_escape and msg == 'QUIT':
                        abort_calibration = True
                        break
            
            gevent.sleep(0.001)
            self.MsgPump()
            msg = self.getNextMsg()
            while msg:
                if self.allow_escape and msg == 'QUIT':
                    abort_calibration = True
                    break
                gevent.sleep(0.001)
                self.MsgPump()
                msg = self.getNextMsg()
            
            self.registerCalibrationPointHook(pt)

            self.clearCalibrationWindow()
            self.clearAllEventBuffers()
            i += 1
        
        if self.targetClassHasPlayPause:
            self.targetStim.pause()
        
        self.finishCalibrationHook(abort_calibration)

        if abort_calibration is False:
            self.showFinishedScreen()
        
        X = []
        Y = []
        data_medians = []
        for point in self.dataset:
            data = [d for d in point['data']]
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
        return True
    
    def showIntroScreen(self, text_msg='Press SPACE to Start Calibration; Press ESCAPE to Exit.'):

        self.clearAllEventBuffers()

        while True:
            self.textLineStim.setText(text_msg)
            self.textLineStim.draw()
            self.window.flip()

            msg = self.getNextMsg()
            if msg == 'SPACE_KEY_ACTION':
                self.clearAllEventBuffers()
                return True
            elif msg == 'QUIT':
                self.clearAllEventBuffers()
                return False
            self.MsgPump()
            gevent.sleep(0.001)
    
    def showFinishedScreen(self, text_msg="Calibration Complete. Press 'SPACE' key to continue."):
        
        self.clearAllEventBuffers()

        while True:
            self.textLineStim.setText(text_msg)
            self.textLineStim.draw()
            self.window.flip()

            msg = self.getNextMsg()
            if msg in ['SPACE_KEY_ACTION', 'QUIT']:
                self.clearAllEventBuffers()
                return True
            
            self.MsgPump()
            gevent.sleep(0.001)
    
    def getCalibMatrix(self):
        pass

    def getThresholdValues(self):
        pass

    def saveCalibrationData(self, data):
        pass


        