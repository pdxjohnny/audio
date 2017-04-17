import gc
import esp
import time
import json
import socket
import network
import machine

AP_CONFIG_DEFAULT = {
        'essid': 'FEADFACE',
        'channel': 11,
        'hidden': False,
        'authmode': network.AUTH_WPA2_PSK,
        'password': 'DEADBEEF'
        }

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
                return False
            time.sleep_ms(200)
            status = self.sta.status()
        print("Connected", self.sta.ifconfig())
        return True

    def restart(self):
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
                return self.connected()
        # If we got here we know APs but they didn't show up in the
        # scan. Now try to connect to hidden ones we know of.
        for ap in [a for a in known_aps if 'hidden' in known_aps[a]
                and known_aps[a]['hidden']]:
            print("Trying to connect to hidden AP:", known_aps[ap])
            self.sta.connect(known_aps[ap]['ssid'],
                    known_aps[ap]['password'])
            return self.connected()
        return False

def needs(d, *args):
    for a in args:
        if not a in d:
            raise Exception('Missing \'%s\' field' % (a))

def main():
    print('Main')
    config = Config()
    if not config.load():
        print('Failed to load config')
    if config.get('disable_debug'):
        esp.osdebug(None)
    wifi = WiFi(config)
    wifi.restart()
    # Start the server
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.bind(addr)
    s.listen(1)
    # Serve until we are told to reset
    serve = True
    while serve:
        c, addr = s.accept()
        print('Connection from', addr)
        try:
            req = c.recv(2048)
            print('Request', req)
            req = json.loads(req)
            print('JSON', req)
            needs(req, 'action')
            if req['action'] == 'reset':
                serve = False
            elif req['action'] == 'wifi_add':
                needs(req, 'ssid', 'password', 'hidden')
                wifi.add(req['ssid'], req['password'], req['hidden'])
        except Exception as e:
            print('Error while serving request', e)
            try:
                c.send(json.dumps({"error": e}))
            except Exception as e:
                print("Couldn't send error to client", e)
        c.close()
        print('Done serving', addr)
    # Save config
    config.save()
    # We were told to stop serving so reset the device
    machine.reset()

if __name__ == '__main__':
    gc.collect()
    main()
