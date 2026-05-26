import AppKit
import Foundation

struct KeeperConfig: Codable {
    var enabled: Bool
    var groupName: String
    var candidateNodes: [String]
    var checkIntervalSeconds: TimeInterval
    var failThreshold: Int
    var switchCooldownSeconds: TimeInterval
    var testUrls: [String]
    var unixSocketPath: String
    var mixedProxyURL: String

    static let defaults = KeeperConfig(
        enabled: false,
        groupName: "OpenAI",
        candidateNodes: [],
        checkIntervalSeconds: 60,
        failThreshold: 3,
        switchCooldownSeconds: 600,
        testUrls: [
            "https://api.openai.com/v1/models",
            "https://chat.openai.com/cdn-cgi/trace"
        ],
        unixSocketPath: "/tmp/verge/verge-mihomo.sock",
        mixedProxyURL: "http://127.0.0.1:7897"
    )
}

struct ProxyGroup: Decodable {
    let alive: Bool?
    let all: [String]?
    let name: String?
    let now: String?
    let type: String?
}

struct DelayResponse: Decodable {
    let delay: Int?
}

struct CurlResult {
    let output: String
    let status: Int32
}

final class Paths {
    static let home = FileManager.default.homeDirectoryForCurrentUser
    static let supportDir = home.appendingPathComponent(".codex-node-keeper", isDirectory: true)
    static let backupDir = supportDir.appendingPathComponent("backups", isDirectory: true)
    static let logDir = supportDir.appendingPathComponent("logs", isDirectory: true)
    static let configFile = supportDir.appendingPathComponent("config.json")
    static let logFile = logDir.appendingPathComponent("keeper.log")
    static let clashConfig = home.appendingPathComponent("Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml")
}

final class Logger {
    static func write(_ message: String) {
        try? FileManager.default.createDirectory(at: Paths.logDir, withIntermediateDirectories: true)
        let line = "[\(ISO8601DateFormatter().string(from: Date()))] \(message)\n"
        if FileManager.default.fileExists(atPath: Paths.logFile.path),
           let handle = try? FileHandle(forWritingTo: Paths.logFile) {
            _ = try? handle.seekToEnd()
            if let data = line.data(using: .utf8) {
                try? handle.write(contentsOf: data)
            }
            try? handle.close()
        } else {
            try? line.write(to: Paths.logFile, atomically: true, encoding: .utf8)
        }
    }
}

enum KeeperError: Error, LocalizedError {
    case commandFailed(String)
    case missingGroup(String)
    case noCandidates

    var errorDescription: String? {
        switch self {
        case .commandFailed(let detail): return detail
        case .missingGroup(let name): return "Missing Mihomo selector group: \(name)"
        case .noCandidates: return "No usable candidate nodes were found."
        }
    }
}

@discardableResult
func runProcess(_ launchPath: String, _ args: [String]) throws -> CurlResult {
    let process = Process()
    let pipe = Pipe()
    process.executableURL = URL(fileURLWithPath: launchPath)
    process.arguments = args
    process.standardOutput = pipe
    process.standardError = pipe
    try process.run()
    process.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    let output = String(data: data, encoding: .utf8) ?? ""
    return CurlResult(output: output.trimmingCharacters(in: .whitespacesAndNewlines), status: process.terminationStatus)
}

func pathEncode(_ value: String) -> String {
    var allowed = CharacterSet.alphanumerics
    allowed.insert(charactersIn: "-._~")
    return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
}

func jsonDecode<T: Decodable>(_ type: T.Type, from text: String) throws -> T {
    guard let data = text.data(using: .utf8) else {
        throw KeeperError.commandFailed("Invalid UTF-8 response.")
    }
    return try JSONDecoder().decode(T.self, from: data)
}

final class ConfigStore {
    static func load() -> KeeperConfig {
        try? FileManager.default.createDirectory(at: Paths.supportDir, withIntermediateDirectories: true)
        guard let data = try? Data(contentsOf: Paths.configFile),
              let config = try? JSONDecoder().decode(KeeperConfig.self, from: data) else {
            save(KeeperConfig.defaults)
            return KeeperConfig.defaults
        }
        return config
    }

    static func save(_ config: KeeperConfig) {
        try? FileManager.default.createDirectory(at: Paths.supportDir, withIntermediateDirectories: true)
        if let data = try? JSONEncoder.pretty.encode(config) {
            try? data.write(to: Paths.configFile)
        }
    }
}

extension JSONEncoder {
    static var pretty: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return encoder
    }
}

final class MihomoClient {
    private let config: KeeperConfig

    init(config: KeeperConfig) {
        self.config = config
    }

    func getProxy(_ name: String) throws -> ProxyGroup {
        let result = try mihomo("GET", path: "/proxies/\(pathEncode(name))")
        guard result.status == 0 else {
            throw KeeperError.commandFailed(result.output)
        }
        return try jsonDecode(ProxyGroup.self, from: result.output)
    }

    func getGroup() throws -> ProxyGroup {
        let group = try getProxy(config.groupName)
        guard group.type?.lowercased().contains("selector") == true || group.all != nil else {
            throw KeeperError.missingGroup(config.groupName)
        }
        return group
    }

    func setNode(_ node: String) throws {
        let body = #"{"name":"\#(node.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\""))"}"#
        let result = try mihomo("PUT", path: "/proxies/\(pathEncode(config.groupName))", data: body)
        guard result.status == 0 else {
            throw KeeperError.commandFailed(result.output)
        }
    }

    func delay(node: String, url: String) throws -> Int {
        let endpoint = "/proxies/\(pathEncode(node))/delay?timeout=5000&url=\(pathEncode(url))"
        let result = try mihomo("GET", path: endpoint)
        guard result.status == 0 else {
            throw KeeperError.commandFailed(result.output)
        }
        let response = try jsonDecode(DelayResponse.self, from: result.output)
        guard let delay = response.delay else {
            throw KeeperError.commandFailed(result.output)
        }
        return delay
    }

    func currentHTTPHealth() throws -> TimeInterval {
        let url = config.testUrls.first ?? "https://api.openai.com/v1/models"
        let args = [
            "-I", "-sS", "--max-time", "12",
            "--proxy", config.mixedProxyURL,
            "-o", "/dev/null",
            "-w", "code=%{http_code} total=%{time_total}",
            url
        ]
        let result = try runProcess("/usr/bin/curl", args)
        guard result.status == 0 else {
            throw KeeperError.commandFailed(result.output)
        }
        let parts = Dictionary(uniqueKeysWithValues: result.output.split(separator: " ").compactMap { item -> (String, String)? in
            let pair = item.split(separator: "=", maxSplits: 1).map(String.init)
            return pair.count == 2 ? (pair[0], pair[1]) : nil
        })
        let code = Int(parts["code"] ?? "0") ?? 0
        let total = TimeInterval(parts["total"] ?? "0") ?? 0
        if [200, 204, 301, 302, 401, 403].contains(code), total > 0 {
            return total
        }
        throw KeeperError.commandFailed(result.output)
    }

    private func mihomo(_ method: String, path: String, data: String? = nil) throws -> CurlResult {
        var args = [
            "--unix-socket", config.unixSocketPath,
            "-sS", "--max-time", "10",
            "-X", method,
            "http://localhost\(path)"
        ]
        if let data {
            args.insert(contentsOf: ["-H", "Content-Type: application/json", "-d", data], at: args.count - 1)
        }
        return try runProcess("/usr/bin/curl", args)
    }
}

final class NodeJudge {
    private(set) var failureCount = 0
    private(set) var lastDelay: Int?
    private(set) var lastCheck: Date?
    private(set) var lastSwitch: Date?
    private(set) var previousNode: String?

    func recordSuccess(delay: Int?) {
        failureCount = 0
        lastDelay = delay
        lastCheck = Date()
    }

    func recordFailure() {
        failureCount += 1
        lastCheck = Date()
    }

    func shouldEvaluateCandidates(config: KeeperConfig) -> Bool {
        guard failureCount >= config.failThreshold else { return false }
        if let lastSwitch, Date().timeIntervalSince(lastSwitch) < config.switchCooldownSeconds {
            return false
        }
        return true
    }

    func recordSwitch(from oldNode: String) {
        previousNode = oldNode
        lastSwitch = Date()
        failureCount = 0
    }
}

protocol KeeperControlPanelDelegate: AnyObject {
    func controlPanelToggleAuto()
    func controlPanelRunCheck()
    func controlPanelSwitchBest()
    func controlPanelRestorePrevious()
    func controlPanelRepair()
    func controlPanelOpenLogs()
}

final class KeeperControlPanel: NSWindowController {
    weak var delegate: KeeperControlPanelDelegate?

    private let statusPill = NSTextField(labelWithString: "已暂停")
    private let statusLabel = NSTextField(labelWithString: "等待检测")
    private let policyValue = NSTextField(labelWithString: "Unknown")
    private let outletValue = NSTextField(labelWithString: "Unknown")
    private let routePathLabel = NSTextField(labelWithString: "OpenAI -> --")
    private let delayValue = NSTextField(labelWithString: "--")
    private let failureValue = NSTextField(labelWithString: "0 / 3")
    private let switchValue = NSTextField(labelWithString: "--")
    private let candidatesValue = NSTextField(labelWithString: "--")
    private let autoSwitch = NSSwitch()
    private let autoTitle = NSTextField(labelWithString: "Codex 自动择优")
    private let autoSubtitle = NSTextField(labelWithString: "只在连续异常时切换；候选只包含 GPT 专用节点和国家/旗帜开头的真实出口。")
    private let checkButton = NSButton(title: "立即检测", target: nil, action: nil)
    private let bestButton = NSButton(title: "切到最佳节点", target: nil, action: nil)
    private let restoreButton = NSButton(title: "恢复上一节点", target: nil, action: nil)
    private let repairButton = NSButton(title: "修复 Clash", target: nil, action: nil)
    private let logsButton = NSButton(title: "日志", target: nil, action: nil)

    private let ink = NSColor(calibratedRed: 0.08, green: 0.10, blue: 0.14, alpha: 1)
    private let muted = NSColor(calibratedRed: 0.42, green: 0.45, blue: 0.50, alpha: 1)
    private let surface = NSColor(calibratedRed: 0.96, green: 0.97, blue: 0.98, alpha: 1)
    private let cardSurface = NSColor.white
    private let blue = NSColor(calibratedRed: 0.08, green: 0.37, blue: 0.86, alpha: 1)
    private let green = NSColor(calibratedRed: 0.03, green: 0.55, blue: 0.33, alpha: 1)
    private let red = NSColor(calibratedRed: 0.78, green: 0.12, blue: 0.16, alpha: 1)

    init(delegate: KeeperControlPanelDelegate) {
        self.delegate = delegate
        let view = NSView(frame: NSRect(x: 0, y: 0, width: 720, height: 500))
        view.wantsLayer = true
        view.layer?.backgroundColor = surface.cgColor
        let controller = NSViewController()
        controller.view = view
        let window = NSWindow(contentViewController: controller)
        window.title = "Codex Node Keeper"
        window.styleMask = [.titled, .closable, .miniaturizable]
        window.isReleasedWhenClosed = false
        super.init(window: window)
        buildUI(in: view)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func buildUI(in root: NSView) {
        let shell = makeCard(cornerRadius: 22)
        root.addSubview(shell)

        let badge = makeLabel("OPENAI ROUTE GUARD", size: 11, weight: .bold, color: blue, monospaced: true)
        let title = makeLabel("Codex Node Keeper", size: 24, weight: .bold, color: ink)
        let subtitle = makeLabel("看住 OpenAI 策略组，异常时自动换到更稳的国家节点。", size: 13, weight: .medium, color: muted)

        statusPill.font = .systemFont(ofSize: 12, weight: .bold)
        statusPill.textColor = blue
        statusPill.alignment = .center
        statusPill.wantsLayer = true
        statusPill.layer?.cornerRadius = 12
        statusPill.layer?.backgroundColor = NSColor(calibratedRed: 0.90, green: 0.94, blue: 1.00, alpha: 1).cgColor
        statusPill.translatesAutoresizingMaskIntoConstraints = false
        statusPill.widthAnchor.constraint(greaterThanOrEqualToConstant: 76).isActive = true
        statusPill.heightAnchor.constraint(equalToConstant: 26).isActive = true

        let titleBlock = NSStackView(views: [badge, title, subtitle])
        titleBlock.orientation = .vertical
        titleBlock.alignment = .leading
        titleBlock.spacing = 5
        titleBlock.setContentHuggingPriority(.defaultLow, for: .horizontal)
        statusPill.setContentHuggingPriority(.required, for: .horizontal)

        let header = NSStackView(views: [titleBlock, statusPill])
        header.orientation = .horizontal
        header.alignment = .top
        header.distribution = .fill
        header.spacing = 20

        statusLabel.font = .systemFont(ofSize: 13, weight: .semibold)
        statusLabel.textColor = muted

        autoTitle.font = .systemFont(ofSize: 16, weight: .bold)
        autoTitle.textColor = ink
        autoSubtitle.font = .systemFont(ofSize: 12, weight: .medium)
        autoSubtitle.textColor = muted
        autoSubtitle.maximumNumberOfLines = 2
        autoSwitch.target = self
        autoSwitch.action = #selector(toggleAuto)

        for button in [checkButton, bestButton, restoreButton, repairButton, logsButton] {
            button.bezelStyle = .rounded
            button.controlSize = .large
            button.font = .systemFont(ofSize: 13, weight: .semibold)
        }
        checkButton.target = self
        checkButton.action = #selector(runCheck)
        bestButton.target = self
        bestButton.action = #selector(switchBest)
        restoreButton.target = self
        restoreButton.action = #selector(restorePrevious)
        repairButton.target = self
        repairButton.action = #selector(repair)
        logsButton.target = self
        logsButton.action = #selector(openLogs)

        let autoTextBlock = NSStackView(views: [autoTitle, autoSubtitle])
        autoTextBlock.orientation = .vertical
        autoTextBlock.alignment = .leading
        autoTextBlock.spacing = 3
        let autoRow = NSStackView(views: [autoTextBlock, autoSwitch])
        autoRow.orientation = .horizontal
        autoRow.alignment = .centerY
        autoRow.distribution = .fill
        autoRow.spacing = 20
        autoTextBlock.setContentHuggingPriority(.defaultLow, for: .horizontal)
        autoSwitch.setContentHuggingPriority(.required, for: .horizontal)
        let autoCard = wrap(autoRow, background: NSColor(calibratedRed: 0.94, green: 0.97, blue: 1.00, alpha: 1), border: NSColor(calibratedRed: 0.78, green: 0.86, blue: 0.98, alpha: 1))
        autoCard.heightAnchor.constraint(equalToConstant: 68).isActive = true

        configureRouteLabel(policyValue)
        configureRouteLabel(outletValue)
        routePathLabel.font = .systemFont(ofSize: 12, weight: .medium)
        routePathLabel.textColor = muted
        routePathLabel.lineBreakMode = .byTruncatingMiddle

        let routeGrid = NSStackView(views: [
            routeCard(title: "OpenAI 策略", value: policyValue, note: "Keeper 只修改这个组"),
            routeCard(title: "实际出口", value: outletValue, note: "最终会经过的国家节点")
        ])
        routeGrid.orientation = .horizontal
        routeGrid.spacing = 14
        routeGrid.distribution = .fillEqually

        let pathCard = wrap(routePathLabel, background: NSColor(calibratedWhite: 0.98, alpha: 1), border: NSColor(calibratedWhite: 0.86, alpha: 1))
        pathCard.heightAnchor.constraint(equalToConstant: 48).isActive = true

        let metricGrid = NSStackView(views: [
            metricCard(title: "最近延迟", value: delayValue),
            metricCard(title: "连续失败", value: failureValue),
            metricCard(title: "候选节点", value: candidatesValue),
            metricCard(title: "上次切换", value: switchValue)
        ])
        metricGrid.orientation = .horizontal
        metricGrid.spacing = 12
        metricGrid.distribution = .fillEqually

        let actions = NSStackView(views: [checkButton, bestButton, restoreButton, repairButton, logsButton])
        actions.orientation = .horizontal
        actions.spacing = 10
        actions.distribution = .fillEqually

        let stack = NSStackView(views: [header, statusLabel, autoCard, routeGrid, pathCard, metricGrid, actions])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        shell.addSubview(stack)

        for view in [shell, stack, header, titleBlock, autoCard, routeGrid, pathCard, metricGrid, actions] {
            view.translatesAutoresizingMaskIntoConstraints = false
        }

        NSLayoutConstraint.activate([
            shell.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 26),
            shell.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -26),
            shell.topAnchor.constraint(equalTo: root.topAnchor, constant: 22),
            shell.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -22),

            stack.leadingAnchor.constraint(equalTo: shell.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: shell.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: shell.topAnchor, constant: 22),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: shell.bottomAnchor, constant: -22),

            header.widthAnchor.constraint(equalTo: stack.widthAnchor),
            statusLabel.widthAnchor.constraint(equalTo: stack.widthAnchor),
            autoCard.widthAnchor.constraint(equalTo: stack.widthAnchor),
            routeGrid.widthAnchor.constraint(equalTo: stack.widthAnchor),
            pathCard.widthAnchor.constraint(equalTo: stack.widthAnchor),
            metricGrid.widthAnchor.constraint(equalTo: stack.widthAnchor),
            actions.widthAnchor.constraint(equalTo: stack.widthAnchor)
        ])
    }

    private func makeCard(cornerRadius: CGFloat) -> NSView {
        let view = NSView()
        view.wantsLayer = true
        view.layer?.backgroundColor = cardSurface.cgColor
        view.layer?.cornerRadius = cornerRadius
        view.layer?.shadowColor = NSColor.black.cgColor
        view.layer?.shadowOpacity = 0.10
        view.layer?.shadowRadius = 24
        view.layer?.shadowOffset = CGSize(width: 0, height: -8)
        view.translatesAutoresizingMaskIntoConstraints = false
        return view
    }

    private func makeLabel(_ text: String, size: CGFloat, weight: NSFont.Weight, color: NSColor, monospaced: Bool = false) -> NSTextField {
        let label = NSTextField(labelWithString: text)
        label.font = monospaced ? .monospacedSystemFont(ofSize: size, weight: weight) : .systemFont(ofSize: size, weight: weight)
        label.textColor = color
        return label
    }

    private func wrap(_ child: NSView, background: NSColor, border: NSColor) -> NSView {
        let view = NSView()
        view.wantsLayer = true
        view.layer?.backgroundColor = background.cgColor
        view.layer?.cornerRadius = 14
        view.layer?.borderColor = border.cgColor
        view.layer?.borderWidth = 1
        view.translatesAutoresizingMaskIntoConstraints = false
        child.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(child)
        NSLayoutConstraint.activate([
            child.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            child.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            child.topAnchor.constraint(equalTo: view.topAnchor, constant: 14),
            child.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -14)
        ])
        return view
    }

    private func configureRouteLabel(_ label: NSTextField) {
        label.font = .systemFont(ofSize: 18, weight: .bold)
        label.textColor = ink
        label.lineBreakMode = .byTruncatingMiddle
        label.maximumNumberOfLines = 2
    }

    private func routeCard(title: String, value: NSTextField, note: String) -> NSView {
        let titleLabel = makeLabel(title, size: 12, weight: .bold, color: muted)
        let noteLabel = makeLabel(note, size: 12, weight: .medium, color: muted)
        let stack = NSStackView(views: [titleLabel, value, noteLabel])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 7
        let card = wrap(stack, background: NSColor(calibratedRed: 0.98, green: 0.99, blue: 1.00, alpha: 1), border: NSColor(calibratedWhite: 0.86, alpha: 1))
        card.heightAnchor.constraint(equalToConstant: 104).isActive = true
        return card
    }

    private func metricCard(title: String, value: NSTextField) -> NSView {
        let titleLabel = makeLabel(title, size: 11, weight: .semibold, color: muted)
        value.font = .monospacedSystemFont(ofSize: 17, weight: .bold)
        value.textColor = ink
        value.lineBreakMode = .byTruncatingMiddle
        let stack = NSStackView(views: [titleLabel, value])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 5
        let card = wrap(stack, background: NSColor(calibratedWhite: 0.985, alpha: 1), border: NSColor(calibratedWhite: 0.88, alpha: 1))
        card.heightAnchor.constraint(equalToConstant: 70).isActive = true
        return card
    }

    func update(config: KeeperConfig, status: String, policyNode: String, actualNode: String, routePath: [String], delay: Int?, failures: Int, lastSwitch: Date?, candidateCount: Int, canRestore: Bool, busy: Bool) {
        DispatchQueue.main.async {
            self.autoSwitch.state = config.enabled ? .on : .off
            let isError = status.lowercased().contains("error") || status.lowercased().contains("failure")
            self.statusPill.stringValue = busy ? "检测中" : (config.enabled ? "守护中" : "已暂停")
            self.statusPill.textColor = isError ? self.red : (config.enabled ? self.green : self.blue)
            self.statusPill.layer?.backgroundColor = (isError
                ? NSColor(calibratedRed: 1.00, green: 0.90, blue: 0.90, alpha: 1)
                : (config.enabled
                    ? NSColor(calibratedRed: 0.88, green: 0.97, blue: 0.92, alpha: 1)
                    : NSColor(calibratedRed: 0.90, green: 0.94, blue: 1.00, alpha: 1))).cgColor
            self.statusLabel.stringValue = "状态：\(status)"
            self.policyValue.stringValue = policyNode
            self.outletValue.stringValue = actualNode
            self.routePathLabel.stringValue = "路径：" + (routePath.isEmpty ? "OpenAI -> --" : routePath.joined(separator: " -> "))
            self.delayValue.stringValue = delay.map { "\($0)ms" } ?? "--"
            self.failureValue.stringValue = "\(failures) / \(config.failThreshold)"
            self.candidatesValue.stringValue = candidateCount > 0 ? "\(candidateCount) 个" : "--"
            if let lastSwitch {
                self.switchValue.stringValue = DateFormatter.localizedString(from: lastSwitch, dateStyle: .none, timeStyle: .short)
            } else {
                self.switchValue.stringValue = "--"
            }
            self.restoreButton.isEnabled = canRestore && !busy
            for button in [self.checkButton, self.bestButton, self.repairButton, self.logsButton] {
                button.isEnabled = !busy
            }
            self.autoSwitch.isEnabled = !busy
        }
    }

    func showPanel() {
        window?.center()
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func toggleAuto() { delegate?.controlPanelToggleAuto() }
    @objc private func runCheck() { delegate?.controlPanelRunCheck() }
    @objc private func switchBest() { delegate?.controlPanelSwitchBest() }
    @objc private func restorePrevious() { delegate?.controlPanelRestorePrevious() }
    @objc private func repair() { delegate?.controlPanelRepair() }
    @objc private func openLogs() { delegate?.controlPanelOpenLogs() }
}

final class ConfigRepair {
    static func backupClashConfig(reason: String) throws -> URL? {
        guard FileManager.default.fileExists(atPath: Paths.clashConfig.path) else { return nil }
        try FileManager.default.createDirectory(at: Paths.backupDir, withIntermediateDirectories: true)
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let target = Paths.backupDir.appendingPathComponent("clash-verge-\(reason)-\(stamp).yaml")
        try FileManager.default.copyItem(at: Paths.clashConfig, to: target)
        Logger.write("Backed up Clash config to \(target.path)")
        return target
    }

    static func needsRepair() -> Bool {
        guard let text = try? String(contentsOf: Paths.clashConfig, encoding: .utf8) else { return true }
        return !text.contains("- name: OpenAI")
            || !text.contains("DOMAIN,api.openai.com,OpenAI")
            || !text.contains("fake-ip-filter:")
            || !text.contains("chatgpt.com")
    }

    static func repair() throws {
        guard FileManager.default.fileExists(atPath: Paths.clashConfig.path) else {
            throw KeeperError.commandFailed("Clash config not found at \(Paths.clashConfig.path)")
        }
        guard needsRepair() else {
            Logger.write("Repair skipped; Clash integration already looks complete.")
            return
        }
        _ = try backupClashConfig(reason: "repair")
        var text = try String(contentsOf: Paths.clashConfig, encoding: .utf8)
        if !text.contains("mode: rule") {
            text = text.replacingOccurrences(of: "mode: global", with: "mode: rule")
        }
        if !text.contains("fake-ip-filter:") {
            text = text.replacingOccurrences(
                of: "  fake-ip-range: 198.18.0.1/16\n",
                with: """
                  fake-ip-range: 198.18.0.1/16
                  fake-ip-filter:
                  - 'openai.com'
                  - '*.openai.com'
                  - 'chat.openai.com'
                  - 'chatgpt.com'
                  - '*.chatgpt.com'
                  - 'oaistatic.com'
                  - '*.oaistatic.com'
                  - 'oaiusercontent.com'
                  - '*.oaiusercontent.com'

                """
            )
        } else {
            let requiredFilters = [
                "  - 'openai.com'",
                "  - '*.openai.com'",
                "  - 'chat.openai.com'",
                "  - 'chatgpt.com'",
                "  - '*.chatgpt.com'",
                "  - 'oaistatic.com'",
                "  - '*.oaistatic.com'",
                "  - 'oaiusercontent.com'",
                "  - '*.oaiusercontent.com'"
            ]
            if let range = text.range(of: "  fake-ip-filter:\n") {
                let additions = requiredFilters.filter { !text.contains($0) }.joined(separator: "\n")
                if !additions.isEmpty {
                    text.insert(contentsOf: additions + "\n", at: range.upperBound)
                }
            }
        }
        if !text.contains("- name: OpenAI"), let range = text.range(of: "proxy-groups:\n") {
            text.insert(contentsOf: """
            - name: OpenAI
              type: select
              proxies:
              - ChatGPT · 01 · 限 30 Mbs
              - ChatGPT · 02 · 限 30 Mbs
              - ChatGPT · 03 · 限 30 Mbs
              - ChatGPT · 04 · 限 30 Mbs
              - 🇺🇸 美国 · 05 · Chatgpt/TikTok
              - 🇺🇸 美国 · 06 · Chatgpt/TikTok
              - 自动选择
              - 故障转移
              - 大哥云
            """, at: range.upperBound)
        }
        if !text.contains("DOMAIN,api.openai.com,OpenAI"), let range = text.range(of: "rules:\n") {
            text.insert(contentsOf: """
            - DOMAIN,api.openai.com,OpenAI
            - DOMAIN,chat.openai.com,OpenAI
            - DOMAIN,auth.openai.com,OpenAI
            - DOMAIN-SUFFIX,openai.com,OpenAI
            - DOMAIN-SUFFIX,chatgpt.com,OpenAI
            - DOMAIN-SUFFIX,oaistatic.com,OpenAI
            - DOMAIN-SUFFIX,oaiusercontent.com,OpenAI
            """, at: range.upperBound)
        }
        try text.write(to: Paths.clashConfig, atomically: true, encoding: .utf8)
        try reloadMihomoConfig()
        Logger.write("Repaired Clash integration and reloaded Mihomo config.")
    }

    static func reloadMihomoConfig() throws {
        let path = Paths.clashConfig.path
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        let body = #"{"path":"\#(path)","force":true}"#
        let result = try runProcess("/usr/bin/curl", [
            "--unix-socket", "/tmp/verge/verge-mihomo.sock",
            "-sS", "--max-time", "10",
            "-X", "PUT",
            "-H", "Content-Type: application/json",
            "-d", body,
            "http://localhost/configs"
        ])
        guard result.status == 0 else {
            throw KeeperError.commandFailed(result.output)
        }
    }
}

final class KeeperApp: NSObject, NSApplicationDelegate, KeeperControlPanelDelegate {
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private let launchedInBackground = ProcessInfo.processInfo.arguments.contains("--background")
    private var config = ConfigStore.load()
    private lazy var client = MihomoClient(config: config)
    private let judge = NodeJudge()
    private lazy var controlPanel = KeeperControlPanel(delegate: self)
    private var timer: Timer?
    private var currentNode = "Unknown"
    private var policyNode = "Unknown"
    private var actualNode = "Unknown"
    private var routePath: [String] = ["OpenAI", "--"]
    private var candidateCount = 0
    private var statusLine = "Starting..."
    private var isBusy = false

    private let menu = NSMenu()
    private let statusItemView = NSMenuItem(title: "Status: Starting", action: nil, keyEquivalent: "")
    private let nodeItem = NSMenuItem(title: "OpenAI: Unknown", action: nil, keyEquivalent: "")
    private let outletItem = NSMenuItem(title: "Outlet: Unknown", action: nil, keyEquivalent: "")
    private let delayItem = NSMenuItem(title: "Last check: --", action: nil, keyEquivalent: "")
    private let toggleItem = NSMenuItem(title: "开启 Codex 自动择优", action: #selector(toggleAuto), keyEquivalent: "")
    private let checkItem = NSMenuItem(title: "立即检测", action: #selector(runManualCheck), keyEquivalent: "r")
    private let bestItem = NSMenuItem(title: "切到最佳节点", action: #selector(switchToBest), keyEquivalent: "b")
    private let restoreItem = NSMenuItem(title: "恢复上一个节点", action: #selector(restorePrevious), keyEquivalent: "z")
    private let repairItem = NSMenuItem(title: "修复 Clash 集成", action: #selector(repairClashIntegration), keyEquivalent: "")
    private let logsItem = NSMenuItem(title: "打开日志", action: #selector(openLogs), keyEquivalent: "l")
    private let panelItem = NSMenuItem(title: "打开控制面板", action: #selector(openControlPanel), keyEquivalent: "o")

    func applicationDidFinishLaunching(_ notification: Notification) {
        try? FileManager.default.createDirectory(at: Paths.supportDir, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: Paths.logDir, withIntermediateDirectories: true)
        _ = try? ConfigRepair.backupClashConfig(reason: "startup")
        Logger.write("Codex Node Keeper launched.")
        setupMenu()
        startTimer()
        runCheck(auto: false)
        if !launchedInBackground {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                self.openControlPanel()
            }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        openControlPanel()
        return true
    }

    private func setupMenu() {
        statusItem.button?.title = "CK"
        statusItem.button?.toolTip = "Codex Node Keeper"
        for item in [statusItemView, nodeItem, outletItem, delayItem] {
            item.isEnabled = false
            menu.addItem(item)
        }
        menu.addItem(.separator())
        for item in [panelItem, toggleItem, checkItem, bestItem, restoreItem, repairItem, logsItem] {
            item.target = self
            menu.addItem(item)
        }
        menu.addItem(.separator())
        menu.addItem(withTitle: "退出", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        statusItem.menu = menu
        renderMenu()
    }

    private func startTimer() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: config.checkIntervalSeconds, repeats: true) { [weak self] _ in
            self?.runCheck(auto: true)
        }
    }

    private func renderMenu() {
        DispatchQueue.main.async {
            self.statusItem.button?.title = self.config.enabled ? "CK●" : "CK"
            self.statusItemView.title = "Status: \(self.statusLine)"
            self.nodeItem.title = "OpenAI: \(self.policyNode)"
            self.outletItem.title = "Outlet: \(self.actualNode)"
            let delayText = self.judge.lastDelay.map { "\($0)ms" } ?? "--"
            self.delayItem.title = "Last check: \(delayText) · Failures: \(self.judge.failureCount)"
            self.toggleItem.title = self.config.enabled ? "关闭 Codex 自动择优" : "开启 Codex 自动择优"
            self.restoreItem.isEnabled = self.judge.previousNode != nil && !self.isBusy
            for item in [self.panelItem, self.toggleItem, self.checkItem, self.bestItem, self.repairItem, self.logsItem] {
                item.isEnabled = !self.isBusy
            }
            self.controlPanel.update(
                config: self.config,
                status: self.statusLine,
                policyNode: self.policyNode,
                actualNode: self.actualNode,
                routePath: self.routePath,
                delay: self.judge.lastDelay,
                failures: self.judge.failureCount,
                lastSwitch: self.judge.lastSwitch,
                candidateCount: self.candidateCount,
                canRestore: self.judge.previousNode != nil,
                busy: self.isBusy
            )
        }
    }

    @objc private func toggleAuto() {
        config.enabled.toggle()
        ConfigStore.save(config)
        statusLine = config.enabled ? "Auto On" : "Auto Off"
        Logger.write("Auto mode changed: \(config.enabled)")
        renderMenu()
        if config.enabled { runCheck(auto: false) }
    }

    @objc private func runManualCheck() {
        runCheck(auto: false)
    }

    @objc private func switchToBest() {
        evaluateAndSwitch(force: true)
    }

    @objc private func restorePrevious() {
        guard let previous = judge.previousNode else { return }
        performAsync("Restoring...") {
            try self.client.setNode(previous)
            Logger.write("Restored node to \(previous)")
        }
    }

    @objc private func repairClashIntegration() {
        performAsync("Repairing...") {
            try ConfigRepair.repair()
        }
    }

    @objc private func openLogs() {
        NSWorkspace.shared.open(Paths.logFile)
    }

    @objc private func openControlPanel() {
        controlPanel.showPanel()
        renderMenu()
    }

    func controlPanelToggleAuto() {
        toggleAuto()
    }

    func controlPanelRunCheck() {
        runManualCheck()
    }

    func controlPanelSwitchBest() {
        switchToBest()
    }

    func controlPanelRestorePrevious() {
        restorePrevious()
    }

    func controlPanelRepair() {
        repairClashIntegration()
    }

    func controlPanelOpenLogs() {
        openLogs()
    }

    private func performAsync(_ busyStatus: String, work: @escaping () throws -> Void) {
        guard !isBusy else { return }
        isBusy = true
        statusLine = busyStatus
        renderMenu()
        DispatchQueue.global(qos: .utility).async {
            do {
                try work()
                self.statusLine = "OK"
            } catch {
                self.statusLine = "Error: \(error.localizedDescription)"
                Logger.write("Error: \(error.localizedDescription)")
            }
            self.isBusy = false
            self.runCheck(auto: false)
        }
    }

    private func runCheck(auto: Bool) {
        guard !isBusy else { return }
        if auto && !config.enabled { return }
        isBusy = true
        statusLine = "Checking..."
        renderMenu()
        DispatchQueue.global(qos: .utility).async {
            defer {
                self.isBusy = false
                self.renderMenu()
            }
            do {
                let group = try self.client.getGroup()
                self.updateRoute(from: group)
                self.candidateCount = self.prioritizedCandidates(from: group.all ?? [], current: group.now ?? "").count
                let total = try self.client.currentHTTPHealth()
                let ms = Int(total * 1000)
                self.judge.recordSuccess(delay: ms)
                self.statusLine = auto ? "Auto On" : "Healthy"
                Logger.write("Health OK policy=\(self.policyNode), outlet=\(self.actualNode), total=\(ms)ms")
            } catch {
                self.judge.recordFailure()
                self.statusLine = "Failure \(self.judge.failureCount)"
                Logger.write("Health failed: \(error.localizedDescription)")
                if auto && self.judge.shouldEvaluateCandidates(config: self.config) {
                    self.evaluateAndSwitch(force: false)
                }
            }
        }
    }

    private func evaluateAndSwitch(force: Bool) {
        guard !isBusy || force == false else { return }
        isBusy = true
        statusLine = "Finding best..."
        renderMenu()
        DispatchQueue.global(qos: .utility).async {
            defer {
                self.isBusy = false
                self.renderMenu()
            }
            do {
                let group = try self.client.getGroup()
                let oldNode = group.now ?? ""
                self.updateRoute(from: group)
                let candidates = self.prioritizedCandidates(from: group.all ?? [], current: oldNode)
                self.candidateCount = candidates.count
                guard !candidates.isEmpty else { throw KeeperError.noCandidates }
                let best = try self.bestCandidate(candidates)
                if best.name != oldNode {
                    try self.client.setNode(best.name)
                    self.judge.recordSwitch(from: oldNode)
                    self.policyNode = best.name
                    self.currentNode = best.name
                    self.routePath = [self.config.groupName, best.name]
                    self.actualNode = self.resolveActualOutlet(policyNode: best.name)
                    self.judge.recordSuccess(delay: best.delay)
                    self.statusLine = "Switched · \(best.delay)ms"
                    Logger.write("Switched OpenAI node from \(oldNode) to \(best.name), delay=\(best.delay)ms")
                } else {
                    self.statusLine = "Current is best · \(best.delay)ms"
                    self.judge.recordSuccess(delay: best.delay)
                    Logger.write("Current node remains best: \(oldNode), delay=\(best.delay)ms")
                }
            } catch {
                self.statusLine = "Error: \(error.localizedDescription)"
                Logger.write("Switch evaluation failed: \(error.localizedDescription)")
            }
        }
    }

    private func updateRoute(from group: ProxyGroup) {
        let policy = group.now ?? "Unknown"
        policyNode = policy
        currentNode = policy
        routePath = resolveRoute(start: config.groupName, group: group)
        actualNode = routePath.last ?? policy
    }

    private func resolveRoute(start: String, group: ProxyGroup) -> [String] {
        var path = [start]
        guard var next = group.now, !next.isEmpty else { return path }
        var visited = Set(path)
        for _ in 0..<5 {
            path.append(next)
            if visited.contains(next) { break }
            visited.insert(next)
            guard let proxy = try? client.getProxy(next),
                  let nested = proxy.now,
                  nested != next,
                  proxy.all != nil else {
                break
            }
            next = nested
        }
        return path
    }

    private func resolveActualOutlet(policyNode: String) -> String {
        var current = policyNode
        var visited = Set([config.groupName])
        for _ in 0..<5 {
            guard !visited.contains(current) else { return current }
            visited.insert(current)
            guard let proxy = try? client.getProxy(current),
                  let next = proxy.now,
                  next != current,
                  proxy.all != nil else {
                return current
            }
            current = next
        }
        return current
    }

    private func prioritizedCandidates(from nodes: [String], current: String) -> [String] {
        let configured = config.candidateNodes.filter { nodes.contains($0) }
        let source = configured.isEmpty ? nodes : configured
        let realNodes = source.filter { isUsableRealNode($0) }
        let withCurrent = isUsableRealNode(current) ? [current] + realNodes : realNodes
        return Array(NSOrderedSet(array: withCurrent).array as? [String] ?? [])
            .filter { !$0.isEmpty }
    }

    private func isUsableRealNode(_ node: String) -> Bool {
        let value = node.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return false }
        let blockedSelectors = ["自动选择", "故障转移", "大哥云", "DIRECT", "REJECT", "GLOBAL"]
        if blockedSelectors.contains(value) { return false }
        let lower = value.lowercased()
        if lower.hasPrefix("chatgpt") || lower.hasPrefix("gpt") || lower.contains("chatgpt/tiktok") {
            return true
        }
        if let first = value.unicodeScalars.first,
           (0x1F1E6...0x1F1FF).contains(Int(first.value)) {
            return true
        }
        let countryPrefixes = [
            "美国", "日本", "新加坡", "香港", "台湾", "韩国", "英国", "德国", "法国", "加拿大",
            "澳大利亚", "荷兰", "俄罗斯", "印度", "泰国", "越南", "菲律宾", "马来西亚", "印尼",
            "土耳其", "巴西", "阿根廷", "墨西哥", "意大利", "西班牙", "瑞士", "瑞典"
        ]
        return countryPrefixes.contains { value.hasPrefix($0) }
    }

    private func bestCandidate(_ nodes: [String]) throws -> (name: String, delay: Int) {
        let url = config.testUrls.first ?? "https://api.openai.com/v1/models"
        var best: (String, Int)?
        for node in nodes {
            do {
                let first = try client.delay(node: node, url: url)
                let second = try client.delay(node: node, url: url)
                let avg = (first + second) / 2
                Logger.write("Candidate delay node=\(node), first=\(first), second=\(second), avg=\(avg)")
                if best == nil || avg < best!.1 {
                    best = (node, avg)
                }
            } catch {
                Logger.write("Candidate failed node=\(node), error=\(error.localizedDescription)")
            }
        }
        guard let best else { throw KeeperError.noCandidates }
        return best
    }
}

let app = NSApplication.shared
let delegate = KeeperApp()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
