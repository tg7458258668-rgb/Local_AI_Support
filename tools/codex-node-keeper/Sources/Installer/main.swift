import AppKit
import Foundation

final class InstallerPaths {
    static let home = FileManager.default.homeDirectoryForCurrentUser
    static let targetDir = home.appendingPathComponent("Applications", isDirectory: true)
    static let targetApp = targetDir.appendingPathComponent("Codex Node Keeper.app", isDirectory: true)
    static let supportDir = home.appendingPathComponent(".codex-node-keeper", isDirectory: true)
    static let configFile = supportDir.appendingPathComponent("config.json")
    static let logDir = supportDir.appendingPathComponent("logs", isDirectory: true)
    static let logFile = logDir.appendingPathComponent("keeper.log")
    static let launchAgentDir = home.appendingPathComponent("Library/LaunchAgents", isDirectory: true)
    static let plistFile = launchAgentDir.appendingPathComponent("com.ai-studio.codex-node-keeper.plist")
}

@discardableResult
func run(_ executable: String, _ arguments: [String]) throws -> String {
    let process = Process()
    let pipe = Pipe()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.standardOutput = pipe
    process.standardError = pipe
    try process.run()
    process.waitUntilExit()
    let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    if process.terminationStatus != 0 {
        throw NSError(domain: "CodexNodeKeeperInstaller", code: Int(process.terminationStatus), userInfo: [
            NSLocalizedDescriptionKey: output.trimmingCharacters(in: .whitespacesAndNewlines)
        ])
    }
    return output
}

func defaultConfig() -> String {
    """
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
    """
}

final class InstallerViewController: NSViewController {
    private let titleLabel = NSTextField(labelWithString: "Codex Node Keeper")
    private let subtitleLabel = NSTextField(labelWithString: "安装节点守护工具，让 Codex 自动使用更稳的 OpenAI 节点。")
    private let statusLabel = NSTextField(labelWithString: "等待安装")
    private let detailLabel = NSTextField(labelWithString: "安装不会修改 Clash 主程序；只会安装独立控制面板、菜单栏工具、配置文件和开机启动项。")
    private let installButton = NSButton(title: "安装并启动", target: nil, action: nil)
    private let openAppButton = NSButton(title: "打开控制面板", target: nil, action: nil)
    private let openLogButton = NSButton(title: "打开日志", target: nil, action: nil)
    private let quitButton = NSButton(title: "退出", target: nil, action: nil)
    private let progress = NSProgressIndicator()

    override func loadView() {
        view = NSView(frame: NSRect(x: 0, y: 0, width: 560, height: 380))
        view.wantsLayer = true
        view.layer?.backgroundColor = NSColor(calibratedRed: 0.955, green: 0.965, blue: 0.98, alpha: 1).cgColor
        buildUI()
        refreshStatus()
    }

    private func buildUI() {
        let card = NSView()
        card.wantsLayer = true
        card.layer?.backgroundColor = NSColor.white.cgColor
        card.layer?.cornerRadius = 18
        card.layer?.shadowColor = NSColor.black.cgColor
        card.layer?.shadowOpacity = 0.10
        card.layer?.shadowRadius = 24
        card.layer?.shadowOffset = CGSize(width: 0, height: -8)
        card.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(card)

        titleLabel.font = .systemFont(ofSize: 28, weight: .bold)
        titleLabel.textColor = NSColor(calibratedRed: 0.06, green: 0.08, blue: 0.12, alpha: 1)
        subtitleLabel.font = .systemFont(ofSize: 14, weight: .medium)
        subtitleLabel.textColor = .secondaryLabelColor
        subtitleLabel.maximumNumberOfLines = 2
        detailLabel.font = .systemFont(ofSize: 13, weight: .regular)
        detailLabel.textColor = .secondaryLabelColor
        detailLabel.maximumNumberOfLines = 3
        statusLabel.font = .monospacedSystemFont(ofSize: 13, weight: .semibold)
        statusLabel.textColor = NSColor(calibratedRed: 0.09, green: 0.34, blue: 0.72, alpha: 1)

        progress.style = .bar
        progress.isIndeterminate = false
        progress.minValue = 0
        progress.maxValue = 100
        progress.doubleValue = 0

        for button in [installButton, openAppButton, openLogButton, quitButton] {
            button.bezelStyle = .rounded
            button.controlSize = .large
            button.font = .systemFont(ofSize: 14, weight: .semibold)
            button.translatesAutoresizingMaskIntoConstraints = false
        }
        installButton.keyEquivalent = "\r"
        installButton.target = self
        installButton.action = #selector(install)
        openAppButton.target = self
        openAppButton.action = #selector(openInstalledApp)
        openLogButton.target = self
        openLogButton.action = #selector(openLog)
        quitButton.target = self
        quitButton.action = #selector(quit)

        let badge = NSTextField(labelWithString: "Safe Clash Integration")
        badge.font = .monospacedSystemFont(ofSize: 11, weight: .bold)
        badge.textColor = NSColor(calibratedRed: 0.10, green: 0.39, blue: 0.78, alpha: 1)

        let stack = NSStackView(views: [badge, titleLabel, subtitleLabel, statusLabel, progress, detailLabel])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 13
        stack.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(stack)

        let buttonRow = NSStackView(views: [installButton, openAppButton, openLogButton, quitButton])
        buttonRow.orientation = .horizontal
        buttonRow.alignment = .centerY
        buttonRow.distribution = .fillEqually
        buttonRow.spacing = 10
        buttonRow.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(buttonRow)

        for item in [titleLabel, subtitleLabel, statusLabel, detailLabel, progress] {
            item.translatesAutoresizingMaskIntoConstraints = false
        }

        NSLayoutConstraint.activate([
            card.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 28),
            card.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -28),
            card.topAnchor.constraint(equalTo: view.topAnchor, constant: 28),
            card.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -28),

            stack.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 30),
            stack.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -30),
            stack.topAnchor.constraint(equalTo: card.topAnchor, constant: 30),

            progress.widthAnchor.constraint(equalTo: stack.widthAnchor),
            progress.heightAnchor.constraint(equalToConstant: 8),

            buttonRow.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 30),
            buttonRow.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -30),
            buttonRow.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -28),
            buttonRow.heightAnchor.constraint(equalToConstant: 42)
        ])
    }

    private func setBusy(_ busy: Bool, text: String, progress value: Double) {
        DispatchQueue.main.async {
            self.installButton.isEnabled = !busy
            self.openAppButton.isEnabled = !busy && FileManager.default.fileExists(atPath: InstallerPaths.targetApp.path)
            self.openLogButton.isEnabled = !busy
            self.statusLabel.stringValue = text
            self.progress.doubleValue = value
        }
    }

    private func refreshStatus() {
        let installed = FileManager.default.fileExists(atPath: InstallerPaths.targetApp.path)
        openAppButton.isEnabled = installed
        progress.doubleValue = installed ? 100 : 0
        statusLabel.stringValue = installed ? "已安装，可以打开控制面板或从菜单栏 CK 控制" : "未安装，点击安装并启动"
    }

    @objc private func install() {
        setBusy(true, text: "正在安装 App...", progress: 15)
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                try self.performInstall()
                self.setBusy(false, text: "安装完成，控制面板与菜单栏 CK 已启动", progress: 100)
            } catch {
                self.setBusy(false, text: "安装失败：\(error.localizedDescription)", progress: 0)
            }
        }
    }

    private func performInstall() throws {
        let bundle = Bundle.main.bundleURL
        let sourceApp = bundle.deletingLastPathComponent().appendingPathComponent("Codex Node Keeper.app")
        guard FileManager.default.fileExists(atPath: sourceApp.path) else {
            throw NSError(domain: "CodexNodeKeeperInstaller", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "没有找到同目录下的 Codex Node Keeper.app"
            ])
        }

        try FileManager.default.createDirectory(at: InstallerPaths.targetDir, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: InstallerPaths.supportDir, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: InstallerPaths.logDir, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: InstallerPaths.launchAgentDir, withIntermediateDirectories: true)

        if FileManager.default.fileExists(atPath: InstallerPaths.targetApp.path) {
            try FileManager.default.removeItem(at: InstallerPaths.targetApp)
        }
        try FileManager.default.copyItem(at: sourceApp, to: InstallerPaths.targetApp)

        if !FileManager.default.fileExists(atPath: InstallerPaths.configFile.path) {
            try defaultConfig().write(to: InstallerPaths.configFile, atomically: true, encoding: .utf8)
        }

        let plist = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
          <key>Label</key>
          <string>com.ai-studio.codex-node-keeper</string>
          <key>ProgramArguments</key>
          <array>
            <string>\(InstallerPaths.targetApp.path)/Contents/MacOS/CodexNodeKeeper</string>
          </array>
          <key>RunAtLoad</key>
          <true/>
          <key>KeepAlive</key>
          <false/>
          <key>StandardOutPath</key>
          <string>\(InstallerPaths.supportDir.path)/logs/launchd.out.log</string>
          <key>StandardErrorPath</key>
          <string>\(InstallerPaths.supportDir.path)/logs/launchd.err.log</string>
        </dict>
        </plist>
        """
        try plist.write(to: InstallerPaths.plistFile, atomically: true, encoding: .utf8)

        _ = try? run("/bin/launchctl", ["bootout", "gui/\(getuid())", InstallerPaths.plistFile.path])
        _ = try run("/bin/launchctl", ["bootstrap", "gui/\(getuid())", InstallerPaths.plistFile.path])
        _ = try run("/bin/launchctl", ["kickstart", "-k", "gui/\(getuid())/com.ai-studio.codex-node-keeper"])
    }

    @objc private func openInstalledApp() {
        NSWorkspace.shared.open(InstallerPaths.targetApp)
    }

    @objc private func openLog() {
        if !FileManager.default.fileExists(atPath: InstallerPaths.logFile.path) {
            try? FileManager.default.createDirectory(at: InstallerPaths.logDir, withIntermediateDirectories: true)
            try? "Log file is empty.\n".write(to: InstallerPaths.logFile, atomically: true, encoding: .utf8)
        }
        NSWorkspace.shared.open(InstallerPaths.logFile)
    }

    @objc private func quit() {
        NSApplication.shared.terminate(nil)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let controller = InstallerViewController()
        let window = NSWindow(contentViewController: controller)
        window.title = "Codex Node Keeper Installer"
        window.styleMask = [.titled, .closable, .miniaturizable]
        window.center()
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        self.window = window
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
