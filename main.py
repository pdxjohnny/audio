import gc
import esp
import time
import json
import socket
import network
import machine

RECEIVE_LEN = 2048
AP_CONFIG_DEFAULT = {
        'essid': 'FEADFACE',
        'channel': 11,
        'hidden': False,
        'authmode': network.AUTH_WPA2_PSK,
        'password': 'DEADBEEF'
        }
DEFAULT_PORT = 8080
DISCOVERY_GROUP = '224.1.1.1'
DISCOVERY_PORT = 45362

class Config(object):
    '''
    Stores and loads config file
    '''

    def __init__(self, filename="config.json"):
        self.filename = filename
        self.c = {}
        self.c_modified = {}

    def load(self):
        '''
        Loads json config from self.filename
        '''
        try:
            with open(self.filename, 'r') as f:
                try:
                    self.c = json.load(f)
                except Exception as e:
                    print("Error loading config json:", e)
                    return False
        except OSError as e:
            print("Error opening config file for reading:", e)
            return False
        self.c_modified = {k: False for k in self.c}
        return True

    def modified(self):
        '''
        If any config elements were modified return True
        '''
        for k in self.c:
            if not k in self.c_modified or self.c_modified[k]:
                return True
        return False

    def save(self):
        '''
        Saves json config to self.filename if not modified
        '''
        if not self.modified():
            return True
        try:
            with open(self.filename, 'w') as f:
                try:
                    f.write(json.dumps(self.c))
                except Exception as e:
                    print("Error writing config json:", e)
                    return False
        except OSError as e:
            print("Error opening config file for writing:", e)
            return False
        return True

    def get(self, key):
        if not key in self.c:
            return None
        return self.c[key]

    def set(self, key, value):
        self.c_modified[key] = True
        self.c[key] = value
        self.save()

class WiFi(object):
    '''
    Connects to known wifi networks if present. If none are present
    it becomes the AP.
    '''

    def __init__(self, config):
        self.config = config
        self.sta = network.WLAN(network.STA_IF)
        self.ap = network.WLAN(network.AP_IF)

    def add(self, ssid, password, hidden):
        '''
        Add an AP to our known APs.
        '''
        known_aps = self.config.get('known_aps')
        if known_aps is None:
            known_aps = {}
        known_aps[ssid] = {
                'ssid': ssid,
                'password': password,
                'hidden': hidden
                }
        self.config.set('known_aps', known_aps)

    def remove(self, ssid):
        '''
        Remove an AP from our known APs.
        '''
        known_aps = self.config.get('known_aps')
        if known_aps is None:
            return
        if ssid in known_aps:
            del known_aps[ssid]
        self.config.set('known_aps', known_aps)

    def connected(self):
        '''
        Checks if we are connected to an AP. Returns False if we are
        anything other than connected with an IP or connecting.
        '''
        status = self.sta.status()
        # Wait until we get an IP
        while status != network.STAT_GOT_IP:
            print("Connecting...")
            # If we are anything other than connecting this is bad
            if status != network.STAT_CONNECTING:
                print("Failed to connect")
                return False
            time.sleep_ms(200)
            status = self.sta.status()
        print("Connected", self.sta.ifconfig())
        return True

    def reset(self):
        self.sta.active(False)
        self.ap.active(False)
        if not self.connect():
            self.sta.active(False)
            self.broadcast()

    def broadcast(self):
        # Make active if not active
        if self.ap.active() is False:
            self.ap.active(True)
        ap_config = self.config.get('ap_config')
        # If we don't have a config use the default
        if ap_config is None:
            ap_config = AP_CONFIG_DEFAULT
        print('Broadcasting', ap_config)
        self.ap.config(**ap_config)

    def connect(self):
        '''
        Scan for WiFi networks and connect to known ones. If we
        don't see any we know on the scan try to connect to hidden
        ones that we know of.
        '''
        # Make active if not active
        if self.sta.active() is False:
            self.sta.active(True)
        # Disconnect if we are connected
        if self.sta.isconnected():
            self.sta.disconnect()
        known_aps = self.config.get('known_aps')
        # If we don't know any APs return False
        if known_aps is None:
            return False
        # Look for APs
        aps = self.sta.scan()
        for ap in aps:
            ap = ap[0].decode('utf-8')
            # If the SSID is in our know APs then we connect to it
            print("Checking if we know AP:", ap)
            if ap in known_aps:
                print("Trying to connect to AP:", known_aps[ap])
                self.sta.connect(known_aps[ap]['ssid'],
                        known_aps[ap]['password'])
                if self.connected():
                    return True
        # If we got here we know APs but they didn't show up in the
        # scan. Now try to connect to hidden ones we know of.
        for ap in [a for a in known_aps if 'hidden' in known_aps[a]
                and known_aps[a]['hidden']]:
            print("Trying to connect to hidden AP:", known_aps[ap])
            self.sta.connect(known_aps[ap]['ssid'],
                    known_aps[ap]['password'])
            if self.connected():
                return True
        return False

class App(object):

    METHODS = {
            'methods': {
                'args': [],
                'response': True,
                },
            'reset': {
                'args': [],
                'response': False,
                },
            'wifi_add': {
                'args': ['ssid', 'password', 'hidden'],
                'response': False,
                },
            'wifi_reset': {
                'args': [],
                'response': False,
                },
            'load_file': {
                'args': ['filename', 'length'],
                'response': False,
                }
            }

    def __init__(self):
        self.config = Config()
        if not self.config.load():
            print('Failed to load config')
        if self.config.get('disable_debug'):
            esp.osdebug(None)
        self.wifi = WiFi(self.config)
        self.serve = False

    def socket_reset(self):
        # Start the TCP server
        addr = socket.getaddrinfo('0.0.0.0', DEFAULT_PORT)[0][-1]
        self.s = socket.socket()
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.bind(addr)
        self.s.listen(1)

    def needs(self, d, *args):
        for a in args:
            if not a in d:
                raise Exception('Missing \'%s\' field' % (a))

    def handle_methods(self, req, c):
        c.send(json.dumps(self.METHODS))

    def handle_reset(self, req, c):
        self.serve = False

    def handle_wifi_add(self, req, c):
        self.wifi.add(req['ssid'], req['password'], req['hidden'])

    def handle_wifi_reset(self, req, c):
        self.wifi.reset()
        print('resetting socket', self.s)
        self.socket_reset()
        print('socket reset', self.s)

    def handle_load_file(self, req, c):
        self.needs(req, 'filename', 'length')
        received_length = 0
        with open(req['filename'], 'wb') as fd:
            c.send(json.dumps({"ready": True}))
            while received_length < req['length']:
                still_need = req['length'] - received_length
                if (still_need % RECEIVE_LEN) == 0:
                    still_need = RECEIVE_LEN
                else:
                    still_need %= RECEIVE_LEN
                print('Receiving...', still_need)
                data = c.recv(still_need)
                print('Got', len(data))
                fd.write(data)
                received_length += len(data)

    def main(self):
        self.wifi.reset()
        self.socket_reset()
        # Serve until we are told to reset
        self.serve = True
        while self.serve is not False:
            c, addr = self.s.accept()
            print('Connection from', addr)
            while True:
                try:
                    req = c.recv(RECEIVE_LEN)
                    print('Request', req)
                    if len(req) == 0:
                        break
                    req = json.loads(req)
                    self.needs(req, 'action')
                    if not req['action'] in self.METHODS:
                        c.send(json.dumps({"error": "no such method"}))
                    else:
                        m = self.METHODS[req['action']]
                        self.needs(req, *m['args'])
                        f = getattr(self,
                                'handle_' + req['action'])
                        f(req, c)
                        if not m['response']:
                            c.send(json.dumps({"error": False}))
                except Exception as e:
                    print('Error while serving request:', e)
                    try:
                        c.send(json.dumps({"error": str(e)}))
                    except Exception as e:
                        print("Couldn't send error to client", e)
                        break
            c.close()
            print('Done serving', addr)
        # Close the server
        self.s.close()
        # We were told to stop serving so reset the device
        machine.reset()

def main():
    app = App()
    app.main()

if __name__ == '__main__':
    gc.collect()
    main()
