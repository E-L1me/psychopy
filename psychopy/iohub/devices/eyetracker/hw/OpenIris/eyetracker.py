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
        self.screen_thresh = {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0}
        self.pupil_area_thresh = {'max': 0.0, 'min': 0.0}
        self.P4_thresh = {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0}
        self.CR_thresh = {'maxx': 0.0, 'minx': 0.0, 'maxy': 0.0, 'miny': 0.0}
        self.P4_speed_thresh = 0.0
        

    def _connectEyetracker(self):
        """Connect to the OpenIris client."""
        self.setConnectionState(True)
        self._client = OpenIrisClient()

    def isConnected(self):
        """Check if the OpenIris client is connected.
        """
        return self._client is not None

    def setConnectionState(self, enable):
        """
        Set the connection state of the OpenIris client.
        Parameters:
            enable (bool): True to connect, False to disconnect.
        Returns:
            bool: True if the connection is established, False otherwise."""
        if enable and self._client is None:
            self._connectEyetracker()
        elif enable is False and self._client:
            self._client = None
        return self.isConnected()

    def isRecordingEnabled(self):
        """Check if the OpenIris client is recording.
        Returns:
            bool: True if the client is recording, False otherwise.
        """
        return self._recording

    def setRecordingState(self, recording):
        """Set the recording state of the OpenIris client.
        Parameters:
            recording (bool): True to start recording, False to stop.
        Returns:
            bool: True if the recording state is set, False otherwise.
        """
        current_state = self.isRecordingEnabled()
        if recording and current_state is not True:
            self._recording = True
            self.setConnectionState(True)
        elif recording is not True and current_state:
            self._recording = False
            self._latest_data = None
            self._lastEventTime = 0
        return self.isRecordingEnabled()

    def filter(self, data):
        """Filter the eye data based on calibration values.
        Parameters:
            data (EyeData): The eye data to filter.
        Returns:
            bool: True if the data is valid, False if it is erroneous.
        """
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
            if dt <= 0:
                print("Warning: dt is zero or negative, cannot calculate speed.")
                return False
            speed = np.linalg.norm(dd) / dt

            if speed >= self.P4_speed_thresh:
                return False
        
        return True

    def updateFilteringValues(self, screen_thresh=None, pupil_area_thresh=None, P4_thresh=None, CR_thresh=None, P4_speed_thresh=None):
        """Update the filtering values used for data processing.
        Parameters:
            screen_thresh (dict): Thresholds for screen coordinates {'maxx': float, 'minx': float, 'maxy': float, 'miny': float}
            pupil_area_thresh (dict): Thresholds for pupil area {'max': float, 'min': float}
            P4_thresh (dict): Thresholds for P4 coordinates {'maxx': float, 'minx': float, 'maxy': float, 'miny': float}
            CR_thresh (dict): Thresholds for CR coordinates {'maxx': float, 'minx': float, 'maxy': float, 'miny': float}
            P4_speed_thresh (float): Speed threshold for P4 movement
        Returns:
            None
        """
        if screen_thresh is not None:
            self.screen_thresh = screen_thresh
        if pupil_area_thresh is not None: # Continuously updated
            self.pupil_area_thresh = pupil_area_thresh
        if P4_thresh is not None:
            self.P4_thresh = P4_thresh
        if CR_thresh is not None:
            self.CR_thresh = CR_thresh
        if P4_speed_thresh is not None: # Continuously updated
            self.P4_speed_thresh = P4_speed_thresh

    def find_pos(self, data):
        """Find the position of the eye based on calibrated regression.
        Uses the calibration coefficients to calculate the position.
        Parameters:
            data (EyeData): The eye data containing the necessary fields.
        Returns:
            - A Numpy array object representing the eye position, [x, y].
            - If the data is not valid, returns None.
        """
        try:
            if data is None:
                print("No data available.")
                return None
            if self.cal is None:
                print("Calibration coefficients are not set.")
                return None
            x = data.cr.x - data.p4.x
            y = data.cr.y - data.p4.y
            X = np.array([1,x,y,x**2,y**2,x * y])
            Y = X @ self.cal
            return Y
        except Exception as e:
            return None

    def interpolate(self): 
        """To be implemented:
        Interpolate missing data based on the last valid data point.
        alpha-beta interpolation or similar methods can be used."""
        return None, None, 0

    def _poll(self, filter=True, interpolate=False): #ADD: log point in separate location if it is filtered out
        """ Poll the OpenIris client for the latest eye data.
        Parameters:
            filter (bool): Whether to apply filtering to the data.
            interpolate (bool): Whether to interpolate missing data.
        Returns:
            - position: The processed eye position.
            - raw_data: The latest eye data.
            - data_time: The timestamp of the latest eye data.
            - marker: An integer indicating the type of data returned:
                0: Filtered data
                1: Interpolated data (if interpolate is True)
                2: No data (if no interpolation and data is filtered, if the client is not connected, recording is not enabled)
                3: Unfiltered data
        """
        if self.isConnected() and self.isRecordingEnabled():
            self.last_data = self._latest_data
            self.last_data_time = self._latest_data_time
            # Fetch the next data point from the OpenIris client
            try:
                self._latest_data, self._latest_data_time = self._client.fetch_next_data(True)
            except Exception as e:
                print(f"Error fetching data from OpenIris client: {e}")
                return [None, None, None, 2]
            if filter:
                if self.filter(self._latest_data):
                        return [self.find_pos(self._latest_data), self._latest_data, self._latest_data_time, 0]
                else: #erroneous data
                    if interpolate: # interpolate missing data
                        position, self._latest_data, self._latest_data_time = self.interpolate()
                        return [position, self._latest_data, self._latest_data_time, 1]
                    else: # void data
                        self._latest_data = None
                        self._latest_data_time = 0
                        return [None, None, None, 2]
            else:
                return [self.find_pos(self._latest_data), self._latest_data, self._latest_data_time, 3]
        else:
            # If the client is not connected or recording is not enabled, return None with a marker
                if self._latest_data is not None:
                    self._latest_data = None
                    self._latest_data_time = 0
                return [None, None, None, 2]

    def runSetupProcedure(self, calibration_args={}):
        """
        Run calibration and establish filtering values.
        Parameters:
            calibration_args (dict): Arguments for the calibration procedure.
        Returns:
            None
        """
        try:
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
            
            return True
        except Exception as e:
            print(f"Error during setup procedure: {e}")
            return False