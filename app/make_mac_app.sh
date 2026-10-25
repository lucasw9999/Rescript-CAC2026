#!/bin/bash
# Build "Rescript Studio.app", a double-clickable Mac app that starts Rescript Studio and opens it in the browser.
#
#   app/make_mac_app.sh                 # installs to ~/Applications
#   app/make_mac_app.sh /some/folder    # or anywhere else
#
# The app is a thin launcher: it runs app/server.py from this repository with the Python that has the
# requirements installed, so pulling new code updates the app too. Quit it from the Dock to stop the server.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/Applications}"
PY="$(python3 -c 'import sys; print(sys.executable)')"
APPDIR="$DEST/Rescript Studio.app"

python3 -c 'import mlx_whisper, mlx_audio' 2>/dev/null || { echo "Install the requirements first: pip install -r $ROOT/requirements.txt"; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/Contents/MacOS" "$APPDIR/Contents/Resources"

cat > "$APPDIR/Contents/MacOS/Rescript Studio" <<EOF
#!/bin/bash
# Apps opened from the Dock get a minimal PATH; Rescript needs Homebrew's ffmpeg and the Codex CLI.
export PATH="/opt/homebrew/bin:/usr/local/bin:\$HOME/.local/bin:\$PATH"
exec "$PY" "$ROOT/app/server.py"
EOF
chmod +x "$APPDIR/Contents/MacOS/Rescript Studio"

cat > "$APPDIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Rescript Studio</string>
  <key>CFBundleDisplayName</key><string>Rescript Studio</string>
  <key>CFBundleIdentifier</key><string>app.rescript.studio</string>
  <key>CFBundleExecutable</key><string>Rescript Studio</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
EOF

# App icon: every size macOS asks for, made from the 1024 px master.
SET="$(mktemp -d)/AppIcon.iconset"; mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$ROOT/app/icon.png" --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$ROOT/app/icon.png" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o "$APPDIR/Contents/Resources/AppIcon.icns"

echo "Built $APPDIR"
echo "Open it from Finder, or: open \"$APPDIR\""
