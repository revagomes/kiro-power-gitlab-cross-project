"""Regression tests for error handling and edge cases (adversarial review).

Findings addressed:
- C1: _glab_api must surface JSON parse failures / empty stdout with context,
  not an opaque JSONDecodeError.
- C2: glab-not-installed (FileNotFoundError) and timeout (TimeoutExpired) must
  become clear RuntimeErrors, not raw tracebacks.
- C3: gitlab_mr_status must still return gracefully when the approvals endpoint
  returns unparseable output (not only on non-zero exit).
- C5: gitlab_list_mrs must clamp `limit` to a valid GitLab per_page range.
- C8: draft prefixing must not double-mark titles already flagged as draft/WIP.
- Q5: _format_mr must tolerate an explicit null author.
- Q1: merge tool must include merge_when_pipeline_succeeds in its fields.

All tests mock the subprocess boundary; no real `glab` runs.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest


def _run_returning(stdout, returncode=0, stderr=""):
    calls = []

    def run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

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


# ── C1: JSON / empty output handling ─────────────────────────────────────────

def test_glab_api_raises_context_on_invalid_json(gl, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_returning("not json at all"))
    with pytest.raises(RuntimeError) as exc:
        gl._glab_api("projects/1/merge_requests")
    msg = str(exc.value)
    assert "projects/1/merge_requests" in msg
    # It must not leak a raw JSONDecodeError type name only.
    assert "non-JSON" in msg or "JSON" in msg


def test_glab_api_raises_context_on_empty_stdout(gl, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_returning("   "))
    with pytest.raises(RuntimeError) as exc:
        gl._glab_api("projects/1/x")
    assert "projects/1/x" in str(exc.value)


# ── C2: missing glab / timeout ───────────────────────────────────────────────

def test_glab_api_missing_binary_gives_clear_message(gl, monkeypatch):
    def run(cmd, capture_output=True, text=True, timeout=None):
        raise FileNotFoundError(2, "No such file or directory", "glab")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError) as exc:
        gl._glab_api("projects/1/x")
    assert "glab" in str(exc.value).lower()
    assert "not found" in str(exc.value).lower() or "install" in str(exc.value).lower()


def test_glab_api_timeout_gives_clear_message(gl, monkeypatch):
    def run(cmd, capture_output=True, text=True, timeout=None):
        raise subprocess.TimeoutExpired(cmd, timeout or 30)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError) as exc:
        gl._glab_api("projects/1/x")
    assert "timed out" in str(exc.value).lower() or "timeout" in str(exc.value).lower()


# ── C3: approvals endpoint returns garbage ───────────────────────────────────

def test_mr_status_survives_unparseable_approvals(gl, monkeypatch):
    def run(cmd, capture_output=True, text=True, timeout=None):
        endpoint = cmd[2] if len(cmd) > 2 else ""
        if endpoint.endswith("/approvals"):
            # Exit 0 but non-JSON body — must not crash the whole status call.
            return SimpleNamespace(returncode=0, stdout="<html>oops</html>", stderr="")
        return SimpleNamespace(returncode=0, stdout=MR_JSON, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    result = gl.gitlab_mr_status(720)
    assert result["iid"] == 720
    assert result["approved"] is None
    assert "approvals_note" in result


# ── C5: limit clamping ───────────────────────────────────────────────────────

def test_list_mrs_clamps_limit_above_max(gl, monkeypatch):
    fake = _run_returning(json.dumps([]))
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_list_mrs(limit=100000)
    endpoint = fake.calls[-1][2]
    assert "per_page=100&" in endpoint or endpoint.endswith("per_page=100")


def test_list_mrs_clamps_non_positive_limit(gl, monkeypatch):
    fake = _run_returning(json.dumps([]))
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_list_mrs(limit=0)
    endpoint = fake.calls[-1][2]
    assert "per_page=1" in endpoint


# ── C8: draft double-prefix ──────────────────────────────────────────────────

def test_create_cross_mr_does_not_double_prefix_lowercase_draft(gl, monkeypatch):
    fake = _run_returning(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_create_cross_mr(branch="b", title="draft: already", draft=True)
    joined = " ".join(fake.calls[-1])
    assert "Draft: draft: already" not in joined


def test_create_cross_mr_does_not_prefix_wip_title(gl, monkeypatch):
    fake = _run_returning(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_create_cross_mr(branch="b", title="WIP: work", draft=True)
    joined = " ".join(fake.calls[-1])
    assert "Draft: WIP: work" not in joined


# ── Q5: null author ──────────────────────────────────────────────────────────

def test_format_mr_tolerates_null_author(gl):
    mr = gl._format_mr({"iid": 1, "author": None})
    assert mr["author"] is None


# ── Q1: merge flag present ───────────────────────────────────────────────────

def test_merge_mr_includes_pipeline_flag(gl, monkeypatch):
    fake = _run_returning(MR_JSON)
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_merge_mr(720, merge_when_pipeline_succeeds=True)
    joined = " ".join(fake.calls[-1])
    assert "merge_when_pipeline_succeeds=true" in joined


# ── C6: numeric env validation ───────────────────────────────────────────────

def test_required_numeric_env_rejects_non_numeric(gl, monkeypatch):
    monkeypatch.setenv("GITLAB_TARGET_ID", "not-a-number")
    with pytest.raises(ValueError) as exc:
        gl._required_numeric_env("GITLAB_TARGET_ID")
    assert "GITLAB_TARGET_ID" in str(exc.value)


def test_required_numeric_env_accepts_numeric(gl, monkeypatch):
    monkeypatch.setenv("GITLAB_TARGET_ID", "1234")
    assert gl._required_numeric_env("GITLAB_TARGET_ID") == "1234"


def test_required_env_rejects_unset(gl, monkeypatch):
    monkeypatch.delenv("GITLAB_SOURCE_PROJECT", raising=False)
    with pytest.raises(ValueError) as exc:
        gl._required_env("GITLAB_SOURCE_PROJECT")
    assert "GITLAB_SOURCE_PROJECT" in str(exc.value)
    assert "required" in str(exc.value).lower()


# ── approvals happy path ─────────────────────────────────────────────────────

def test_mr_status_reports_approvals_when_available(gl, monkeypatch):
    approvals_json = json.dumps({
        "approved": True,
        "approvals_required": 2,
        "approvals_left": 0,
        "approved_by": [{"user": {"username": "carol"}}],
    })

    def run(cmd, capture_output=True, text=True, timeout=None):
        endpoint = cmd[2] if len(cmd) > 2 else ""
        if endpoint.endswith("/approvals"):
            return SimpleNamespace(returncode=0, stdout=approvals_json, stderr="")
        return SimpleNamespace(returncode=0, stdout=MR_JSON, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    result = gl.gitlab_mr_status(720)
    assert result["approved"] is True
    assert result["approvals_required"] == 2
    assert result["approved_by"] == ["carol"]
