import importlib.util
import shutil

import pytest


def _module(repo_root):
    spec = importlib.util.spec_from_file_location("release_version", repo_root / "scripts/release_version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy(repo_root, tmp_path):
    for name in ("firmware/CMakeLists.txt", "gateway/pyproject.toml", "bridge/pyproject.toml"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(repo_root / name, tmp_path / name)
    return tmp_path


def test_repository_versions_agree(repo_root):
    module = _module(repo_root)
    assert module.SEMVER.fullmatch(module.release_version(repo_root))


def test_mismatched_versions_are_rejected(repo_root, tmp_path):
    module = _module(repo_root)
    root = _copy(repo_root, tmp_path)
    path = root / "bridge/pyproject.toml"
    text = path.read_text()
    current = module.release_version(repo_root)
    path.write_text(text.replace(f'version = "{current}"', 'version = "9.9.9"'))
    with pytest.raises(ValueError, match="一致しません"):
        module.release_version(root)


def test_non_semver_is_rejected(repo_root, tmp_path):
    module = _module(repo_root)
    root = _copy(repo_root, tmp_path)
    current = module.release_version(repo_root)
    for name in module.SOURCES:
        path = root / name
        path.write_text(path.read_text().replace(f'"{current}"', '"1.1"'))
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        module.release_version(root)
