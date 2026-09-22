#!/bin/zsh
rm -f /tmp/gg_diag.sock /tmp/gg_diag_serial.log
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native
DARWIN_FB=1 DARWIN_RTKIT=1 nohup build/qemu-system-aarch64 \
  -M darwin \
  -bootkc firmware/bootkc.md0size.uidfix.netboot1 \
  -dtree firmware/dtree.dcp8.bigdram2.dcpbyte.nubx.bsroot.nopda.bootuuid \
  -tc /Users/raahimsyed/goldengate/installer_work_26A428/tc_extracted/022-20292-673.raw.tc \
  -ramdisk /Users/raahimsyed/goldengate/installer_work_26A428/decrypted/imageboot-wrapper-022.dmg \
  -sptm firmware/sptm.asidfix4 \
  -txm firmware/txm.slotfix4 \
  -args 'rd=md0 serial=3 -v -noprogress wdt=-1 wlan-olyhal-abort -rootdmg-ramdisk auth-root-dmg=file:///BaseSystem.dmg allow-root-hash-mismatch=1 acm_fastsim=1 trm_base_system=0' \
  -serial file:/tmp/gg_diag_serial.log \
  -display cocoa \
  -monitor unix:/tmp/gg_diag.sock,server,nowait \
  -m 8G </dev/null >/tmp/gg_diag_stdout.log 2>&1 &
echo "PID $!"
