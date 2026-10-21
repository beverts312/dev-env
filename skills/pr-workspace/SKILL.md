---
name: pr-workspace
description: >-
  Open a cmux PR review workspace with the `be` CLI (`be pr r REPO NUMBER`):
  clone or reuse the repo, start Claude running /pr-review, show the PR in a
  browser pane, and file the workspace under the `prs` group. Use when the user
  runs /pr-workspace with a PR link, `owner/repo#123`, or `repo 123`.
argument-hint: <pr-url | owner/repo#N | repo N>
disable-model-invocation: true
---

# Open a PR review workspace

Turn `$ARGUMENTS` into `REPO NUMBER` and run `be pr r REPO NUMBER`. Don't review
the PR here; the new workspace does that.

## Steps

1. Parse the arguments into a repo and a PR number:
   - `https://github.com/owner/repo/pull/123` (any trailing path such as `/files`) → `owner/repo 123`
   - `owner/repo#123` → `owner/repo 123`
   - `owner/repo 123` or `repo 123` → as given. A bare repo name is fine: `be` fills in the owner from `work_org`.

   If there are no arguments, or no PR number can be found, ask for the PR link and stop.
2. Run `be pr r REPO NUMBER`. Pass no other flags: the clone location comes from
   the `pr.dir` config. Pass `--parent` or `--org` only when the user asks for them.
3. Report the result in one line: the workspace name (`pr-<repo>-<number>`) and that it is in the
   `prs` group. If the command fails, show its error output as-is and stop. Don't retry with
   different flags.
