from pathlib import Path
import subprocess

root = Path.home()/'goldengate/qemu-sptm-cl4-native'
ninja = '/usr/local/homebrew/Cellar/ninja/1.13.2/bin/ninja'
result = subprocess.run([ninja, 'qemu-system-aarch64'], cwd=root/'build',
                         capture_output=True, text=True, timeout=300)
print('returncode', result.returncode)
print(result.stdout[-3000:])
print(result.stderr[-3000:])
