#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Codex Node Keeper"
INSTALLER_NAME="Codex Node Keeper Installer"
BUILD_DIR="$ROOT_DIR/build"
DIST_DIR="$ROOT_DIR/dist"
APP_DIR="$BUILD_DIR/$APP_NAME.app"
INSTALLER_APP_DIR="$BUILD_DIR/$INSTALLER_NAME.app"
DMG_STAGING="$BUILD_DIR/dmg"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
INSTALLER_CONTENTS_DIR="$INSTALLER_APP_DIR/Contents"
INSTALLER_MACOS_DIR="$INSTALLER_CONTENTS_DIR/MacOS"

rm -rf "$BUILD_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR" "$INSTALLER_MACOS_DIR" "$DIST_DIR"

swiftc \
  "$ROOT_DIR/Sources/CodexNodeKeeper/main.swift" \
  -o "$MACOS_DIR/CodexNodeKeeper" \
  -framework AppKit \
  -framework Foundation

cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>zh_CN</string>
  <key>CFBundleExecutable</key>
  <string>CodexNodeKeeper</string>
  <key>CFBundleIdentifier</key>
  <string>com.ai-studio.codex-node-keeper</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Codex Node Keeper</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>LSUIElement</key>
  <false/>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

chmod +x "$MACOS_DIR/CodexNodeKeeper"

swiftc \
  "$ROOT_DIR/Sources/Installer/main.swift" \
  -o "$INSTALLER_MACOS_DIR/CodexNodeKeeperInstaller" \
  -framework AppKit \
  -framework Foundation

cat > "$INSTALLER_CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>zh_CN</string>
  <key>CFBundleExecutable</key>
  <string>CodexNodeKeeperInstaller</string>
  <key>CFBundleIdentifier</key>
  <string>com.ai-studio.codex-node-keeper.installer</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Codex Node Keeper Installer</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

chmod +x "$INSTALLER_MACOS_DIR/CodexNodeKeeperInstaller"

rm -f "$DIST_DIR/CodexNodeKeeperInstaller.zip"
cp "$ROOT_DIR/scripts/install.command" "$DIST_DIR/install.command"
chmod +x "$DIST_DIR/install.command"

(
  cd "$BUILD_DIR"
  zip -qr "$DIST_DIR/CodexNodeKeeperInstaller.zip" "$APP_NAME.app"
  zip -qr "$DIST_DIR/CodexNodeKeeperInstaller.zip" "$INSTALLER_NAME.app"
)
(
  cd "$DIST_DIR"
  zip -qur "$DIST_DIR/CodexNodeKeeperInstaller.zip" "install.command"
)

rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"
cp -R "$APP_DIR" "$DMG_STAGING/"
cp -R "$INSTALLER_APP_DIR" "$DMG_STAGING/"
cp "$ROOT_DIR/scripts/install.command" "$DMG_STAGING/install.command"
chmod +x "$DMG_STAGING/install.command"
cat > "$DMG_STAGING/安装说明.txt" <<'TXT'
Codex Node Keeper

推荐安装方式：
1. 双击 Codex Node Keeper Installer.app
2. 安装后菜单栏会出现 CK
3. 打开 Codex Node Keeper.app 可以看到控制面板
4. 在控制面板或 CK 菜单里开启/关闭「Codex 自动择优」

install.command 仅作为备用安装方式。
也可以直接把 Codex Node Keeper.app 拖到 Applications 运行；这种方式不会自动安装开机启动项。
TXT

rm -f "$DIST_DIR/CodexNodeKeeper.dmg"
hdiutil create \
  -volname "Codex Node Keeper" \
  -srcfolder "$DMG_STAGING" \
  -ov \
  -format UDZO \
  "$DIST_DIR/CodexNodeKeeper.dmg" >/dev/null

echo "Built: $APP_DIR"
echo "Installer App: $INSTALLER_APP_DIR"
echo "Installer: $DIST_DIR/CodexNodeKeeperInstaller.zip"
echo "DMG: $DIST_DIR/CodexNodeKeeper.dmg"
