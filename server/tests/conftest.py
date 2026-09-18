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


@pytest.fixture()
def gl():
    """Import a fresh copy of the server module."""
    if "gitlab_cross_project_mcp" in sys.modules:
        return importlib.reload(sys.modules["gitlab_cross_project_mcp"])
    return importlib.import_module("gitlab_cross_project_mcp")
