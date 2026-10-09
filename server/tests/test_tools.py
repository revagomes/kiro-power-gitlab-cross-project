"""Behavioral tests for the GitLab cross-project MCP tools.

All tests mock subprocess.run so no real `glab` process runs.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest


def _fake_run(stdout, returncode=0, stderr=""):
    """Build a fake subprocess.run that records the command and returns stdout."""
    calls = []

    def run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd)
        return SimpleNamespace(
            returncode=returncode, stdout=stdout, stderr=stderr
        )

    run.calls = calls
    return run


MR_JSON = json.dumps({
    "iid": 720,
    "title": "Fix cache",
    "state": "opened",
    "web_url": "https://gitlab.example.com/x/-/merge_requests/720",
    "source_branch": "feature/x",
    "target_branch": "master",
    "author": {"username": "alice"},
    "labels": ["ai::review"],
    "head_pipeline": {"status": "success"},
})


# ── helpers ──────────────────────────────────────────────────────────────────

def test_encode_project_escapes_slashes(gl):
    assert gl._encode_project("group/sub/proj") == "group%2Fsub%2Fproj"


def test_format_mr_extracts_fields(gl):
    mr = gl._format_mr(json.loads(MR_JSON))
    assert mr["iid"] == 720
    assert mr["author"] == "alice"
    assert mr["pipeline_status"] == "success"


def test_glab_api_raises_on_nonzero_exit(gl, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("", returncode=1, stderr="boom"))
    with pytest.raises(RuntimeError) as exc:
        gl._glab_api("projects/1/merge_requests")
    assert "boom" in str(exc.value)


# ── gitlab_create_cross_mr ───────────────────────────────────────────────────

def test_create_cross_mr_builds_expected_command(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)

    result = gl.gitlab_create_cross_mr(
        branch="feature/x", title="Fix cache", description="details"
    )

    cmd = fake.calls[-1]
    assert cmd[0:2] == ["glab", "api"]
    assert "--method" in cmd and "POST" in cmd
    # target_project_id must be the configured target id (cross-project MR).
    joined = " ".join(cmd)
    assert f"target_project_id={gl.TARGET_ID}" in joined
    assert "source_branch=feature/x" in joined
    assert result["iid"] == 720


def test_create_cross_mr_draft_prefixes_title(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_create_cross_mr(branch="b", title="Add x", draft=True)
    joined = " ".join(fake.calls[-1])
    assert "title=Draft: Add x" in joined


def test_create_cross_mr_defaults_labels(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_create_cross_mr(branch="b", title="t")
    joined = " ".join(fake.calls[-1])
    assert f"labels={gl.DEFAULT_LABELS}" in joined


# ── gitlab_list_mrs ──────────────────────────────────────────────────────────

def test_list_mrs_returns_formatted(gl, monkeypatch):
    fake = _fake_run(json.dumps([json.loads(MR_JSON)]))
    monkeypatch.setattr(subprocess, "run", fake)
    rows = gl.gitlab_list_mrs(state="opened")
    assert isinstance(rows, list) and rows[0]["iid"] == 720
    # queries the TARGET project
    assert gl._encode_project(gl.TARGET_PROJECT) in " ".join(fake.calls[-1])


# ── gitlab_mr_status ─────────────────────────────────────────────────────────

def test_mr_status_handles_missing_approvals(gl, monkeypatch):
    """When the approvals endpoint 404s, status still returns with a note."""
    calls = []

    def run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd)
        # The endpoint is the argument at index 2 (glab api <endpoint> --method GET).
        endpoint = cmd[2] if len(cmd) > 2 else ""
        if endpoint.endswith("/approvals"):
            return SimpleNamespace(returncode=1, stdout="", stderr="404")
        return SimpleNamespace(returncode=0, stdout=MR_JSON, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    result = gl.gitlab_mr_status(720)
    assert result["iid"] == 720
    assert result["approved"] is None
    assert "approvals_note" in result


# ── gitlab_mr_add_comment ────────────────────────────────────────────────────

def test_add_comment_posts_body(gl, monkeypatch):
    fake = _fake_run(json.dumps({
        "id": 5, "author": {"username": "bob"}, "body": "hello",
        "created_at": "2026-01-01",
    }))
    monkeypatch.setattr(subprocess, "run", fake)
    result = gl.gitlab_mr_add_comment(720, "hello")
    assert result["id"] == 5
    joined = " ".join(fake.calls[-1])
    assert "body=hello" in joined


# ── gitlab_update_mr ─────────────────────────────────────────────────────────

def test_update_mr_builds_put_with_changed_fields(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)

    result = gl.gitlab_update_mr(720, description="new body", labels="ai::reviewed")

    cmd = fake.calls[-1]
    joined = " ".join(cmd)
    assert "--method" in cmd and "PUT" in cmd
    assert "/merge_requests/720" in joined
    assert "description=new body" in joined
    assert "labels=ai::reviewed" in joined
    # targets the upstream (TARGET) project
    assert gl._encode_project(gl.TARGET_PROJECT) in joined
    assert result["iid"] == 720


def test_update_mr_only_sends_provided_fields(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_update_mr(720, title="New title")
    joined = " ".join(fake.calls[-1])
    assert "title=New title" in joined
    # description/labels/target_branch not touched
    assert "description=" not in joined
    assert "labels=" not in joined
    assert "target_branch=" not in joined


def test_update_mr_requires_a_field(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(ValueError) as exc:
        gl.gitlab_update_mr(720)
    assert "at least one field" in str(exc.value)
    # no glab call made
    assert fake.calls == []


def test_update_mr_draft_true_prefixes_given_title(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_update_mr(720, title="Add x", draft=True)
    joined = " ".join(fake.calls[-1])
    assert "title=Draft: Add x" in joined


def test_update_mr_draft_false_strips_marker(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_update_mr(720, title="Draft: Add x", draft=False)
    joined = " ".join(fake.calls[-1])
    assert "title=Add x" in joined
    assert "Draft:" not in joined


def test_update_mr_draft_without_title_fetches_current(gl, monkeypatch):
    """draft toggle with no title given fetches the current MR title first."""
    calls = []

    def run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd)
        endpoint = cmd[2] if len(cmd) > 2 else ""
        method = cmd[cmd.index("--method") + 1] if "--method" in cmd else "GET"
        # The GET to fetch current title returns an un-drafted title.
        if method == "GET":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({**json.loads(MR_JSON), "title": "Add x"}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout=MR_JSON, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    gl.gitlab_update_mr(720, draft=True)
    # Last call is the PUT carrying the drafted title.
    joined = " ".join(calls[-1])
    assert "--method" in calls[-1] and "PUT" in calls[-1]
    assert "title=Draft: Add x" in joined


def test_update_mr_undraft_marker_only_title_raises(gl, monkeypatch):
    """Un-drafting a title that is only a marker must fail loudly, not no-op.

    Previously this collapsed to an empty title, the field was dropped, and the
    un-draft silently did nothing (or raised the generic 'requires a field').
    """
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(ValueError) as exc:
        gl.gitlab_update_mr(720, title="Draft:", draft=False)
    assert "usable title" in str(exc.value)
    # No PUT should have been issued.
    assert fake.calls == []


def test_update_mr_draft_alone_fetches_and_toggles(gl, monkeypatch):
    """Passing draft alone (no other field) must update the MR, not error."""
    calls = []

    def run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd)
        method = cmd[cmd.index("--method") + 1] if "--method" in cmd else "GET"
        if method == "GET":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({**json.loads(MR_JSON), "title": "Draft: Add x"}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout=MR_JSON, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    gl.gitlab_update_mr(720, draft=False)
    joined = " ".join(calls[-1])
    assert "--method" in calls[-1] and "PUT" in calls[-1]
    assert "title=Add x" in joined
    assert "Draft:" not in joined


def test_update_mr_sends_target_branch(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_update_mr(720, target_branch="release/2.0")
    joined = " ".join(fake.calls[-1])
    assert "--method" in fake.calls[-1] and "PUT" in fake.calls[-1]
    assert "target_branch=release/2.0" in joined


# ── gitlab_merge_mr ──────────────────────────────────────────────────────────

def test_merge_mr_builds_put_with_flags(gl, monkeypatch):
    fake = _fake_run(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_merge_mr(720, squash=True, remove_source_branch=True)
    cmd = fake.calls[-1]
    joined = " ".join(cmd)
    assert "--method" in cmd and "PUT" in cmd
    assert "/merge_requests/720/merge" in joined
    assert "squash=true" in joined
    assert "should_remove_source_branch=true" in joined
