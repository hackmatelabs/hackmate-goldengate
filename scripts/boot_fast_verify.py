from pathlib import Path
import os, subprocess, time

root = Path.home() / 'goldengate/qemu-sptm-cl4-native'
out = Path.home() / 'goldengate/evidence' / ('fastverify-' + time.strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True)

args = [str(root/'build/qemu-system-aarch64'), '-M', 'darwin',
        '-bootkc', str(root/'firmware/bootkc.netboot10.bootfb-probe'),
        '-dtree', str(root/'firmware/dtree.netboot10.bootfb-probe'),
        '-tc', str(root/'firmware/ramdisk.tc'),
        '-ramdisk', str(root/'firmware/ramdisk.dmg'),
        '-sptm', str(root/'firmware/sptm.asidfix5'),
        '-txm', str(root/'firmware/txm.slotfix4.stealslot'),
        '-icount', 'shift=auto',
        '-args', 'rd=md0 serial=3 -v -noprogress wdt=-1 wlan-olyhal-abort',
        '-serial', 'unix:/tmp/gg_fastverify_serial.sock,server,nowait',
        '-display', 'none',
        '-monitor', 'unix:/tmp/gg_fastverify.sock,server,nowait', '-m', '8G']
env = {k: v for k, v in os.environ.items() if not k.startswith('DARWIN_')}
env.update(DARWIN_FB='1', DARWIN_RTKIT='1', DARWIN_DART='1', DARWIN_AIC='1')
(out/'launch.txt').write_text(' '.join(args))
with open(out/'stdout.log', 'wb') as log:
    proc = subprocess.Popen(args, cwd=root, env=env, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
(out/'pid').write_text(str(proc.pid))
Path('/tmp/gg_fastverify_evidence').write_text(str(out))
print('PID', proc.pid, 'EVIDENCE', out)
