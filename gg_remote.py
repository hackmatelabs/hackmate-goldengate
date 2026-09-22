"""Run a UTF-8 Python diagnostic on the T480s without shell quoting loss."""
import base64
import pathlib
import subprocess
import sys

source = pathlib.Path(sys.argv[1]).read_bytes() if len(sys.argv) > 1 else sys.stdin.buffer.read()
payload = base64.b64encode(source).decode('ascii')
command = 'echo ' + payload + ' | base64 -D | python3'
result = subprocess.run([
    'ssh', '-i', r'C:\Users\Raahim Syed\.ssh\hackmate_t480s',
    '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=12',
    'raahimsyed@192.168.1.24', command,
])
sys.exit(result.returncode)
