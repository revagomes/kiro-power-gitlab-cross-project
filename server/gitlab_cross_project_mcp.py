#!/usr/bin/env python3
"""
GitLab Cross-Project MCP Server.

Copyright (C) 2026 Renato Vasconcellos Gomes

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

Exposes GitLab operations that `glab` CLI doesn't support natively,
primarily cross-project merge request management.

Uses `glab api` as the transport layer — inherits authentication from
the user's existing glab configuration. No separate tokens needed.

Configuration via environment variables (all project settings are required;
the server ships no default project references):
    GITLAB_SOURCE_PROJECT  — Source project path, e.g. your-group/source-project (required)
    GITLAB_TARGET_PROJECT  — Target project path, e.g. your-group/target-project (required)
    GITLAB_SOURCE_ID       — Source project numeric ID (required)
    GITLAB_TARGET_ID       — Target project numeric ID (required)
    GITLAB_DEFAULT_LABELS  — Comma-separated default MR labels (default: ai::review)

Run via:
    uvx --from fastmcp fastmcp run server/gitlab_cross_project_mcp.py
"""

import json
import os
import re
import subprocess
import urllib.parse

from fastmcp import FastMCP

# ── Configuration ──────────────────────────────────────────────────────────────


def _required_env(name: str) -> str:
    """Read a required env var, failing fast with a clear message if unset."""
    value = os.environ.get(name)
    if not value:
        raise ValueError(
            f"{name} is required. Set it in your mcp.json env block "
            f"(this server ships no default project references)."
        )
    return value


def _required_numeric_env(name: str) -> str:
    """Read a required numeric project-ID env var, failing fast if invalid."""
    value = _required_env(name)
    if not value.isdigit():
        raise ValueError(
            f"{name} must be a numeric project ID, got {value!r}."
        )
    return value


SOURCE_PROJECT = _required_env("GITLAB_SOURCE_PROJECT")
TARGET_PROJECT = _required_env("GITLAB_TARGET_PROJECT")
SOURCE_ID = _required_numeric_env("GITLAB_SOURCE_ID")
TARGET_ID = _required_numeric_env("GITLAB_TARGET_ID")
DEFAULT_LABELS = os.environ.get("GITLAB_DEFAULT_LABELS", "ai::review")

# GitLab's draft-title markers (see GitLab MR draft detection).
_DRAFT_MARKER = re.compile(r"^\s*(\[draft\]|\(draft\)|draft:|\[wip\]|wip:)", re.IGNORECASE)

mcp = FastMCP(
    "GitLab Cross-Project",
    instructions=(
        "GitLab MCP server for cross-project merge request operations. "
        "Wraps `glab api` for operations that glab CLI doesn't support "
        "natively, such as cross-project MR creation. "
        "Inherits auth from the user's glab configuration."
    ),
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _glab_api(
    endpoint: str,
    method: str = "GET",
    fields: dict | None = None,
) -> dict | list:
    """Call GitLab REST API via glab and return parsed JSON."""
    cmd = ["glab", "api", endpoint, "--method", method]
    for key, value in (fields or {}).items():
        cmd.extend(["-f", f"{key}={value}"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "glab CLI not found on PATH. Install glab and run 'glab auth login'."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"glab api timed out after 30s for {endpoint!r}."
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"glab api failed (exit {result.returncode}): {stderr}")

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"glab api returned an empty response for {endpoint!r}."
        )
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"glab api returned non-JSON output for {endpoint!r}: {stdout[:200]!r}"
        ) from exc


def _encode_project(project_path: str) -> str:
    """URL-encode a project path for the GitLab API."""
    return urllib.parse.quote(project_path, safe="")


def _format_mr(mr: dict) -> dict:
    """Extract the useful fields from a raw MR API response."""
    return {
        "iid": mr.get("iid"),
        "title": mr.get("title"),
        "state": mr.get("state"),
        "url": mr.get("web_url"),
        "source_branch": mr.get("source_branch"),
        "target_branch": mr.get("target_branch"),
        "author": (mr.get("author") or {}).get("username"),
        "created_at": mr.get("created_at"),
        "updated_at": mr.get("updated_at"),
        "merge_status": mr.get("merge_status"),
        "draft": mr.get("draft"),
        "labels": mr.get("labels", []),
        "pipeline_status": (mr.get("head_pipeline") or {}).get("status"),
    }


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def gitlab_create_cross_mr(
    branch: str,
    title: str,
    description: str = "",
    target_branch: str = "master",
    labels: str = "",
    draft: bool = False,
) -> dict:
    """Create a cross-project merge request from the dev fork to the upstream reference repo.

    Args:
        branch: Source branch name (e.g. feature/PROJ-123-cache-fix).
        title: MR title. Keep under 70 chars. Use description for details.
        description: MR description in Markdown. Supports GitLab flavored markdown.
        target_branch: Target branch on the upstream repo. Defaults to 'master'.
        labels: Comma-separated labels. Defaults to the server's GITLAB_DEFAULT_LABELS.
        draft: If True, creates the MR as a draft/WIP.
    """
    effective_labels = labels if labels else DEFAULT_LABELS
    if draft and not _DRAFT_MARKER.match(title):
        title = f"Draft: {title}"

    endpoint = f"projects/{_encode_project(SOURCE_PROJECT)}/merge_requests"
    fields = {
        "source_branch": branch,
        "target_branch": target_branch,
        "target_project_id": TARGET_ID,
        "title": title,
        "labels": effective_labels,
    }
    if description:
        fields["description"] = description

    data = _glab_api(endpoint, method="POST", fields=fields)
    return _format_mr(data)


@mcp.tool()
def gitlab_list_mrs(
    state: str = "opened",
    branch: str = "",
    author: str = "",
    labels: str = "",
    limit: int = 20,
) -> list[dict]:
    """List merge requests on the upstream reference repo.

    Args:
        state: Filter by state: opened, closed, merged, all. Defaults to 'opened'.
        branch: Filter by source branch name. Optional.
        author: Filter by author username. Optional.
        labels: Comma-separated labels to filter by. Optional.
        limit: Maximum number of results. Defaults to 20.
    """
    endpoint = f"projects/{_encode_project(TARGET_PROJECT)}/merge_requests"
    per_page = max(1, min(int(limit), 100))
    params = [
        f"state={urllib.parse.quote(state, safe='')}",
        f"per_page={per_page}",
    ]
    if branch:
        params.append(f"source_branch={urllib.parse.quote(branch, safe='')}")
    if author:
        params.append(
            f"author_username={urllib.parse.quote(author, safe='')}"
        )
    if labels:
        params.append(f"labels={urllib.parse.quote(labels, safe='')}")

    full_endpoint = f"{endpoint}?{'&'.join(params)}"
    data = _glab_api(full_endpoint)

    return [_format_mr(mr) for mr in data]


@mcp.tool()
def gitlab_mr_status(mr_iid: int) -> dict:
    """Get detailed status of a merge request on the upstream reference repo.

    Returns MR metadata, pipeline status, approvals, and merge readiness.

    Args:
        mr_iid: The MR IID (the number shown in the UI, e.g. 720).
    """
    endpoint = f"projects/{_encode_project(TARGET_PROJECT)}/merge_requests/{mr_iid}"
    data = _glab_api(endpoint)

    result = _format_mr(data)
    # Add extra detail fields not in the list view.
    result["has_conflicts"] = data.get("has_conflicts", False)
    result["blocking_discussions_resolved"] = data.get(
        "blocking_discussions_resolved", True
    )
    result["changes_count"] = data.get("changes_count")
    result["user_notes_count"] = data.get("user_notes_count", 0)
    result["upvotes"] = data.get("upvotes", 0)
    result["downvotes"] = data.get("downvotes", 0)

    # Fetch approvals separately (may not be available on all tiers).
    try:
        approvals_endpoint = f"{endpoint}/approvals"
        approvals = _glab_api(approvals_endpoint)
        result["approved"] = approvals.get("approved", False)
        result["approvals_required"] = approvals.get("approvals_required", 0)
        result["approvals_left"] = approvals.get("approvals_left", 0)
        result["approved_by"] = [
            a.get("user", {}).get("username")
            for a in approvals.get("approved_by", [])
        ]
    except (RuntimeError, json.JSONDecodeError):
        result["approved"] = None
        result["approvals_note"] = "Approvals API not available"

    return result


@mcp.tool()
def gitlab_merge_mr(
    mr_iid: int,
    merge_when_pipeline_succeeds: bool = True,
    squash: bool = True,
    remove_source_branch: bool = True,
) -> dict:
    """Merge an MR on the upstream reference repo.

    Args:
        mr_iid: The MR IID to merge (e.g. 720).
        merge_when_pipeline_succeeds: Wait for pipeline to pass before merging. Defaults to True.
        squash: Squash commits on merge. Defaults to True.
        remove_source_branch: Remove the source branch after merge. Defaults to True.
    """
    endpoint = (
        f"projects/{_encode_project(TARGET_PROJECT)}"
        f"/merge_requests/{mr_iid}/merge"
    )
    fields = {
        "merge_when_pipeline_succeeds": str(merge_when_pipeline_succeeds).lower(),
        "squash": str(squash).lower(),
        "should_remove_source_branch": str(remove_source_branch).lower(),
    }

    data = _glab_api(endpoint, method="PUT", fields=fields)
    return _format_mr(data)


@mcp.tool()
def gitlab_update_mr(
    mr_iid: int,
    title: str = "",
    description: str = "",
    labels: str = "",
    target_branch: str = "",
    draft: bool | None = None,
) -> dict:
    """Update an existing merge request on the upstream reference repo.

    Edits MR metadata in place — the title, description/body, labels, target
    branch, or draft state. Only the fields you pass are changed; omitted fields
    are left untouched. At least one changeable field must be provided.

    Note on labels: GitLab replaces the full label set with the value given, so
    pass the complete comma-separated list you want the MR to end up with (not
    just the additions).

    Args:
        mr_iid: The MR IID (the number shown in the UI, e.g. 720).
        title: New MR title. Optional. If 'draft' is also set, the Draft:
            prefix is applied/removed on this title.
        description: New MR description in Markdown (GitLab flavored). Optional.
            Supports multi-line content.
        labels: Comma-separated labels to SET on the MR (replaces existing).
            Optional.
        target_branch: New target branch. Optional.
        draft: If True, mark the MR as draft; if False, unmark it; if omitted,
            leave the draft state unchanged. Toggling draft needs a usable
            title: if none is supplied the current MR title is fetched, and a
            title that is empty or only a draft marker raises ValueError.
    """
    fields: dict = {}

    # Resolve the title together with the draft flag so the Draft: marker stays
    # consistent with GitLab's own draft detection.
    effective_title = title.strip()
    if draft is not None:
        base = _DRAFT_MARKER.sub("", effective_title).strip()
        if not effective_title:
            # No title supplied: fetch the current MR title to carry the marker.
            current = _glab_api(
                f"projects/{_encode_project(TARGET_PROJECT)}"
                f"/merge_requests/{mr_iid}"
            )
            fetched = (
                (current.get("title") or "").strip()
                if isinstance(current, dict)
                else ""
            )
            base = _DRAFT_MARKER.sub("", fetched).strip()

        if not base:
            # Either a supplied title was only a marker, or the fetched title
            # was empty/marker-only. Fail loudly rather than silently writing an
            # empty or "Draft: " title.
            raise ValueError(
                f"Cannot toggle draft on MR {mr_iid}: no usable title "
                "(empty or draft-marker only). Pass an explicit 'title'."
            )

        effective_title = f"Draft: {base}" if draft else base

    if effective_title:
        fields["title"] = effective_title
    if description:
        fields["description"] = description
    if labels:
        fields["labels"] = labels
    if target_branch:
        fields["target_branch"] = target_branch

    if not fields:
        raise ValueError(
            "gitlab_update_mr requires at least one field to change "
            "(title, description, labels, target_branch, or draft)."
        )

    endpoint = (
        f"projects/{_encode_project(TARGET_PROJECT)}/merge_requests/{mr_iid}"
    )
    data = _glab_api(endpoint, method="PUT", fields=fields)
    return _format_mr(data)


@mcp.tool()
def gitlab_mr_add_comment(mr_iid: int, body: str) -> dict:
    """Add a comment/note to a merge request on the upstream reference repo.

    Args:
        mr_iid: The MR IID (e.g. 720).
        body: Comment body in Markdown.
    """
    endpoint = (
        f"projects/{_encode_project(TARGET_PROJECT)}"
        f"/merge_requests/{mr_iid}/notes"
    )
    data = _glab_api(endpoint, method="POST", fields={"body": body})

    return {
        "id": data.get("id"),
        "author": (data.get("author") or {}).get("username"),
        "body": data.get("body", "")[:200],
        "created_at": data.get("created_at"),
    }
