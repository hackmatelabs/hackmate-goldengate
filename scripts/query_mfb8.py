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

out = run_slow('ioreg -c IOBootFramebuffer -l', wait=30)
print('RAW BYTES LENGTH:', len(out))
text = out.decode('utf-8', 'replace')
idx = text.find('IOBootFramebuffer')
print('found at idx:', idx)
if idx >= 0:
    print(text[max(0,idx-200):idx+2000])
else:
    print(text[-2000:])

s.close()
