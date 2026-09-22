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

out = run_slow('ioreg -c IOMobileFramebufferVeryLegacy', wait=20)
text = out.decode('utf-8', 'replace')
idxs = [i for i in range(len(text)) if text.startswith('IOMobileFramebufferVeryLegacy', i)]
print('total occurrences:', len(idxs), 'total length:', len(text))
for i in idxs:
    print(text[max(0,i-150):i+400])
    print('---')
if not idxs:
    print('NOT FOUND. Also checking IOBootFramebuffer for sanity:')
    out2 = run_slow('ioreg -c IOBootFramebuffer', wait=15)
    text2 = out2.decode('utf-8', 'replace')
    idx2 = text2.find('IOBootFramebuffer  <class')
    print('IOBootFramebuffer found:', idx2 >= 0)

s.close()
