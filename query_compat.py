import socket, time

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/tmp/gg_fastverify_serial.sock')
s.settimeout(2)

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

def run_slow(cmd, wait=8.0):
    for ch in cmd:
        s.sendall(ch.encode())
        time.sleep(0.02)
    s.sendall(b'\r')
    time.sleep(wait)
    return drain(wait)

out = run_slow('ioreg -w 0 -n IOFB', wait=15)
text = out.decode('utf-8', 'replace')
idx = text.find('IOCompatibilityProperties')
print('=== raw window (idx=%d) ===' % idx)
print(repr(text[max(0,idx-20):idx+600]) if idx >= 0 else text[-2000:])

s.close()
