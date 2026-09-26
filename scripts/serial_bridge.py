import socket, time, threading, sys, os

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
for attempt in range(30):
    try:
        s.connect('/tmp/gg_visible_serial.sock')
        break
    except (ConnectionRefusedError, FileNotFoundError):
        time.sleep(0.5)
else:
    print('could not connect')
    sys.exit(1)

logf = open('/tmp/gg_visible_bridge.log', 'ab', buffering=0)
CMD_FILE = '/tmp/gg_visible_cmd.txt'

def drain_loop():
    while True:
        try:
            chunk = s.recv(65536)
            if not chunk:
                break
            logf.write(chunk)
        except Exception:
            break

def cmd_loop():
    while True:
        if os.path.exists(CMD_FILE):
            try:
                with open(CMD_FILE, 'r') as f:
                    cmd = f.read()
                os.remove(CMD_FILE)
                for ch in cmd.rstrip('\n'):
                    s.sendall(ch.encode())
                    time.sleep(0.02)
                s.sendall(b'\r')
            except Exception as e:
                logf.write(('BRIDGE ERROR: ' + str(e) + '\n').encode())
        time.sleep(0.3)

t1 = threading.Thread(target=drain_loop, daemon=True)
t2 = threading.Thread(target=cmd_loop, daemon=True)
t1.start()
t2.start()
t1.join()
