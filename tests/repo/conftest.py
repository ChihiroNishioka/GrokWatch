from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    return tmp_path
