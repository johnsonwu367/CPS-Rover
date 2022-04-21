from digi.xbee.devices import *
from threading import Thread, Lock
from time import sleep
import json
from queue import Queue

xbee = XBeeDevice("/dev/ttyUSB0", 9600)
xbee.open()

address = str(xbee.get_64bit_addr())
print("Local 64 bit address: " + address)
print("Waiting for connection...")

addrsBook = []
list_of_conn = []
queueSize = 10
q = Queue(queueSize)

#global telemetry info variable/dictionary
telemetryInfo = {}

timeout = 100000000 #set timeout to infinite or None
xbee.set_sync_ops_timeout(timeout) #allows for xbee sent_data method to run forever, Prevents "Packet listener is not running" error

def broadcasting(localXbee, localAddress):
    while True:
        #broadcasting local 64 bit address
        localAddr = "addr:" + localAddress
        localXbee.send_data_broadcast(localAddr)
        sleep(1)


def connection_listener(localXbee, lock):
    while True:
        msg = localXbee.read_data()
        # read messages that begins with "0013A2004" (it means that its an address to connect to) and take only address that is not already connected to
        if msg is not None:
            data = msg.data.decode()
            key = "addr:"
            addr = data[len(key):len(data)] # actual message with key removed
            if data[0:len(key)] == key and addr not in addrsBook:
                addrsBook.append(addr)
                print("Connected to: " + addr)
                conn = Thread(target = threaded_connection, args = (localXbee, addr, lock, ))
#                list_of_conn.append(conn)
                conn.start()
        sleep(0.5)

# threaded location broadcasting method
def broadcast_location(localXbee, localAddress):
    while True:
        telemetryInfo[localAddress] = "beast" # add or update new local position to telemtryInfo
        temp = list(telemetryInfo.items()) # avoid "dictionary chnaged size during iteration" error
        for key, value in temp: 
            info = 'info:{"%s":"%s"}' % (key, value)
            localXbee.send_data_broadcast(info)
#        print(telemetryInfo)
        sleep(1)

def threaded_connection(localXbee, deviceAddr, lock):
    remote = RemoteXBeeDevice(localXbee, XBee64BitAddress.from_hex_string(deviceAddr))
    timeout = 5 # in seconds
    while True:
        lock.acquire()
        try:
            d = localXbee.read_data_from(remote, timeout)
            # read message received that is not broadcasted address. Broadcasted address always begins with "0013A2004"
            if d is not None:
                if q.full():
                    q.get()
                    q.put(d.remote_device)
                    if remote not in q.queue:
                        break
                else:
                    q.put(d.remote_device)
                    
                data = d.data.decode()
                key = "info:"
                if data[0:len(key)] == key:
                    m = data[len(key):len(data)]
                    m_as_dict = json.loads(m)
                    #combining the telemetry info received with locally known telemetry info
                    telemetryInfo.update(m_as_dict)
        except Exception as e:
            print(e)
            break
        lock.release()
        sleep(0.1)
        
    addrsBook.remove(deviceAddr)
    telemetryInfo.clear()
    print("Threaded connection with " + deviceAddr + " stopped.")
    print("List of connected device: " + str(addrsBook))
    lock.release()
    sleep(0.1)

lock = Lock()
bCastLocalAddr = Thread(target = broadcasting, args = (xbee, address, ))
connListener = Thread(target = connection_listener, args = (xbee, lock, ))
bCastLocation = Thread(target = broadcast_location, args = (xbee, address, ))
bCastLocalAddr.start()
connListener.start()
bCastLocation.start()


xbee.close()