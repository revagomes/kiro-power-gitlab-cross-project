"""Pytest fixtures for the GitLab cross-project MCP server.

The module imports without side effects (no .env bootstrap, config is read from
the environment at import). Tests mock the CLI boundary at ``subprocess.run`` so
no real ``glab`` invocation or network call happens.
"""

import importlib
import sys
import pathlib

import pytest

_SERVER_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))


# The server requires project configuration via env vars at import time and
# ships no default project references. Provide synthetic test values so the
# module imports cleanly without referencing any real project.
_TEST_ENV = {
    "GITLAB_SOURCE_PROJECT": "test-group/source-project",
    "GITLAB_TARGET_PROJECT": "test-group/target-project",
    "GITLAB_SOURCE_ID": "1001",
    "GITLAB_TARGET_ID": "2002",
    "GITLAB_DEFAULT_LABELS": "ai::review",
}


@pytest.fixture(autouse=True)
def _server_env(monkeypatch):
    """Ensure required config env vars are set before the module imports."""
    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture()
def gl():
    """Import a fresh copy of the server module."""
    if "gitlab_cross_project_mcp" in sys.modules:
        return importlib.reload(sys.modules["gitlab_cross_project_mcp"])
    return importlib.import_module("gitlab_cross_project_mcp")
