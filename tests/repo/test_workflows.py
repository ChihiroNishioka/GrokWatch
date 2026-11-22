import re

from yaml import BaseLoader, load


# タグを付けるジョブだけが contents: write を持つ。
WRITE_JOBS = {("release-tag.yml", "tag")}


def test_permissions_and_pinning(repo_root):
    files = sorted((repo_root / ".github/workflows").glob("*.y*ml"))
    assert {file.name for file in files} >= {"ci.yml", "secrets-pii.yml", "release-tag.yml"}
    for path in files:
        workflow = load(path.read_text(), Loader=BaseLoader)
        assert workflow["permissions"] == {"contents": "read"}, path
        assert "pull_request_target" not in workflow["on"], path
        for name, job in workflow["jobs"].items():
            expected = "write" if (path.name, name) in WRITE_JOBS else "read"
            assert job.get("permissions", workflow["permissions"]) == {"contents": expected}, path
            for entry in [job, *job.get("steps", [])]:
                if "uses" in entry:
                    assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", entry["uses"]), path
                assert "upload-artifact" not in entry.get("uses", ""), path


def test_release_tag_runs_only_after_successful_main_push(repo_root):
    workflow = load((repo_root / ".github/workflows/release-tag.yml").read_text(), Loader=BaseLoader)
    assert set(workflow["on"]) == {"workflow_run"}
    trigger = workflow["on"]["workflow_run"]
    assert trigger["workflows"] == ["ビルドとテスト"]
    assert trigger["types"] == ["completed"] and trigger["branches"] == ["main"]
    ci = load((repo_root / ".github/workflows/ci.yml").read_text(), Loader=BaseLoader)
    assert ci["name"] == "ビルドとテスト"
    job = workflow["jobs"]["tag"]
    assert "conclusion == 'success'" in job["if"] and "event == 'push'" in job["if"]
    checkout = job["steps"][0]
    assert checkout["with"]["persist-credentials"] == "false"
    assert checkout["with"]["ref"] == "${{ github.event.workflow_run.head_sha }}"
