import re
import subprocess
import tomllib


def test_asset_allowlist(repo_root, git_repo):
    approved = {
        ".github/workflows/ci.yml", "bridge/src/main.py", "firmware/CMakeLists.txt",
        "firmware/main/Kconfig.projbuild", "firmware/main/main.cpp", "firmware/main/board.hpp",
        "firmware/main/driver.h", "firmware/main/driver.c", "firmware/check.cmake",
        "firmware/partitions.csv", "firmware/sdkconfig.defaults", "firmware/dependencies.lock",
        "README.md", "pyproject.toml", "scripts/check.sh", "tests/fixture.json",
        "LICENSE", ".gitignore", "config/.env.example",
    }
    rejected = {"assets/example.png", "assets/example.jpg", "assets/example.mp4", "other.dat", "notes.txt"}
    config = tomllib.loads((repo_root / ".gitleaks.toml").read_text())
    rule = next(rule for rule in config["rules"] if rule["id"] == "grokwatch-file-format")
    allowed_paths = [regex for allowlist in rule["allowlists"] for regex in allowlist["paths"]]
    for name in approved | rejected:
        assert bool(any(re.search(regex, name) for regex in allowed_paths)) == (name in approved), name
        path = git_repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n")

    def stage(names):
        subprocess.run(["git", "add", "--force", "--", *sorted(names)], cwd=git_repo, check=True)

    def scan():
        return subprocess.run(
            ["bash", repo_root / "scripts/check_pii.sh"], cwd=git_repo, capture_output=True, text=True,
        )

    stage(approved)
    assert scan().returncode == 0
    stage(rejected)
    result = scan()
    assert result.returncode == 1
    for name in rejected:
        assert name in result.stderr
