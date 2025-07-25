from psychopy.iohub.devices.eyetracker import EyeTrackerDevice
import math
import numpy as np
import os
import json
import time
from psychopy.iohub.devices.eyetracker.hw.OpenIrirs.calibration import DPICalibrationProcedure
from psychopy.iohub.devices.eyetracker.hw.OpenIrirs.client import OpenIrisClient

class  DPIEyeTracker(EyeTrackerDevice):
    """
    Eyetracker to run with OpenIris for real-time eyetracking experiments

    Functionality: 
    - Connect to OpenIris client
    - Fetch eye data
    - Filter data based on calibration values
        - Be able to provide data unfiltered
    - Return raw and processed eye data
    - Run setup procedure
    - Log erroneous data
    - Update filtering values
    - Interpolate missing data
    - data should come with a marker: [1] unfiltered raw, [2] filtered raw, [3] erroneous raw, [4] real position, [5] interpolated position, [6] none
    """

    def __init__(self, *args, **kwargs):
        EyeTrackerDevice.__init__(self, *args, **kwargs)
        config = self.getConfiguration()
        self._latest_data = None
        self._latest_data_time = 0

        # OpenIris client
        self._client = None
        self._recording = False
        self._lastEventTime = 0
        
        self.last_data = None
        self.last_data_time = 0

        # filtering values
        self.cal = None
        self.screen_thresh = None
        self.pupil_area_thresh = None
        self.P4_thresh = None
        self.CR_thresh = None
        self.P4_speed_thresh = None

    def _connectEyetracker(self):
        super.setConnectionState(True)
        self._client = OpenIrisClient()

    def isConnected(self):
        return self._client is not None

    def setConnectionState(self, enable):
        if enable and self._client is None:
            self._connectEyetracker()
        elif enable is False and self._client:
            self._client = None
        return self.isConnected()

    def isRecordingEnabled(self):
        return self.recording

    def setRecordingState(self, recording):
        current_state = self.isRecordingEnabled()
        if recording and current_state is not True:
            self._recording = True
            super().setConnectionState(True)
        elif recording is not True and current_state:
            self.recording = False
            self._latest_data = None
            self._lastEventTime = 0
        return self.isRecordingEnabled()

    def filter(self, data):
        if data is None:
            return False
        # check pupil area, blink protection
        if not (self.pupil_area_thresh['min'] <= data.pupil_area <= self.pupil_area_thresh['max']):
            return False
        #check P4
        if not (self.P4_thresh['minx'] <= data.p4.x <= self.P4_thresh['maxx'] and
                self.P4_thresh['miny'] <= data.p4.y <= self.P4_thresh['maxy']):
            return False
        #check CR
        if not (self.CR_thresh['minx'] <= data.cr.x <= self.CR_thresh['maxx'] and
                self.CR_thresh['miny'] <= data.cr.y <= self.CR_thresh['maxy']):
            return False

        #check P4 speed
        if self.last_data is not None and self.last_data_time > 0:
            dd = np.array([data.P4.x - self.last_data.P4.x, data.P4.y - self.last_data.P4.y])
            dt = self._latest_data_time - self.last_data_time
            speed = np.linalg.norm(dd) / dt

            if speed >= self.P4_speed_thresh:
                return False
        
        return True

    def updateFilteringValues(self, screen_thresh=None, pupil_area_thresh=None, P4_thresh=None, CR_thresh=None, P4_speed_thresh=None):
        if screen_thresh is not None:
            self.screen_thresh = screen_thresh
        if pupil_area_thresh is not None:
            self.pupil_area_thresh = pupil_area_thresh
        if P4_thresh is not None:
            self.P4_thresh = P4_thresh
        if CR_thresh is not None:
            self.CR_thresh = CR_thresh
        if P4_speed_thresh is not None:
            self.P4_speed_thresh = P4_speed_thresh

    def find_pos(self, data):
        x = data.cr.x - data.p4.x
        y = data.cr.y - data.p4.y
        X = np.array([1,x,y,x**2,y**2,x * y])
        Y = X @ self.cal
        return Y

    def interpolate(self): 
        """To be implemented:
        Interpolate missing data based on the last valid data point.
        alpha-beta interpolation or similar methods can be used."""
        return None
        pass

    def _poll(self, screen=True, calibration=False, filter=True, interpolate=False): #ADD: log point in separate location if it is filtered out
        if self.isConnected() and self.isRecordingEnabled():
            self.last_data = self._latest_data
            self.last_data_time = self._latest_data_time
            # Fetch the next data point from the OpenIris client
            self._latest_data, self._latest_data_time = self._client.fetch_next_data(True)
            if filter:
                if self.filter(self._latest_data):
                    if calibration and screen:
                        # real position, with time
                        return self.find_pos(self._latest_data), self._latest_data_time, 4
                    elif calibration:
                        # filtered raw, with time
                        return self._latest_data, self._latest_data_time, 2
                    if screen:
                        # real position
                        return self.find_pos(self._latest_data), 4
                    else:
                        # filtered raw
                        return self._latest_data, 2
                else:
                    # If the data is filtered out, return None with a marker for filtered data
                    if interpolate:
                        self._latest_data, self._latest_data_time = self.interpolate()
                        return self._latest_data, 5
                    ret_raw = self._latest_data
                    ret_time = self._latest_data_time
                    self._latest_data = None
                    self._latest_data_time = 0
                    return ret_raw, ret_time, 3
            else:
                return self._latest_data, self._latest_data_time, 1
        else:
            # If the client is not connected or recording is not enabled, return None with a marker
                if self._latest_data is not None:
                    self._latest_data = None
                    self._latest_data_time = 0
                return None, 6

    def runSetupProcedure(self, calibration_args={}):
        """
        Run calibration and establish filterig values
        """
        calibration = DPICalibrationProcedure(self, calibration_args)
        calibration.runCalibration()
        self.cal = calibration.cal
        self.screen_thresh = calibration.screen_thresh
        self.pupil_area_thresh = calibration.pupil_area_thresh
        self.P4_thresh = calibration.P4_thresh
        self.CR_thresh = calibration.CR_thresh
        self.P4_speed_thresh = calibration.P4_speed_thresh

        self.setConnectionState(True)
        self.setRecordingState(True)