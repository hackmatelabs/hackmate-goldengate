import socket, time

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/tmp/gg_bootfbprobe_serial.sock')
s.settimeout(3)

def drain():
    buf = b''
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    except socket.timeout:
        pass
    return buf

# wake the prompt, drain banner noise
s.sendall(b'\n')
time.sleep(1)
drain()

cmd = b"ioreg -c IOBootFramebuffer -l 2>&1; echo IOREG_DONE_MARKER\n"
s.sendall(cmd)
time.sleep(3)
out = drain()
print('--- ioreg -c IOBootFramebuffer output ---')
print(out.decode('utf-8', 'replace'))

cmd2 = b"ioreg -l | grep -i framebuffer 2>&1; echo GREP_DONE_MARKER\n"
s.sendall(cmd2)
time.sleep(3)
out2 = drain()
print('--- ioreg -l | grep framebuffer output ---')
print(out2.decode('utf-8', 'replace'))

s.close()
