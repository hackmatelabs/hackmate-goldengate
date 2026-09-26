from pathlib import Path
import subprocess, time

img = Path.home()/'goldengate/installer_work_26A428/decrypted/imageboot-wrapper-022.dmg'

r = subprocess.run(['hdiutil', 'attach', '-readonly', '-nomount', str(img)],
                    capture_output=True, text=True, timeout=60)
print('attach stdout:', r.stdout)
print('attach stderr:', r.stderr)

# find the APFS volume device (line ending in the APFS signature, second column)
disk = None
for line in r.stdout.splitlines():
    parts = line.split()
    if len(parts) >= 2 and parts[1].startswith('41504653'):
        disk = parts[0]
        break
if not disk:
    print('could not find APFS volume device in attach output')
else:
    print('found volume device:', disk)
    mnt = Path('/tmp/gg_crashmount')
    mnt.mkdir(exist_ok=True)
    r2 = subprocess.run(['mount_apfs', '-o', 'rdonly', disk, str(mnt)],
                         capture_output=True, text=True, timeout=30)
    print('mount stdout:', r2.stdout)
    print('mount stderr:', r2.stderr)
    if r2.returncode == 0:
        for d in ['Library/Logs/DiagnosticReports', 'private/var/db/diagnostics/Crash',
                   'private/var/db/uuidtext', 'Users']:
            p = mnt / d
            if p.exists():
                print(f'--- {d} ---')
                for f in sorted(p.rglob('*'))[:50]:
                    print(' ', f.relative_to(mnt))
            else:
                print(f'--- {d}: does not exist ---')
        # search more broadly for anything WindowServer-related
        print('--- searching for WindowServer*.ips anywhere ---')
        r3 = subprocess.run(['find', str(mnt), '-iname', '*WindowServer*'],
                             capture_output=True, text=True, timeout=60)
        print(r3.stdout)
        subprocess.run(['umount', str(mnt)], capture_output=True, timeout=15)
    subprocess.run(['hdiutil', 'detach', disk.rsplit('s', 1)[0] if 's' in disk.split('/')[-1] else disk],
                    capture_output=True, timeout=15)
