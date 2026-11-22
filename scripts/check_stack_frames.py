#!/usr/bin/env python3
"""Check firmware task stack paths from direct calls in an Xtensa ELF."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
FRAME_LIMIT = 2048
INTERNAL_PREFIXES = ("gwapp::", "grokwatch::")
TASKS = {
    "net": "netTask",
    "audio": "audioTask",
    "render": "renderTask",
    "buttons": "buttonTask",
    "touch": "touchTask",
}


@dataclass(frozen=True)
class DirectCall:
    address: int
    name: str | None


@dataclass(frozen=True)
class FunctionFrame:
    address: int
    name: str
    size: int | None
    calls: tuple[DirectCall, ...]


@dataclass(frozen=True)
class TaskStack:
    function: str
    size: int


@dataclass(frozen=True)
class Reserve:
    size: int
    basis: str


RESERVES = {
    "net": Reserve(3072, "_vfprintf_r と ESP_LOG、Wi-Fi、FreeRTOS の呼び出し連鎖を見込む"),
    "audio": Reserve(3072, "M5Unified の Mic、Speaker、I2S 呼び出し連鎖を見込む"),
    "render": Reserve(3072, "M5GFX と M5Unified の描画呼び出し連鎖を見込む"),
    "buttons": Reserve(2048, "GPIO と FreeRTOS の呼び出し連鎖を見込む"),
    "touch": Reserve(3072, "M5Unified、LGFX I2C、FreeRTOS の呼び出し連鎖を見込む"),
}


class CheckError(Exception):
    pass


def is_internal(name: str) -> bool:
    return name.startswith(INTERNAL_PREFIXES)


def parse_disassembly(text: str) -> list[FunctionFrame]:
    frames: list[FunctionFrame] = []
    current_address: int | None = None
    current_name: str | None = None
    current_size: int | None = None
    current_calls: list[DirectCall] = []

    def finish_function() -> None:
        if current_address is None or current_name is None:
            return
        frames.append(FunctionFrame(
            current_address, current_name, current_size, tuple(current_calls)
        ))

    for line in text.splitlines():
        symbol = re.match(r"^\s*([0-9a-fA-F]+)\s+<(.+)>:$", line)
        if symbol:
            finish_function()
            current_address = int(symbol.group(1), 16)
            current_name = symbol.group(2)
            current_size = None
            current_calls = []
            continue
        if current_name is None:
            continue
        entry = re.search(r"\bentry\s+a1,\s*(0x[0-9a-fA-F]+|[0-9]+)", line)
        if entry:
            current_size = int(entry.group(1), 0)
        call = re.search(
            r"\bcall(?:0|4|8|12)\s+(?:0x)?([0-9a-fA-F]+)", line
        )
        if call:
            annotation = re.search(r"\bcall(?:0|4|8|12)\s+.*?<(.+)>\s*$", line)
            current_calls.append(DirectCall(
                int(call.group(1), 16), annotation.group(1) if annotation else None
            ))
    finish_function()

    unreadable = sorted(
        frame.name for frame in frames if is_internal(frame.name) and frame.size is None
    )
    if unreadable:
        raise CheckError(
            "gwapp:: / grokwatch:: 関数の枠を読み取れません: " + ", ".join(unreadable)
        )
    if not any(is_internal(frame.name) for frame in frames):
        raise CheckError("gwapp:: または grokwatch:: の関数を逆アセンブルから読めません")
    return frames


def parse_task_stacks(source: str) -> dict[str, TaskStack]:
    stacks: dict[str, TaskStack] = {}
    for function, name, size in re.findall(
        r'xTaskCreate\s*\(\s*(\w+)\s*,\s*"([^"]+)"\s*,\s*(\d+)',
        source,
        re.DOTALL,
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


def build_graph(
    frames: list[FunctionFrame],
) -> tuple[dict[int, FunctionFrame], dict[int, set[int]], dict[int, list[tuple[str, int | None]]]]:
    by_address: dict[int, FunctionFrame] = {}
    for frame in frames:
        existing = by_address.get(frame.address)
        if existing is None or (not is_internal(existing.name) and is_internal(frame.name)):
            by_address[frame.address] = frame

    graph: dict[int, set[int]] = {
        frame.address: set() for frame in frames if is_internal(frame.name)
    }
    external_calls: dict[int, list[tuple[str, int | None]]] = {
        address: [] for address in graph
    }
    for frame in frames:
        if not is_internal(frame.name):
            continue
        for call in frame.calls:
            target = by_address.get(call.address)
            if target is not None and is_internal(target.name):
                graph[frame.address].add(target.address)
                continue
            target_name = target.name if target else call.name
            if target_name and is_internal(target_name):
                raise CheckError(
                    f"内部呼び出し {frame.name} -> {target_name} の entry が見つかりません"
                )
            external_calls[frame.address].append((
                target_name or f"0x{call.address:x}",
                target.size if target else None,
            ))
    return by_address, graph, external_calls


def find_task_entry(frames: list[FunctionFrame], task: str, function: str) -> FunctionFrame:
    expected = f"gwapp::{function}(void*)"
    matches = [frame for frame in frames if frame.name == expected]
    if len(matches) != 1:
        raise CheckError(
            f"{task} タスク入口 {expected!r} の一致数が {len(matches)} です"
        )
    return matches[0]


def maximum_path(
    root: int,
    frames: dict[int, FunctionFrame],
    graph: dict[int, set[int]],
    memo: dict[int, tuple[int, tuple[int, ...]]],
    active: list[int],
    errors: list[str],
) -> tuple[int, tuple[int, ...]]:
    if root in active:
        start = active.index(root)
        cycle = active[start:] + [root]
        names = " -> ".join(frames[address].name for address in cycle)
        error = f"再帰呼び出しを検出しました: {names}"
        if error not in errors:
            errors.append(error)
        return 0, ()
    if root in memo:
        return memo[root]

    active.append(root)
    frame = frames[root]
    best_size = int(frame.size or 0)
    best_path = (root,)
    for child in sorted(graph.get(root, ()), key=lambda address: frames[address].name):
        child_size, child_path = maximum_path(child, frames, graph, memo, active, errors)
        if not child_path:
            continue
        total = int(frame.size or 0) + child_size
        if total > best_size:
            best_size = total
            best_path = (root,) + child_path
    active.pop()
    memo[root] = best_size, best_path
    return memo[root]


def reachable_external_calls(
    root: int,
    graph: dict[int, set[int]],
    external_calls: dict[int, list[tuple[str, int | None]]],
) -> list[tuple[str, int | None]]:
    pending = [root]
    visited: set[int] = set()
    calls: list[tuple[str, int | None]] = []
    while pending:
        address = pending.pop()
        if address in visited:
            continue
        visited.add(address)
        calls.extend(external_calls.get(address, ()))
        pending.extend(graph.get(address, ()))
    return calls


def check_stack(
    disassembly: str, app_source: str, elf_sha256: str
) -> tuple[str, list[str]]:
    frames_list = parse_disassembly(disassembly)
    stacks = parse_task_stacks(app_source)
    frames, graph, external_calls = build_graph(frames_list)
    roots = {
        task: find_task_entry(frames_list, task, function)
        for task, function in TASKS.items()
    }
    memo: dict[int, tuple[int, tuple[int, ...]]] = {}
    errors: list[str] = []
    for address in graph:
        maximum_path(address, frames, graph, memo, [], errors)

    lines = [f"ELF SHA256 prefix: {elf_sha256[:9]}"]
    lines.append(f"関数枠上限: gwapp:: / grokwatch:: の各関数 {FRAME_LIMIT:,} B")
    internal = [frame for frame in frames_list if is_internal(frame.name)]
    largest = max(internal, key=lambda frame: int(frame.size or 0))
    lines.append(f"最大関数枠: {largest.size:,} B  {largest.name}")
    vfprintf = [frame for frame in frames_list if frame.name.endswith("_vfprintf_r")]
    if vfprintf:
        max_vfprintf = max(vfprintf, key=lambda frame: int(frame.size or 0))
        size = "枠を読み取れず" if max_vfprintf.size is None else f"{max_vfprintf.size:,} B"
        lines.append(f"_vfprintf_r の objdump 実測枠: {size}")

    lines.append("タスク | 最悪経路（関数枠） | 関数枠合計 + 余裕 = 使用見積もり / タスク枠")
    for task, function in TASKS.items():
        root = roots[task]
        measured, path = memo[root.address]
        reserve = RESERVES[task]
        total = measured + reserve.size
        stack_size = stacks[task].size
        path_text = " -> ".join(
            f"{frames[address].name}[{frames[address].size} B]" for address in path
        )
        lines.append(
            f"{task} | {path_text} | {measured:,} + {reserve.size:,} = "
            f"{total:,} / {stack_size:,} B"
        )
        calls = reachable_external_calls(root.address, graph, external_calls)
        measured_external = [(name, size) for name, size in calls if size is not None]
        if measured_external:
            external_name, external_size = max(measured_external, key=lambda item: item[1])
            lines.append(
                f"{task} 外部直接呼び出しの最大実測枠: {external_size:,} B  {external_name}"
            )
            if external_size > reserve.size:
                errors.append(
                    f"{task}: 外部直接呼び出し枠 {external_size:,} B > "
                    f"余裕 {reserve.size:,} B"
                )
        else:
            lines.append(f"{task} 外部直接呼び出しの枠: objdump で測定できる対象なし")
        lines.append(f"{task} 余裕の根拠: {reserve.basis}")
        if total > stack_size:
            errors.append(
                f"{task}: {measured:,} B + 余裕 {reserve.size:,} B = {total:,} B "
                f"> タスク枠 {stack_size:,} B"
            )

    for frame in internal:
        size = int(frame.size or 0)
        if size > FRAME_LIMIT:
            errors.append(f"{frame.name}: {size:,} B > {FRAME_LIMIT:,} B")
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
    parser.add_argument(
        "elf", nargs="?", type=Path, default=REPO_ROOT / "firmware/build/grokwatch.elf"
    )
    parser.add_argument("--objdump", help="xtensa-esp32s3-elf-objdump の実行ファイル")
    parser.add_argument("--disassembly-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--app-main", type=Path, default=REPO_ROOT / "firmware/main/app_main.cpp")
    args = parser.parse_args()
    digest = ""
    try:
        digest = hashlib.sha256(args.elf.read_bytes()).hexdigest()
        report, errors = check_stack(
            read_disassembly(args), args.app_main.read_text(), digest
        )
    except (CheckError, OSError) as error:
        if digest:
            print(f"ELF SHA256 prefix: {digest[:9]}", flush=True)
        print(f"スタック検査エラー: {error}", file=sys.stderr)
        return 1
    print(report, flush=True)
    if errors:
        print("検査失敗:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("スタック検査: 合格")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
