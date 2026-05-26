#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -d "$SCRIPT_DIR/../Sources" || -d "$SCRIPT_DIR/../scripts" ]]; then
  ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  ROOT_DIR="$SCRIPT_DIR"
fi
APP_NAME="Codex Node Keeper"
SOURCE_APP="$ROOT_DIR/build/$APP_NAME.app"
DIST_APP="$ROOT_DIR/$APP_NAME.app"
TARGET_DIR="$HOME/Applications"
TARGET_APP="$TARGET_DIR/$APP_NAME.app"
SUPPORT_DIR="$HOME/.codex-node-keeper"
CONFIG_FILE="$SUPPORT_DIR/config.json"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$LAUNCH_AGENT_DIR/com.ai-studio.codex-node-keeper.plist"

if [[ ! -d "$SOURCE_APP" && -d "$DIST_APP" ]]; then
  SOURCE_APP="$DIST_APP"
fi

if [[ ! -d "$SOURCE_APP" ]]; then
  echo "App bundle not found. Running local build first..."
  "$ROOT_DIR/scripts/build.sh"
  SOURCE_APP="$ROOT_DIR/build/$APP_NAME.app"
fi

mkdir -p "$TARGET_DIR" "$SUPPORT_DIR" "$LAUNCH_AGENT_DIR"
rm -rf "$TARGET_APP"
cp -R "$SOURCE_APP" "$TARGET_APP"

if [[ ! -f "$CONFIG_FILE" ]]; then
  cat > "$CONFIG_FILE" <<'JSON'
{
  "candidateNodes" : [],
  "checkIntervalSeconds" : 60,
  "enabled" : false,
  "failThreshold" : 3,
  "groupName" : "OpenAI",
  "mixedProxyURL" : "http://127.0.0.1:7897",
  "switchCooldownSeconds" : 600,
  "testUrls" : [
    "https://api.openai.com/v1/models",
    "https://chat.openai.com/cdn-cgi/trace"
  ],
  "unixSocketPath" : "/tmp/verge/verge-mihomo.sock"
}
JSON
fi

cat > "$PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ai-studio.codex-node-keeper</string>
  <key>ProgramArguments</key>
  <array>
    <string>$TARGET_APP/Contents/MacOS/CodexNodeKeeper</string>
    <string>--background</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>$SUPPORT_DIR/logs/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$SUPPORT_DIR/logs/launchd.err.log</string>
</dict>
</plist>
PLIST

mkdir -p "$SUPPORT_DIR/logs"
launchctl bootout "gui/$(id -u)" "$PLIST_FILE" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_FILE"
launchctl kickstart -k "gui/$(id -u)/com.ai-studio.codex-node-keeper"

echo "Installed: $TARGET_APP"
echo "LaunchAgent: $PLIST_FILE"
echo "Config: $CONFIG_FILE"
