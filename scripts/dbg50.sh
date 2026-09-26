#!/bin/zsh
BS="/Volumes/macOS Base System"
echo "=== AFK refs in graphics/UI frameworks ==="
for f in "$BS/System/Library/PrivateFrameworks/IOMobileGraphicsFamily-DCP.framework/IOMobileGraphicsFamily-DCP" "$BS/System/Library/Frameworks/SwiftUI.framework/SwiftUI" "$BS/System/Library/PrivateFrameworks/MobileGraphics.framework/MobileGraphics"; do
  if [ -f "$f" ]; then echo "--- $(basename $f)"; strings -a "$f" | grep -i -e AFKFirmwareService -e AFKResource | head -n 4; fi
done
echo "=== Installer Progress + loginwindow AFK refs ==="
for f in "$BS/System/Library/CoreServices/Installer Progress.app/Contents/MacOS/Installer Progress" "$BS/System/Library/CoreServices/loginwindow.app/Contents/MacOS/loginwindow"; do
  if [ -f "$f" ]; then echo "--- $(basename $f)"; strings -a "$f" | grep -i -e AFKFirmwareService | head -n 4; fi
done
echo "=== done ==="
