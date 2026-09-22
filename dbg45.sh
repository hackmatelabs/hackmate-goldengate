#!/bin/zsh
BS="/Volumes/macOS Base System"
echo "=== mounted? ==="
ls -d "$BS" 2>/dev/null || hdiutil attach -nobrowse -readonly /Users/raahimsyed/goldengate/installer_work_26A428/decrypted/BaseSystem.clean.udrw.dmg | tail -n 2
echo "=== InstallerProgress binary ==="
ls -la /Volumes/macOS*Base*/System/Installation/CDIS/* 2>/dev/null | head
find /Volumes/macOS*Base* -maxdepth 6 -name "Installer Progress*" -o -maxdepth 6 -name "InstallerProgress*" 2>/dev/null | head
echo "=== AFK refs in likely binaries ==="
for f in /Volumes/macOS*Base*/System/Library/CoreServices/Installer\ Progress.app/Contents/MacOS/Installer\ Progress; do
  if [ -f "$f" ]; then echo "--- $f"; strings -a "$f" | grep -i -e AFK -e AuxKC | head; fi
done
