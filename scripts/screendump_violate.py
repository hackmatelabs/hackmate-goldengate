import socket, time

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/tmp/gg_realbootfb.sock')
s.settimeout(3)

def drain(wait=2.0):
    buf = b''
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        except socket.timeout:
            break
    return buf

drain(1.0)
s.sendall(b'screendump /tmp/gg_realbootfb.ppm\n')
time.sleep(2)
print(drain(2.0).decode('utf-8', 'replace'))
s.close()
