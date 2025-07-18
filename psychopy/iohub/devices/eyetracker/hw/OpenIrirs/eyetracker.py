from psychopy.iohub.devices.eyetracker import EyeTrackerDevice
from . import OpenIrisClient
import math
import numpy
import os
import json

class  EyeTracker(EyeTrackerDevice):
    """
    Eyetracker to run with OpenIris for real-time eyetracking experiments
    """

    def __init__(self, *args, **kwargs):
        EyeTrackerDevice.__init__(self, *args, **kwargs)
        config = self.getConfiguration()
        self._latest_data = None

        self._client = None
        self._recording = False
        self._lastEventTime = 0
        self.logfolder = None #path to logfolder
        self.logfile = None #path to logfile
        self.filename = None
        self.cal = None

    def createDataLog(self, filename):
        self.logfile = logfolder + "/" + filename
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

    def readLastLines(self, n):
        if not os.path.exists(self.logfile):
            print(f"File not found: {logfile}")
            return []

        try:
            with open(filepath, 'r') as f:
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

    def _connectEyetracker(self):
        setConnectionState(True)
        self._client = OpenIrisClient()

    def isConnected():
        return self._client is not None

    def setConnectionState(self, enable):
        if enable and self._client is None:
            self._connectEyetracker()
        elif enable is False and self._client:
            self._client = None
        return self.isConnected()

    def isRecordingEnabled(self):
        return self.recording

    def setRecordingState(self, recording, logName):
        current_state = self.isRecordingEnabled()
        if recording and !(current_state):
            self._recording = True
            setConnectionState(True)
            createDataLog(logName)
        elif !(recording) and currentState:
            self.recording = False
            self._latest_data = None
            self._lastEventTime = 0
        return self.isRecordingEnabled()

    def filter(self, data):
        """"""

    def find_pos(self, data):
        x = data.cr.x - data.p4.x
        y = data.p4.x, data.cr.y-data.p4.y
        X = np.array([1,x,y,x**2,y**2,xy])
        Y = X @ cal
        return Y

    def interpolate(self):


    def __poll(self):
        if self.isConnected() and self.isRecordingEnabled():
            self._latest_data = self._client.fetch_next_data(True)
            if self._latest_data is not None and self.filter(self._latest_data):
                return self.find_pos(_latest_data)
            else:
                #interpolate
    
    def _addSample(self, sample_time):
        if self._

    def runSetupProcedure(self, calibration_args={}):
        
    

                


#i want a choice between interpolating or finding position
#I want data to be filtered then choice



        