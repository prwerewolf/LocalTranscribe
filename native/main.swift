import Cocoa
import WebKit

final class LocalWebView: WKWebView {
    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation { .copy }
    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        guard let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL] else { return false }
        deliver("nativeFilesSelected", urls.map { $0.path })
        return true
    }
    func deliver(_ function: String, _ value: Any) {
        guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed]),
              let text = String(data: data, encoding: .utf8) else { return }
        evaluateJavaScript("window.\(function)(\(text))")
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    var window: NSWindow!
    var web: LocalWebView!
    var server: Process?
    var timer: Timer?
    var checking = false
    var attempts = 0
    let resources = Bundle.main.bundleURL.appendingPathComponent("Contents/Resources")
    var root: URL { resources.appendingPathComponent("app") }
    var dataDirectory: URL {
        if let override = ProcessInfo.processInfo.environment["LOCALTRANSCRIBE_DATA_DIR"] {
            return URL(fileURLWithPath: override, isDirectory: true)
        }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("LocalTranscribe", isDirectory: true)
    }
    let address = URL(string: "http://127.0.0.1:8789/")!

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(NSMenuItem(title: "Quit LocalTranscribe", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        appItem.submenu = appMenu
        menu.addItem(appItem)
        let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "Edit")
        for (title, selector, key) in [("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            editMenu.addItem(NSMenuItem(title: title, action: Selector(selector), keyEquivalent: key))
        }
        editItem.submenu = editMenu
        menu.addItem(editItem)
        NSApp.mainMenu = menu
        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "picker")
        web = LocalWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.registerForDraggedTypes([.fileURL])
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1020, height: 780), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "LocalTranscribe"
        window.minSize = NSSize(width: 740, height: 600)
        window.contentView = web
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        web.loadHTMLString("<body style='font-family:-apple-system;padding:40px;color:#176b52'><h2>Opening LocalTranscribe…</h2></body>", baseURL: nil)
        let process = Process()
        process.executableURL = resources.appendingPathComponent("python/bin/python3")
        process.arguments = ["-s", root.appendingPathComponent("app.py").path]
        process.currentDirectoryURL = root
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONHOME"] = resources.appendingPathComponent("python").path
        environment["PYTHONPATH"] = nil
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PATH"] = resources.appendingPathComponent("tools/bin").path + ":/usr/bin:/bin:/usr/sbin:/sbin"
        process.environment = environment
        let logURL = dataDirectory.appendingPathComponent("server.log")
        do { try FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true) }
        catch { showError("The local app data folder could not be opened: " + error.localizedDescription); return }
        if !FileManager.default.fileExists(atPath: logURL.path) { FileManager.default.createFile(atPath: logURL.path, contents: nil) }
        let log = try? FileHandle(forWritingTo: logURL)
        log?.seekToEndOfFile()
        process.standardOutput = log
        process.standardError = log
        do { try process.run(); server = process }
        catch { showError(error.localizedDescription); return }
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in self?.checkReady() }
    }

    func checkReady() {
        if checking { return }
        checking = true
        attempts += 1
        var request = URLRequest(url: address.appendingPathComponent("health"))
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { [weak self] data, _, _ in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.checking = false
                if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: String], json["root"] == self.root.path {
                    self.timer?.invalidate()
                    self.web.load(URLRequest(url: self.address))
                } else if self.attempts > 40 {
                    self.timer?.invalidate()
                    self.showError("The local app server could not start. See server.log in " + self.dataDirectory.path)
                }
            }
        }.resume()
    }

    func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "LocalTranscribe could not open"
        alert.informativeText = message
        alert.runModal()
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "picker", let body = message.body as? [String: String], let mode = body["mode"] else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = mode != "files"
        panel.canChooseFiles = mode == "files"
        panel.allowsMultipleSelection = mode == "files"
        panel.prompt = mode == "output" ? "Save here" : "Add"
        panel.beginSheetModal(for: window) { [weak self] response in
            guard response == .OK, let self = self else { return }
            if mode == "output", let path = panel.url?.path { self.web.deliver("nativeOutputSelected", path) }
            else { self.web.deliver("nativeFilesSelected", panel.urls.map { $0.path }) }
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = navigationAction.request.url
        decisionHandler(url?.host == "127.0.0.1" || url?.scheme == "about" ? .allow : .cancel)
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        if let server = server, server.isRunning { server.terminate(); server.waitUntilExit() }
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
