# Codex Node Keeper

`Codex Node Keeper` is a small macOS control panel and menu bar utility for keeping the Clash Verge / Mihomo `OpenAI` selector on a healthy node while you use Codex.

It is deliberately conservative:

- It does not reload Clash during normal checks.
- It does not stop TUN mode.
- It does not clear active connections.
- It only changes the `OpenAI` selector when the current route repeatedly fails and a candidate node has been preheated.

## Build

```zsh
tools/codex-node-keeper/scripts/build.sh
```

Output:

- `tools/codex-node-keeper/build/Codex Node Keeper.app`
- `tools/codex-node-keeper/build/Codex Node Keeper Installer.app`
- `tools/codex-node-keeper/dist/CodexNodeKeeperInstaller.zip`
- `tools/codex-node-keeper/dist/CodexNodeKeeper.dmg`

## Install

Open `tools/codex-node-keeper/dist/CodexNodeKeeper.dmg`, then double-click `Codex Node Keeper Installer.app`.

`install.command` is kept as a fallback for automation.

Installed files:

- `~/Applications/Codex Node Keeper.app`
- `~/Library/LaunchAgents/com.ai-studio.codex-node-keeper.plist`
- `~/.codex-node-keeper/config.json`
- `~/.codex-node-keeper/logs/keeper.log`

## Configuration

Default config:

```json
{
  "enabled": false,
  "groupName": "OpenAI",
  "candidateNodes": [],
  "checkIntervalSeconds": 60,
  "failThreshold": 3,
  "switchCooldownSeconds": 600,
  "testUrls": [
    "https://api.openai.com/v1/models",
    "https://chat.openai.com/cdn-cgi/trace"
  ],
  "unixSocketPath": "/tmp/verge/verge-mihomo.sock",
  "mixedProxyURL": "http://127.0.0.1:7897"
}
```

When `candidateNodes` is empty, the app reads all nodes from the `OpenAI` selector and prioritizes ChatGPT, OpenAI, US, Singapore, and Japan nodes.

## Menu Actions

- `开启/关闭 Codex 自动择优`: toggles conservative auto mode.
- `打开控制面板`: opens the full node switching UI.
- `立即检测`: tests the current OpenAI route without switching.
- `切到最佳节点`: preheats candidates and switches only the `OpenAI` selector.
- `恢复上一个节点`: switches the selector back to the last node recorded before a change.
- `修复 Clash 集成`: backs up the Clash config and patches missing OpenAI rules only when needed.
- `打开日志`: opens the local keeper log.

## Safety Model

Normal operation uses only:

- `GET /proxies/OpenAI`
- `GET /proxies/{node}/delay`
- `PUT /proxies/OpenAI`

The app does not call `PUT /configs` during normal checks or node switches.

## Smoke Test

```zsh
tools/codex-node-keeper/scripts/smoke-test.sh
```

The smoke test builds the app, reads Mihomo status, reads the `OpenAI` selector, and tests the current OpenAI route through `127.0.0.1:7897`. It does not switch nodes or reload Clash.

## Clash Verge UI Integration

Clash Verge Rev does not expose a safe extension point for adding custom controls to the Home page. Patching `/Applications/Clash Verge.app` directly would break code signing and can be overwritten by updates.

The safe integration point is:

- Clash Verge keeps the `OpenAI` selector and routing rules.
- Codex Node Keeper provides the on/off switch in the macOS menu bar.
- The app uses Mihomo's local API and never reloads Clash during normal node checks.
