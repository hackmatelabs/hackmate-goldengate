import socket, time

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/tmp/gg_bootfbprobe_serial.sock')
s.settimeout(2)

def drain(total_wait=2.0):
    buf = b''
    deadline = time.time() + total_wait
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

print('=== ioreg -c IOBootFramebuffer (full wait) ===')
out = run_slow('ioreg -c IOBootFramebuffer', wait=10)
print(out.decode('utf-8', 'replace'))

s.close()
