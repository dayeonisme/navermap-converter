// 커스텀 아이콘 주입 — macOS 아이콘 캐시를 무시하고 즉시 반영시킨다.
// 사용법: swift seticon.swift <아이콘.png> <대상.app>
import Cocoa

let args = CommandLine.arguments
guard args.count >= 3, let img = NSImage(contentsOfFile: args[1]) else {
    FileHandle.standardError.write("usage: swift seticon.swift <icon.png> <target.app>\n".data(using: .utf8)!)
    exit(1)
}
let ok = NSWorkspace.shared.setIcon(img, forFile: args[2], options: [])
print(ok ? "icon set: \(args[2])" : "icon FAILED: \(args[2])")
