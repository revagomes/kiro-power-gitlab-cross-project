---
name: "gitlab-cross-project"
displayName: "GitLab Cross-Project"
description: "Create and manage cross-project merge requests on GitLab. Wraps the GitLab REST API via glab CLI for operations that glab doesn't support natively — primarily cross-fork MR creation, status checks, merging, and commenting."
keywords: ["gitlab", "merge request", "cross-project", "MR", "glab", "fork", "upstream", "code review", "pipeline", "CI"]
author: "Renato Vasconcellos Gomes"
---

# GitLab Cross-Project

## Overview

This Power provides GitLab merge request management for cross-project (fork → upstream) workflows. It wraps the GitLab REST API via `glab api` for operations that the `glab` CLI doesn't support natively.

**Key capabilities:**

- **Cross-project MR creation** — Create MRs from a dev fork to the upstream reference repo in one call
- **MR listing** — List open/closed/merged MRs on the upstream repo with filters
- **MR status** — Get detailed MR metadata including pipeline, approvals, conflicts, and merge readiness
- **MR merging** — Merge an MR with squash, pipeline-gating, and branch cleanup options
- **MR commenting** — Add notes/comments to MRs

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **glab CLI** | Must be installed and authenticated (`glab auth login`) |
| **Python 3.11+** | Required for the MCP server |
| **uvx** | Used to run the FastMCP server (part of `uv` toolchain) |

No separate GitLab token is needed — the server inherits authentication from the user's existing `glab` configuration.

## Configuration

All configuration is via environment variables with sensible defaults:

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `GITLAB_SOURCE_PROJECT` | No | `your-group/source-project` | Source project path (the fork) |
| `GITLAB_TARGET_PROJECT` | No | `your-group/target-project` | Target project path (upstream) |
| `GITLAB_SOURCE_ID` | No | `1001` | Source project numeric ID |
| `GITLAB_TARGET_ID` | No | `2002` | Target project numeric ID |
| `GITLAB_DEFAULT_LABELS` | No | `ai::review` | Default labels for new MRs |

Override these in your `mcp.json` `env` block to use with different GitLab projects.

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `gitlab_create_cross_mr` | Create a cross-project MR from fork to upstream |
| `gitlab_list_mrs` | List MRs on the upstream repo (filter by state, branch, author, labels) |
| `gitlab_mr_status` | Get detailed MR status (pipeline, approvals, conflicts, merge readiness) |
| `gitlab_merge_mr` | Merge an MR (with squash, pipeline gating, branch cleanup) |
| `gitlab_mr_add_comment` | Add a comment/note to an MR |

## Activation Keywords

This power activates when you mention:
- gitlab, merge request, MR, cross-project
- create MR, open MR, submit MR
- MR status, pipeline status, approvals
- merge, squash, merge when pipeline succeeds

## Quick Usage Examples

### Create a cross-project MR

User: "Create an MR for the cache fix branch"
→ Call `gitlab_create_cross_mr(branch="feature/PROJ-3882-cache-fix", title="PROJ-3882: Fix cache invalidation.")`

### Check MR status

User: "What's the status of MR 720?"
→ Call `gitlab_mr_status(mr_iid=720)` and summarize pipeline, approvals, merge readiness.

### List open MRs

User: "Show me open MRs"
→ Call `gitlab_list_mrs(state="opened")` and present the list.

### Merge an MR

User: "Merge MR 720"
→ Call `gitlab_merge_mr(mr_iid=720)` with default squash + pipeline gating.

### Add a comment to an MR

User: "Add a comment to MR 720 about the test results"
→ Call `gitlab_mr_add_comment(mr_iid=720, body="All tests passing. Ready for merge.")`

## Why This Exists

The `glab` CLI doesn't support cross-project (fork → upstream) merge request creation. The standard `glab mr create` only works within a single project. For cross-project workflows, you need the GitLab REST API with `target_project_id` — this power wraps that complexity into a single tool call.

## Troubleshooting

### glab auth errors

Run `glab auth status` to verify authentication. If expired, run `glab auth login`.

### "Project not found" errors

Verify the project paths in your env config match your GitLab instance. Use `glab api projects?search=project-name` to find correct paths.

### MR creation fails with "source branch not found"

Push your branch to the **source** project (the fork) before creating the MR. The branch must exist on the remote.

### Merge blocked

Check `gitlab_mr_status` — common blockers are: failed pipeline, unresolved discussions, missing approvals, or merge conflicts.
