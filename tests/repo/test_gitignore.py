import subprocess


def test_local_files_ignored(repo_root):
    ignored = [
        ".env", "gateway/.env", "firmware/sdkconfig.local.defaults", "firmware/sdkconfig",
        "firmware/build/example", "firmware/managed_components/example", "build-host/example", "build/example",
    ]
    checked = subprocess.check_output(
        ["git", "check-ignore", "--no-index", *ignored], cwd=repo_root, text=True,
    ).splitlines()
    assert checked == ignored
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--ignored", "--exclude-standard"], cwd=repo_root, text=True,
    )
    assert tracked == ""
    for lock in ("firmware/dependencies.lock", "uv.lock"):
        assert (repo_root / lock).is_file()
        assert subprocess.run(["git", "check-ignore", "--no-index", lock], cwd=repo_root).returncode == 1
