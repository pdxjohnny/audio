'''
network.py
Fakes the functions in micropython network libary for testing on host
'''

AUTH_WPA2_PSK = 3
STA_IF = 0
AP_IF = 1
STAT_GOT_IP = 1
STAT_CONNECTING = 2

class WLAN(object):

    def __init__(self, args):
        self.isactive = False
        self.isconnected_val = False
        return

    def active(self, isactive=None):
        if isactive is not None:
            self.isactive = isactive
        return self.isactive

    def status(self):
        return STAT_GOT_IP

    def ifconfig(self):
        return "Host Mode Testing"

    def isconnected(self):
        return self.isconnected_val

    def disconnect(self):
        self.isconnected_val = False
        return self.isconnected_val

    def scan(self):
        return []

    def connect(self, *args, **kwargs):
        self.isconnected_val = True
        return True

    def config(self, *args, **kwargs):
        return
