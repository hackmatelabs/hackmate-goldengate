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

out = run_slow('ioreg -c IOBootFramebuffer', wait=30)
text = out.decode('utf-8', 'replace')
idxs = [i for i in range(len(text)) if text.startswith('IOBootFramebuffer', i)]
print('total occurrences:', len(idxs), 'total length:', len(text))
for i in idxs:
    print(text[max(0,i-100):i+300])
    print('---')

s.close()
