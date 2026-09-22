from pathlib import Path
import os, subprocess, time

root = Path.home() / 'goldengate/qemu-sptm-cl4-native'
out = Path.home() / 'goldengate/evidence' / ('gdb-violate-' + time.strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True)

args = [str(root/'build/qemu-system-aarch64'), '-s', '-S', '-M', 'darwin',
        '-bootkc', str(root/'firmware/bootkc.md0size.uidfix.netboot10'),
        '-dtree', str(root/'firmware/dtree.dcp8.bigdram2.dcpbyte.nubx.bsroot.nopda.bootuuid'),
        '-tc', str(Path.home()/'goldengate/installer_work_26A428/tc_extracted/022-20292-673.raw.tc'),
        '-ramdisk', str(Path.home()/'goldengate/installer_work_26A428/decrypted/imageboot-wrapper-022.dmg'),
        '-sptm', str(root/'firmware/sptm.asidfix5'),
        '-txm', str(root/'firmware/txm.slotfix4'),
        '-args', 'rd=md0 serial=3 -v -noprogress wdt=-1 wlan-olyhal-abort -rootdmg-ramdisk auth-root-dmg=file:///BaseSystem.dmg allow-root-hash-mismatch=1 acm_fastsim=1 trm_base_system=0 rtb_syslog_verbosity=7',
        '-serial', 'file:' + str(out/'serial.log'),
        '-display', 'none',
        '-monitor', 'unix:/tmp/gg_violate.sock,server,nowait', '-m', '8G']
env = {k: v for k, v in os.environ.items() if not k.startswith('DARWIN_')}
env.update(DARWIN_FB='1', DARWIN_RTKIT='1', DARWIN_DART='1', DARWIN_AIC='1')
(out/'launch.txt').write_text(' '.join(args))
with open(out/'stdout.log', 'wb') as log:
    proc = subprocess.Popen(args, cwd=root, env=env, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
(out/'pid').write_text(str(proc.pid))
Path('/tmp/gg_violate_evidence').write_text(str(out))
print('PID', proc.pid, 'EVIDENCE', out)
