"""Security regression tests (Lagune-style review).

Findings addressed:
- Query-parameter injection in gitlab_list_mrs: `state` and `author` were
  interpolated into the query string without URL-encoding, unlike `branch`
  and `labels`. A value containing `&`, `#`, or `=` could inject or break
  query parameters on the API request. (No shell injection: the transport is
  a list-form `glab api` subprocess, never a shell.)

Invariant guarded: every user-supplied query value is URL-encoded before it
reaches the endpoint string.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest


def _recorder():
    calls = []

    def run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout=json.dumps([]), stderr="")

    run.calls = calls
    return run


def test_list_mrs_encodes_state(gl, monkeypatch):
    fake = _recorder()
    monkeypatch.setattr(subprocess, "run", fake)
    # A malicious state trying to inject an extra query parameter.
    gl.gitlab_list_mrs(state="opened&access_level=50")
    endpoint = fake.calls[-1][2]
    # The raw '&' must NOT appear as a parameter separator injected by the value;
    # it must be percent-encoded (%26) so it stays part of the state value.
    assert "access_level=50" not in endpoint.split("state=", 1)[1].split("&")[0] or "%26" in endpoint
    assert "&access_level=50" not in endpoint


def test_list_mrs_encodes_author(gl, monkeypatch):
    fake = _recorder()
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_list_mrs(author="alice&foo=bar")
    endpoint = fake.calls[-1][2]
    # The injected '&foo=bar' must be encoded, not a live separator.
    assert "&foo=bar" not in endpoint
    assert "%26foo" in endpoint or "foo%3Dbar" in endpoint


def test_list_mrs_normal_values_still_work(gl, monkeypatch):
    fake = _recorder()
    monkeypatch.setattr(subprocess, "run", fake)
    gl.gitlab_list_mrs(state="opened", author="alice", branch="feature/x")
    endpoint = fake.calls[-1][2]
    assert "state=opened" in endpoint
    assert "author_username=alice" in endpoint
