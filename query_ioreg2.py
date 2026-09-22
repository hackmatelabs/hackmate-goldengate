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

# Drain any pending banner/prompt noise first
drain(1.0)

def run(cmd, wait=2.5):
    s.sendall(cmd.encode() + b'\r\n')
    time.sleep(wait)
    return drain(wait)

print('--- test echo ---')
print(run('echo HELLO_TEST_12345').decode('utf-8', 'replace'))

print('--- ioreg -c IOBootFramebuffer ---')
print(run('ioreg -c IOBootFramebuffer', wait=4).decode('utf-8', 'replace'))

print('--- ioreg -l | grep -i framebuffer ---')
print(run('ioreg -l | grep -i framebuffer', wait=4).decode('utf-8', 'replace'))

print('--- dmesg tail for GoldenGateBootFramebuffer / IOBootFramebuffer mentions ---')
print(run('dmesg 2>/dev/null | grep -i bootframebuffer', wait=3).decode('utf-8', 'replace'))

s.close()
