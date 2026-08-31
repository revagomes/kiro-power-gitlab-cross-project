# kiro-power-gitlab-cross-project

A Kiro Power for managing cross-project GitLab merge requests via MCP.

## Problem

The `glab` CLI doesn't support creating merge requests across projects (fork → upstream). You need the GitLab REST API with `target_project_id`, which requires URL-encoding project paths and remembering numeric project IDs.

## Solution

This MCP server wraps `glab api` calls behind clean tool interfaces. It inherits authentication from the user's existing `glab` configuration — no separate tokens needed.

## Tools

| Tool | Description |
|------|-------------|
| `gitlab_create_cross_mr` | Create a cross-project MR |
| `gitlab_list_mrs` | List MRs with filters |
| `gitlab_mr_status` | Detailed MR status (pipeline, approvals, conflicts) |
| `gitlab_merge_mr` | Merge with squash/pipeline gating |
| `gitlab_mr_add_comment` | Add comments to MRs |

## Setup

1. Ensure `glab` is installed and authenticated: `glab auth status`
2. Ensure `uv`/`uvx` is installed
3. Add to your `.kiro/settings/mcp.json`:

```json
"gitlab-cross-project": {
  "command": "uvx",
  "args": ["--from", "fastmcp", "fastmcp", "run", "/path/to/server/gitlab_cross_project_mcp.py"],
  "env": {
    "GITLAB_SOURCE_PROJECT": "your-org/your-fork",
    "GITLAB_TARGET_PROJECT": "your-org/your-upstream",
    "GITLAB_SOURCE_ID": "1234",
    "GITLAB_TARGET_ID": "5678",
    "GITLAB_DEFAULT_LABELS": "ai::review"
  }
}
```

## Finding Project IDs

```bash
glab api "projects/your-org%2Fyour-project" | jq '.id'
```

## License

GPLv2+ — see [LICENSE](LICENSE) for the full text.
