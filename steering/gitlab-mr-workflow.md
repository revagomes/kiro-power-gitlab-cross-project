---
inclusion: auto
name: "GitLab MR Workflow"
description: "Cross-project merge request creation, review, and merge workflow for fork-based GitLab projects."
---

# GitLab MR Workflow

## Creating a Cross-Project MR

1. Ensure the branch is pushed to the **source** (fork) project
2. Call `gitlab_create_cross_mr` with:
   - `branch`: the source branch name
   - `title`: concise title under 70 chars (use `TICKET-ID: Description.` format)
   - `description`: markdown body with summary, what changed, what was tested
3. The tool handles project IDs, URL encoding, and default labels automatically

## Checking MR Readiness

Call `gitlab_mr_status(mr_iid=N)` and verify:
- `pipeline_status` is `success`
- `has_conflicts` is `false`
- `approved` is `true` (or `approvals_left` is 0)
- `blocking_discussions_resolved` is `true`
- `merge_status` is `can_be_merged`

## Merging

Call `gitlab_merge_mr(mr_iid=N)` — defaults to:
- `squash=true` (clean single commit on target)
- `merge_when_pipeline_succeeds=true` (waits for green pipeline)
- `remove_source_branch=true` (cleanup)

## Post-Merge

After merging, update the related Jira ticket:
1. Add a comment with the MR URL
2. Transition the ticket to the appropriate status
