# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles
to the strings actually used in this repo's issue tracker.

Because this repo tracks issues as local markdown (see `issue-tracker.md`), these are
not GitHub labels. They are the permitted values of the `Status:` line near the top of
each issue file:

```markdown
# 03 — Render the weekly digest as HTML

Status: ready-for-agent
Blocked-by: 01-fda-recall-adapter.md
```

| Role in the skills | String in our tracker | Meaning                                  |
| ------------------ | --------------------- | ---------------------------------------- |
| `needs-triage`     | `needs-triage`        | Maintainer needs to evaluate this issue  |
| `needs-info`       | `needs-info`          | Waiting on reporter for more information |
| `ready-for-agent`  | `ready-for-agent`     | Fully specified, ready for an AFK agent  |
| `ready-for-human`  | `ready-for-human`     | Requires human implementation            |
| `wontfix`          | `wontfix`             | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), write the
corresponding string from this table into the issue's `Status:` line.

Edit the middle column to match whatever vocabulary you actually use.

## If you later switch to GitHub Issues

The repo's existing labels are the GitHub defaults, which already include `wontfix`.
The other four roles would need creating before the `triage` skill could apply them:

```sh
gh label create needs-triage    --description "Maintainer needs to evaluate"
gh label create needs-info      --description "Waiting on reporter"
gh label create ready-for-agent --description "Fully specified, AFK-ready"
gh label create ready-for-human --description "Needs human implementation"
```
