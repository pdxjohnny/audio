import os
import sys
import json
import types
import socket

RECEIVE_LEN = 2048

class Client(object):

    DISCOVERY_GROUP = '224.1.1.1'
    DISCOVERY_PORT = 45362

    def __init__(self, server=()):
        self.server = server
        self.s = socket.socket()
        self.server_methods = {}

    def discover(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                socket.IPPROTO_UDP)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL,
                2)
        s.sendto(b"ping", (self.DISCOVERY_GROUP, self.DISCOVERY_PORT))
        try:
            s.settimeout(0.1)
            data, addr = s.recvfrom(5)
            self.server = (addr[0], int(data))
            return True
        except Exception as e:
            pass
        return False

    def connect(self):
        if len(self.server) != 2 and not self.discover():
            raise Exception("No server address specified and failed to discover")
        self.s.connect(self.server)
        self.methods()

    def disconnect(self):
        self.s.close()

    def send(self, msg):
        return self.s.send(json.dumps(msg).encode('utf-8'))

    def call(self, action, response=True, **kwargs):
        kwargs['action'] = action
        self.send(kwargs)
        if response:
            return self.response()

    def response(self):
        data = json.loads(self.s.recv(RECEIVE_LEN).decode('utf-8'))
        if 'error' in data and data['error'] != False:
            raise Exception(data['error'])
        return data

    def methods(self):
        '''
        methods()
        '''
        self.server_methods = methods = self.call('methods')
        for k, v in self.server_methods.items():
            # Don't make a function if we already have one
            try:
                getattr(self, k)
            except:
                def func_maker(key, value):
                    def func(self, *args, **kwargs):
                        self.call(func.__name__, *args, **kwargs)
                    func.__doc__ = self.fmt_method(key, value)
                    func.__name__ = k
                    return func
                setattr(self, k, types.MethodType(func_maker(k, v), self))

    def fmt_method(self, method_name, method):
        return "%s(%s)" % (method_name,
                ", ".join(method['args']))

    def list_methods(self):
        for i in self.server_methods:
            print(getattr(self, i).__doc__.strip())

    def wifi_reset(self):
        '''
        wifi_reset()
        '''
        self.call('wifi_reset', response=False)

    def load_file(self, filename):
        '''
        load_file(filename)
        '''
        if not os.path.isfile(filename):
            raise Exception('%s is not a file' % (filename,))
        self.call('load_file',
                filename=os.path.basename(filename),
                length=os.stat(filename).st_size)
        with open(filename, 'rb') as fd:
            self.s.sendfile(fd)
        return self.response()

def main():
    c = Client(('192.168.254.43', 8080))
    # c = Client(('192.168.4.1', 8080))
    c.connect()

    if len(sys.argv) < 2:
        return
    if sys.argv[1] == '-h' or sys.argv[1] == '--help':
        c.list_methods()
    else:
        f = None
        try:
            f = getattr(c, sys.argv[1])
        except Exception:
            print('No such method')
            return
        if len(sys.argv) == 2:
            f()
        else:
            data = {}
            for i in sys.argv[2:]:
                if '=' in i:
                    i = i.split('=')
                    data[i[0]] = '='.join(i[1:])
                    if data[i[0]].lower() in ("no", "false"):
                        data[i[0]] = False
                else:
                    data[i] = True
            f(**data)

if __name__ == '__main__':
    main()
