import subprocess, sys
r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "capstone"],
                   capture_output=True, text=True)
print("rc", r.returncode)
print(r.stdout[-500:] if r.stdout else "")
print(r.stderr[-500:] if r.stderr else "")
import capstone
print("capstone", capstone.__version__)
