#!/usr/bin/env python3
"""Check firmware C++ stack frames and task path budgets."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
FRAME_LIMIT = 2048
FRAME_EXCEPTIONS = {
    "gwapp::audioTask(void*)": (3072, "Capture と Playback の状態をループ間で保持する")
}
TASKS = {
    "net": "netTask",
    "buttons": "buttonTask",
    "render": "renderTask",
    "audio": "audioTask",
}


@dataclass(frozen=True)
class FunctionFrame:
    name: str
    size: int


@dataclass(frozen=True)
class TaskStack:
    function: str
    size: int


@dataclass(frozen=True)
class StackPath:
    task: str
    label: str
    functions: tuple[str, ...]
    reserve: int


STACK_PATHS = (
    StackPath("net", "設定読み込み", (
        "=gwapp::netTask(void*)", "gwapp::readConfig()"
    ), 3072),
    StackPath("net", "Network 構築", (
        "=gwapp::netTask(void*)", "Network::Network(", "Socket::Socket()"
    ), 3072),
    StackPath("net", "Wi-Fi 診断走査", (
        "=gwapp::netTask(void*)", "Network::run()", "startWifi(", "diagScan("
    ), 3072),
    StackPath("net", "WebSocket テキスト受信", (
        "=gwapp::netTask(void*)", "Network::run()", "Network::pollSocket()", "Network::receiveText("
    ), 3072),
    StackPath("net", "WebSocket hello 送信", (
        "=gwapp::netTask(void*)", "Network::run()", "Network::pollSocket()",
        "Network::receiveText(", "Network::linkAction(", "Network::send(",
        "Socket::sendText(", "=grokwatch::encode[abi:cxx11](grokwatch::Message const&)"
    ), 3072),
    StackPath("net", "JSON エスケープ解析", (
        "=gwapp::netTask(void*)", "Network::run()", "Network::pollSocket()",
        "Network::receiveText(",
        "=grokwatch::decode(std::basic_string_view<char, std::char_traits<char> >)",
        "Parser::object()", "Parser::value()",
        "Parser::quoted()", "Parser::escape(", "Parser::hexQuad()"
    ), 3072),
    StackPath("net", "JSON メッセージ検証", (
        "=gwapp::netTask(void*)", "Network::run()", "Network::pollSocket()",
        "Network::receiveText(",
        "=grokwatch::decode(std::basic_string_view<char, std::char_traits<char> >)",
        "hasFields(", "Message::string("
    ), 3072),
    StackPath("net", "音声送信", (
        "=gwapp::netTask(void*)", "Network::run()", "Network::capture()"
    ), 3072),
    StackPath("net", "Wi-Fi 状態確認", (
        "=gwapp::netTask(void*)", "Network::run()", "Network::pollWifi("
    ), 3072),
    StackPath("buttons", "音量ボタン処理", (
        "=gwapp::buttonTask(void*)", "VolumeKeys::sample("
    ), 2048),
    StackPath("render", "表情計算", (
        "=gwapp::renderTask(void*)", "renderTask(void*)::{lambda()#1}", "FaceAnimator::frame("
    ), 2048),
    StackPath("render", "表情描画", (
        "=gwapp::renderTask(void*)", "drawFace(", "scaleFace("
    ), 2048),
    StackPath("render", "リング描画", (
        "=gwapp::renderTask(void*)", "drawFace(", "drawRing("
    ), 2048),
    StackPath("audio", "録音処理", (
        "=gwapp::audioTask(void*)", "Capture::pump(", "captureFault("
    ), 3072),
    StackPath("audio", "再生処理", (
        "=gwapp::audioTask(void*)", "Playback::pump(", "Playback::fault("
    ), 3072),
    StackPath("audio", "再生停止", (
        "=gwapp::audioTask(void*)", "Playback::pump(", "Playback::stop("
    ), 3072),
    StackPath("audio", "再生バッファ排出待ち", (
        "=gwapp::audioTask(void*)", "Playback::pump(", "Playback::dmaTail("
    ), 3072),
)


class CheckError(Exception):
    pass


def parse_disassembly(text: str) -> list[FunctionFrame]:
    frames: list[FunctionFrame] = []
    current_name: str | None = None
    current_size = 0
    for line in text.splitlines():
        symbol = re.match(r"^\s*[0-9a-fA-F]+ <(.+)>:$", line)
        if symbol:
            if current_name and ("gwapp::" in current_name or "grokwatch::" in current_name):
                frames.append(FunctionFrame(current_name, current_size))
            current_name = symbol.group(1)
            current_size = 0
        elif current_name:
            entry = re.search(r"\bentry\s+a1,\s*(0x[0-9a-fA-F]+|[0-9]+)", line)
            if entry:
                current_size = int(entry.group(1), 0)
    if current_name and ("gwapp::" in current_name or "grokwatch::" in current_name):
        frames.append(FunctionFrame(current_name, current_size))
    if not frames:
        raise CheckError("gwapp:: または grokwatch:: の関数を逆アセンブルから読めません")
    return frames


def parse_task_stacks(source: str) -> dict[str, TaskStack]:
    stacks: dict[str, TaskStack] = {}
    for function, name, size in re.findall(
        r'xTaskCreate\s*\(\s*(\w+)\s*,\s*"([^"]+)"\s*,\s*(\d+)', source, re.DOTALL
    ):
        if name in stacks:
            raise CheckError(f"app_main.cpp でタスク名 {name!r} が重複しています")
        stacks[name] = TaskStack(function, int(size))
    missing = sorted(set(TASKS) - stacks.keys())
    if missing:
        raise CheckError(f"app_main.cpp にタスクがありません: {', '.join(missing)}")
    for name, expected in TASKS.items():
        if stacks[name].function != expected:
            raise CheckError(f"app_main.cpp の {name} タスクは {expected} を起動してください")
    return stacks


def selected_frame(frames: list[FunctionFrame], selector: str) -> FunctionFrame:
    if selector.startswith("="):
        matches = [frame for frame in frames if selector[1:] == frame.name]
    else:
        matches = [frame for frame in frames if selector in frame.name]
    if len(matches) != 1:
        raise CheckError(f"関数指定 {selector!r} の一致数が {len(matches)} です")
    return matches[0]


def check_stack(disassembly: str, app_source: str) -> tuple[str, list[str]]:
    frames = parse_disassembly(disassembly)
    stacks = parse_task_stacks(app_source)
    lines = ["関数枠上限: 通常 2,048 B。audioTask は 3,072 B。"]
    errors: list[str] = []
    maximum = max(frames, key=lambda frame: frame.size)
    lines.append(f"最大関数枠: {maximum.size:,} B  {maximum.name}")
    for name, (limit, reason) in FRAME_EXCEPTIONS.items():
        lines.append(f"例外上限: {name} は {limit:,} B。理由は {reason}。")
    for frame in frames:
        limit, reason = FRAME_EXCEPTIONS.get(frame.name, (FRAME_LIMIT, ""))
        if frame.size > limit:
            detail = f"{frame.name}: {frame.size:,} B > {limit:,} B"
            if reason:
                detail += f" ({reason})"
            errors.append(detail)

    lines.append("列挙したタスク経路 | 関数枠合計 + 余裕 | 使用見積もり | タスクスタック")
    for path in STACK_PATHS:
        path_frames = [selected_frame(frames, selector) for selector in path.functions]
        measured = sum(frame.size for frame in path_frames)
        total = measured + path.reserve
        stack_size = stacks[path.task].size
        lines.append(
            f"{path.task} {path.label} | {measured:,} + {path.reserve:,} = {total:,} B | "
            f"{total:,} B | {stack_size:,} B"
        )
        if total > stack_size:
            errors.append(
                f"{path.task} {path.label}: {measured:,} B + 余裕 {path.reserve:,} B "
                f"= {total:,} B > タスク枠 {stack_size:,} B"
            )
    return "\n".join(lines), errors


def read_disassembly(args: argparse.Namespace) -> str:
    if args.disassembly_file:
        return args.disassembly_file.read_text()
    objdump = args.objdump or os.environ.get("XTENSA_OBJDUMP") or shutil.which(
        "xtensa-esp32s3-elf-objdump"
    )
    if not objdump:
        raise CheckError("xtensa-esp32s3-elf-objdump が PATH にありません")
    try:
        return subprocess.check_output([objdump, "-dC", str(args.elf)], text=True)
    except subprocess.CalledProcessError as error:
        raise CheckError(f"objdump が終了コード {error.returncode} で失敗しました") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", nargs="?", type=Path, default=REPO_ROOT / "firmware/build/grokwatch.elf")
    parser.add_argument("--objdump", help="xtensa-esp32s3-elf-objdump の実行ファイル")
    parser.add_argument("--disassembly-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--app-main", type=Path, default=REPO_ROOT / "firmware/main/app_main.cpp")
    args = parser.parse_args()
    try:
        report, errors = check_stack(read_disassembly(args), args.app_main.read_text())
    except (CheckError, OSError) as error:
        print(f"スタック検査エラー: {error}", file=sys.stderr)
        return 1
    print(report)
    if errors:
        print("検査失敗:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("スタック検査: 合格")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
