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

def run_slow(cmd, wait=3.0):
    for ch in cmd:
        s.sendall(ch.encode())
        time.sleep(0.02)
    s.sendall(b'\r')
    time.sleep(wait)
    return drain(wait)

print('--- slow-typed echo test ---')
out = run_slow('echo HELLO_TEST_12345')
print(repr(out.decode('utf-8', 'replace')))

print('--- slow-typed ioreg -c IOBootFramebuffer ---')
out2 = run_slow('ioreg -c IOBootFramebuffer', wait=4)
print(repr(out2.decode('utf-8', 'replace')))

s.close()
