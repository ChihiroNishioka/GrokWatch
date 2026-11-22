#!/usr/bin/env python3
"""Print the release version after checking that firmware, gateway and bridge agree."""

from __future__ import annotations

from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
SOURCES = {
    "firmware/CMakeLists.txt": re.compile(r'^set\(PROJECT_VER "([^"]+)"\)$', re.MULTILINE),
    "gateway/pyproject.toml": re.compile(r'^version = "([^"]+)"$', re.MULTILINE),
    "bridge/pyproject.toml": re.compile(r'^version = "([^"]+)"$', re.MULTILINE),
}


def versions(root: Path = REPO_ROOT) -> dict[str, str]:
    found = {}
    for name, pattern in SOURCES.items():
        matches = pattern.findall((root / name).read_text(encoding="utf-8"))
        if len(matches) != 1:
            raise ValueError(f"{name}: 版番号を一つに特定できません")
        found[name] = matches[0]
    return found


def release_version(root: Path = REPO_ROOT) -> str:
    found = versions(root)
    distinct = set(found.values())
    if len(distinct) != 1:
        detail = ", ".join(f"{name}={value}" for name, value in found.items())
        raise ValueError(f"版番号が一致しません: {detail}")
    version = distinct.pop()
    if not SEMVER.fullmatch(version):
        raise ValueError(f"版番号が MAJOR.MINOR.PATCH ではありません: {version}")
    return version


def main() -> int:
    try:
        print(release_version())
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
