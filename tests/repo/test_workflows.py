import re

from yaml import BaseLoader, load


def test_permissions_and_pinning(repo_root):
    files = sorted((repo_root / ".github/workflows").glob("*.y*ml"))
    assert {file.name for file in files} >= {"ci.yml", "secrets-pii.yml"}
    for path in files:
        workflow = load(path.read_text(), Loader=BaseLoader)
        assert workflow["permissions"] == {"contents": "read"}, path
        assert "pull_request_target" not in workflow["on"], path
        for job in workflow["jobs"].values():
            assert job.get("permissions", workflow["permissions"]) == {"contents": "read"}, path
            for entry in [job, *job.get("steps", [])]:
                if "uses" in entry:
                    assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", entry["uses"]), path
                assert "upload-artifact" not in entry.get("uses", ""), path
