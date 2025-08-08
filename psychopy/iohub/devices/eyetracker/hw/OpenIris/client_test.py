import socket
import time
import json
from dataclasses import dataclass
import numpy as np

class Point:
    def __init__(self, x:float=0, y:float=0):
        self._d = np.array([x,y], dtype=np.float32)

    @property
    def x(self):
        return self._d[0]

    @property
    def y(self):
        return self._d[1]
    
    def __sub__(self, other):
        return Point(self.x - other.x, self.y - other.y)
    
    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)

    def __mul__(self, other):
        if isinstance(other, Point):
            return Point(self.x * other.x, self.y * other.y)
        else:
            return Point(self.x * other, self.y * other)
    
    def copy(self):
        return Point(self.x, self.y)

    def clip(self, minimum, maximum):
        np.clip(self._d, minimum, maximum, out=self._d)
        return self

    def rotate(self, angle:float):
        R = np.array([[np.cos(angle), np.sin(angle)],[-np.sin(angle), np.cos(angle)]])
        self._d = np.matmul(self._d, R)
        return self
    
    def __repr__(self):
        return str(self._d)

@dataclass
class EyeData:
    frame_number:int
    pupil: Point
    pupil_area:float
    cr: Point
    p4: Point
    cr_error: str
    p4_error: str
    def __init__(self, struct:dict = {}):
        if struct:
            self.frame_number=struct['FrameNumber']
            self.pupil = Point(struct['Pupil']['Center']['X'], struct['Pupil']['Center']['Y'])
            self.pupil_area = struct['Pupil']['Size']['Width'] * struct['Pupil']['Size']['Height']
            if struct['CRs']:
                self.cr = Point(struct['CRs'][0]['X'], struct['CRs'][0]['Y'])
                self.cr_error = ''
            else:
                self.cr = Point(0,0)
                self.cr_error = 'No CRs'
            if len(struct['CRs']) >= 4:
                self.p4 = Point(struct['CRs'][3]['X'], struct['CRs'][3]['Y'])
                self.p4_error = ''
            else:
                self.p4 = Point(0,0)
                self.p4_error = 'No P4'
        else:
            self.frame_number = 0
            self.pupil_area = 0.0
            self.pupil = Point(0,0)
            self.cr = Point(0,0)
            self.p4 = Point(0,0)
            self.cr_error = 'No Data'
            self.p4_error = 'No Data'

    def __repr__(self):
        return f"EyeData({self.frame_number}, Pupil={self.pupil}, Pupil Area={self.pupil_area}, CR={self.cr}, P4={self.p4})"

@dataclass
class EyesData:
    left: EyeData
    right: EyeData
    error: str
    def __init__(self, struct:dict = {}):
        if struct:
            self.left = EyeData(struct['Left'])
            self.right = EyeData(struct['Right'])
            self.error = ''
        else:
            self.left = EyeData()
            self.right = EyeData()
            self.error = 'No Data'
    
    def __repr__(self):
        return f"EyesData\n\tLeft: {repr(self.left)}\n\tRight: {repr(self.right)}"
    
    def get_error(self, left_p4:bool=True, right_p4:bool=True) -> str:
        if self.error:
            return self.error
        error = ''
        if self.left.cr_error or (self.left.p4_error and left_p4):
            error += f"Left:"
            if self.left.cr_error:
                error += f" {self.left.cr_error}"
            if self.left.p4_error and left_p4:
                error += f" {self.left.p4_error}"
            if self.right.cr_error or (self.right.p4_error and right_p4):
                error += ', '
        if self.right.cr_error or (self.right.p4_error and right_p4):
            error += f"Right:"
            if self.right.cr_error:
                error += f" {self.right.cr_error}"
            if self.right.p4_error and right_p4:
                error += f" {self.right.p4_error}"

        return error

class OpenIrisClient:
    def __init__(self, server_address='localhost', port=9003, timeout=1):
        self.server_address = (server_address, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout) # 200 Hz

    def fetch_data_raw(self, debug=False):
        try:
            self.sock.sendto("getdata".encode("utf-8"), self.server_address)
            data = self.sock.recvfrom(8192)  # Adjust the buffer size as needed
            return json.loads(data[0].decode("utf-8"))
        except Exception as e:
            if debug:
                print(f"Error receiving data: {e}")
            return '{}'
        
    def fetch_data_json(self, debug=False):
        return json.loads(self.fetch_data_raw(debug))
    
    def fetch_data(self, debug=False):
        return EyesData(self.fetch_data_json(debug))
    
    def fetch_next_data_raw(self, debug=False):
        try:
            self.sock.sendto("WAITFORDATA".encode("utf-8"), self.server_address)
            data = self.sock.recvfrom(8192)  # Adjust the buffer size as needed
            return data[0].decode("utf-8")
        except Exception as e:
            if debug:
                print(f"Error receiving data: {e}")
            return '{}'
        """
        except socket.error as e:
            if debug:
                print(f"Error receiving data: {e}")
            # Reconnect if the connection was forcibly closed
            if e.errno == 10054:  # WinError 10054
                self.sock.close()
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.settimeout(1)
                print("Socket reconnected after WinError 10054")
            return '{}'
        """
            
    def fetch_next_data_json(self, debug=False):
        raw_data = self.fetch_next_data_raw(debug)
        try:
            # Attempt to parse JSON from the received data
            return json.loads(raw_data)
        except json.JSONDecodeError as e:
            if debug:
                print(f"Failed to decode JSON. Raw data: {raw_data}")
        return {}
    
    def fetch_next_data(self, debug=False):
        return [EyesData(self.fetch_next_data_json(debug)), time.time()]

    def __enter__(self):
        self.sock.connect(self.server_address)
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.sock.close()
        if exc_type:
            print(f"Exception: {exc_type} {exc_value}")
            print(f"Traceback: {traceback}")
            return False
        return True
    
if __name__ == "__main__":
    with OpenIrisClient() as client:
        while True:
            data = client.fetch_next_data(True)
            if data is not None:
                print(f"Received data: {data}")
            else:
                break
    