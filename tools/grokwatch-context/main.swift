// grokwatch-context: GrokWatch Gateway から呼ばれる、予定とメールの読み取り補助コマンド。
// ビルド: deploy/macos/install.sh（swiftc -O、Info.plist を埋め込む）
//
// 終了コード: 0 成功 / 3 権限なし / 4 メール.app が起動していない / 5 読み取り失敗 / 64 引数不正
// メール本文は読まない（差出人・件名・受信日時だけ）。

import AppKit
import EventKit
import Foundation

let toolVersion = "1.2.0"
let maxEvents = 30
let mailScanCap = 200

let usageText = """
Usage:
  grokwatch-context schedule --from YYYY-MM-DD --to YYYY-MM-DD
  grokwatch-context mail --since-hours N --limit N [--unread-only]
  grokwatch-context --version
"""

func printError(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

func fail(_ code: Int32, _ message: String) -> Never {
    printError(message)
    exit(code)
}

func usageFailure() -> Never {
    fail(64, usageText)
}

func writeJSON(_ object: [String: Any]) -> Never {
    guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else {
        fail(5, "JSON の作成に失敗しました")
    }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(0)
}

let isoFormatter: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    formatter.timeZone = TimeZone.current
    return formatter
}()

// MARK: - 引数

func parseDay(_ text: String) -> DateComponents? {
    let parts = text.split(separator: "-", omittingEmptySubsequences: false)
    guard parts.count == 3, parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
          let year = Int(parts[0]), let month = Int(parts[1]), let day = Int(parts[2]) else {
        return nil
    }
    var components = DateComponents()
    components.year = year
    components.month = month
    components.day = day
    guard let date = Calendar.current.date(from: components) else { return nil }
    let check = Calendar.current.dateComponents([.year, .month, .day], from: date)
    guard check.year == year, check.month == month, check.day == day else { return nil }
    return components
}

func optionValue(_ arguments: [String], _ name: String) -> String? {
    guard let index = arguments.firstIndex(of: name), index + 1 < arguments.count else { return nil }
    return arguments[index + 1]
}

func checkOptions(_ arguments: [String], values: Set<String>, flags: Set<String>) {
    var index = 0
    var seen = Set<String>()
    while index < arguments.count {
        let argument = arguments[index]
        if values.contains(argument) {
            guard index + 1 < arguments.count, !seen.contains(argument) else { usageFailure() }
            seen.insert(argument)
            index += 2
        } else if flags.contains(argument) {
            guard !seen.contains(argument) else { usageFailure() }
            seen.insert(argument)
            index += 1
        } else {
            usageFailure()
        }
    }
}

// MARK: - schedule（EventKit）

func runSchedule(_ arguments: [String]) -> Never {
    checkOptions(arguments, values: ["--from", "--to"], flags: [])
    guard let fromText = optionValue(arguments, "--from"), let toText = optionValue(arguments, "--to"),
          let fromDay = parseDay(fromText), let toDay = parseDay(toText),
          let fromDate = Calendar.current.date(from: fromDay),
          let toDayStart = Calendar.current.date(from: toDay),
          let rangeEnd = Calendar.current.date(byAdding: DateComponents(day: 1, second: -1), to: toDayStart),
          fromDate <= rangeEnd else {
        usageFailure()
    }

    let store = EKEventStore()
    switch EKEventStore.authorizationStatus(for: .event) {
    case .fullAccess:
        break
    case .notDetermined:
        let semaphore = DispatchSemaphore(value: 0)
        var granted = false
        store.requestFullAccessToEvents { allowed, _ in
            granted = allowed
            semaphore.signal()
        }
        if semaphore.wait(timeout: .now() + 30) == .timedOut || !granted {
            fail(3, "カレンダーへのアクセスが許可されていません")
        }
    default:
        fail(3, "カレンダーへのアクセスが許可されていません")
    }

    let predicate = store.predicateForEvents(withStart: fromDate, end: rangeEnd, calendars: nil)
    let events = store.events(matching: predicate)
        .sorted { $0.startDate < $1.startDate }
        .prefix(maxEvents)
    let items: [[String: Any]] = events.map { event in
        [
            "title": event.title ?? "",
            "start": isoFormatter.string(from: event.startDate),
            "end": isoFormatter.string(from: event.endDate),
            "all_day": event.isAllDay,
            "location": event.location ?? "",
            "calendar": event.calendar?.title ?? "",
        ]
    }
    writeJSON(["events": items])
}

// MARK: - mail（AppleScript、本文は読まない）

let unitSeparator = "\u{1F}"
let recordSeparator = "\u{1E}"

func mailScript(sinceHours: Int, unreadOnly: Bool) -> String {
    let filter = unreadOnly
        ? "date received > cutoff and read status is false"
        : "date received > cutoff"
    return """
    set us to (ASCII character 31)
    set rs to (ASCII character 30)
    set cutoff to (current date) - (\(sinceHours) * hours)
    set outText to ""
    tell application "Mail"
        set found to (messages of inbox whose \(filter))
        set n to count of found
        if n > \(mailScanCap) then set n to \(mailScanCap)
        repeat with i from 1 to n
            try
                set m to item i of found
                set d to date received of m
                set senderText to (sender of m) as text
                set subjectText to (subject of m) as text
                set stamp to ((year of d) as integer as text) & us & ((month of d) as integer as text) & us & ((day of d) as integer as text) & us & ((hours of d) as integer as text) & us & ((minutes of d) as integer as text) & us & ((seconds of d) as integer as text)
                set outText to outText & senderText & us & subjectText & us & stamp & rs
            end try
        end repeat
    end tell
    return outText
    """
}

func runMail(_ arguments: [String]) -> Never {
    checkOptions(arguments, values: ["--since-hours", "--limit"], flags: ["--unread-only"])
    guard let hoursText = optionValue(arguments, "--since-hours"), let sinceHours = Int(hoursText),
          sinceHours > 0, sinceHours <= 24 * 90,
          let limitText = optionValue(arguments, "--limit"), let limit = Int(limitText),
          limit > 0, limit <= 100 else {
        usageFailure()
    }
    let unreadOnly = arguments.contains("--unread-only")

    // メール.app を起動しない。起動していなければ 4 で終わる。
    if NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.mail").isEmpty {
        fail(4, "メール.app が起動していません")
    }

    var errorInfo: NSDictionary?
    guard let script = NSAppleScript(source: mailScript(sinceHours: sinceHours, unreadOnly: unreadOnly)) else {
        fail(5, "メールの読み取りを開始できません")
    }
    let result = script.executeAndReturnError(&errorInfo)
    if let errorInfo = errorInfo {
        let number = errorInfo["NSAppleScriptErrorNumber"] as? Int ?? 0
        if number == -1743 {
            fail(3, "メールの操作が許可されていません")
        }
        if number == -600 {
            fail(4, "メール.app が起動していません")
        }
        fail(5, "メールの読み取りに失敗しました（\(number)）")
    }

    let raw = result.stringValue ?? ""
    var parsed: [(date: Date, from: String, subject: String)] = []
    for record in raw.components(separatedBy: recordSeparator) where !record.isEmpty {
        let fields = record.components(separatedBy: unitSeparator)
        guard fields.count == 8 else { continue }
        let numbers = fields[2...7].compactMap { Int($0) }
        guard numbers.count == 6 else { continue }
        var components = DateComponents()
        components.year = numbers[0]
        components.month = numbers[1]
        components.day = numbers[2]
        components.hour = numbers[3]
        components.minute = numbers[4]
        components.second = numbers[5]
        guard let date = Calendar.current.date(from: components) else { continue }
        parsed.append((date: date, from: fields[0], subject: fields[1]))
    }
    parsed.sort { $0.date > $1.date }
    let messages: [[String: Any]] = parsed.prefix(limit).map { message in
        [
            "from": message.from,
            "subject": message.subject,
            "received": isoFormatter.string(from: message.date),
        ]
    }
    writeJSON(["messages": messages])
}

// MARK: - 入口

let arguments = Array(CommandLine.arguments.dropFirst())
guard let command = arguments.first else { usageFailure() }
switch command {
case "--version":
    guard arguments.count == 1 else { usageFailure() }
    print(toolVersion)
    exit(0)
case "schedule":
    runSchedule(Array(arguments.dropFirst()))
case "mail":
    runMail(Array(arguments.dropFirst()))
default:
    usageFailure()
}
