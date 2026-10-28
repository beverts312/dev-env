# be

Personal workflow CLI built on [Click](https://click.palletsprojects.com/).
It wraps the `wclone`/`gauthor` shell functions in `aliases/git.sh`,
`scripts/pr_review.py`, and `scripts/workspace_setup.py`. Those originals are
left as they are. `be backup` replaces `backup_util.py`, `be convert` replaces
`scripts/json_to_csv.py` and `scripts/to_base64.py`, `be dns` replaces
`scripts/r53_to_cf.py`, and `be compare` replaces `scripts/compare_dirs.py`;
those have been removed.

## Install

```bash
uv tool install --editable ./cli
```

Or into a virtualenv:

```bash
python3 -m pip install -e './cli[test]'   # needs Python 3.11+
```

Some commands need an extra for their cloud clients:

- `be backup upload` and `download`: `uv tool install --editable './cli[backup]'`
- `be dns r53-cf`: `uv tool install --editable './cli[dns]'`
- `be kube`: `uv tool install --editable './cli[kube]'`

Combine them as `'./cli[backup,dns]'`.

## Commands

`be <command> --help` lists every option, its env var, and its config key.

### `be git`

| Command                                      | Replaces  | What it does                                                                       |
| -------------------------------------------- | --------- | ---------------------------------------------------------------------------------- |
| `be git clone REPO [DEST]`                   | `wclone`  | Clone `REPO` (bare name under `WORK_ORG`, or `owner/repo`) with submodules         |
| `be git author [--email] [--name] [--local]` | `gauthor` | Set `user.email` / `user.name` (global by default, `--local` for the current repo) |

### `be pr`

| Command                                       | Replaces               | What it does                                                                                                                                                                                                                                                                     |
| --------------------------------------------- | ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `be pr review REPO NUMBER [--parent DIR] [--agent claude\|cursor] [--claude-model M] [--cursor-model M]` | `scripts/pr_review.py` | Clone or reuse a checkout (alias: `be pr r`), then open a cmux workspace running `claude '/pr-review <slug> <number>'` (or Cursor's `agent '/pr-review <slug> <number>'` with `--agent cursor`), with the pull request open in a browser pane beside it. When `claude.pr.model` or `--claude-model` is set, Claude is started with `--model`; when `cursor.pr.model` or `--cursor-model` is set, Cursor's `agent` is. The other agent's model is ignored. The workspace goes in the `prs` workspace group, which is created on first use. If a workspace named `pr-<repo>-<number>` is already open in any cmux window, it switches to that one instead, without touching the checkout                   |
| `be pr clean [--parent DIR] [--dry-run] [-y]` |                        | Delete everything inside the PR directory, keeping the directory itself. It lists what it will remove and asks first. It refuses to run if no PR directory is configured, or if the directory is `/`, your home directory, or a parent of it. Symlinks are removed, not followed |
| `be pr list [-i\|-I] [-a] [-m\|-t] [--parent DIR] [--agent claude\|cursor] [--claude-model M] [--cursor-model M]` | | List open PRs that request your review by name (alias: `be pr ls`); `-t`/`--team` lists PRs that request your review only through a team, and `-m`/`--mine` lists open PRs you opened, with the same filters. By default only ready (non-draft) PRs with passing checks that aren't by Renovate (`renovate`) are shown, with a count of the hidden ones on stderr; `-a`/`--all` shows every PR. Shows columns for number, repo, author, combined check status (`pass`, `fail`, `pending`, `none`), approvals (reviewers whose latest review approves), whether it's a draft (only with `--all`, or after `a` in `-i`), and title. Uses `gh`. `-i` moves through the list; enter runs `be pr review` on the selected PR, using this command's `--agent` and model flags, `o` opens it on GitHub, tab cycles through review requests, team review requests, and your PRs, `a` toggles the filters (like `--all`), `q` quits. On your PRs, `r` marks a draft ready for review, `u` enables auto-merge, and `m` merges an approved PR, using the first merge method the repo allows of squash, merge, rebase (auto-merge needs the repo to allow it) |

### `be jira`

| Command                 | What it does                                                                                                                                                                                                                                                                  |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `be jira list [-i\|-I] [-a] [--dir DIR] [--model] [--org] [--window W]` | List Jira issues assigned to you whose status is in the In Progress category (alias: `be jira ls`), most recently updated first, showing the issue key, type, and summary. Features are hidden by default, with a count of them on stderr; `-a`/`--all` shows them. Needs `jira.url`, `jira.email`, and `jira.token`; see [Jira](#jira). `-i` moves through the list; enter opens the selected issue's workspace (a directory in `ws.dir` named after the issue key, or else after its parent's key, ignoring case; as `ws open` does). If there is none, it offers to create one: unless the issue is a Feature or Epic, and when its parent is one, it asks whether the workspace is for the issue only or for that parent, then prompts for the name (default: that key), repos, extra dirs, and description as `ws create -i` does, saving that issue's summary as `issue_name`. `o` opens the issue in your browser, `a` toggles the filter (like `--all`), `q` quits |

### `be server`

| Command | What it does |
| ------- | ------------ |
| `be server [--host H] [--port P] [--parent DIR] [--no-open] [--log-level LEVEL] [--agent claude\|cursor] [--claude-model M] [--cursor-model M]` | Serve a local web page (default `http://127.0.0.1:8765`, opened in your browser) with your Jira issues and tables matching `be pr ls`, `be pr ls --team`, `be pr ls --mine`, and `be ws list`, on four pages in a collapsible sidebar: **my work** (the Jira tree), **my PRs** (your PRs), **reviews** (review requests and team review requests), and **workspaces**. Each page shows how many rows it has shown. The sidebar's open or collapsed state is remembered, as is the last page (or the one in the URL's `#work`, `#prs`, `#reviews`, or `#workspaces`). Each PR row has a review button (runs `be pr review`) and links to GitHub. The reviews page has a review agent toggle at the top (claude or cursor); a review started from the page uses that choice instead of `pr.agent` or `--agent`, and the browser remembers it. The toggle starts on the agent `be server` would otherwise use. Your PRs also get a ready button on drafts and an auto-merge button otherwise, matching `r` and `u` in `be pr ls -i`, plus a merge button once a PR is approved (with the repo's preferred merge method); a PR with auto-merge already enabled gets neither. Your PRs' table has no author column. The Jira issues show as a tree rather than a table: every issue assigned to you that isn't done, each nested under its parent when that's shown too, in progress first; under each of yours that's in progress are its children that aren't done, whoever they're assigned to (with their assignee shown). Projects and status dropdowns above the tree list each project in it (with its `jira.projects` description) and each status (To Do ones first, then In Progress) as checkboxes; checking some shows only the issues matching every dropdown with something checked, plus, dimmed, any issue that holds a match, and checking none (or show all) in a dropdown stops it filtering. The choices are remembered by your browser. Each issue shows its key (linked to Jira), type, status, and summary; a top-level issue names its parent when it has one. An issue with children has an arrow that collapses them (remembered by your browser); `h`/left arrow collapses the selected issue or moves to its parent, `l`/right arrow expands it. Double-clicking an issue opens its workspace (named after or linked to the issue key, or else its parent's key, ignoring case, as `be jira ls -i` finds it; such issues are marked `ws`). Without one, it offers to create one or, when `ws.dir` has workspaces, to link the issue (or the parent it's for) to an existing one instead: linking adds the key to that workspace's `issues` in `workspace.yml` and opens it, and from then on the issue and its children open that workspace here and in `be jira ls -i`. To create one, unless the issue is a Feature or Epic, and when its parent is one, you choose whether it's for the issue or that parent, then give the name (default: that key), repos, extra dirs, and description, as `be jira ls -i` does. Create runs `be ws create` with `ws.dir`, `claude.model`, `work_org`, and `cmux.window`, saving that issue's summary as `issue_name`. The workspaces table lists each directory in `ws.dir` with its issue name, description, repos, and extra dirs (as `be ws get` shows); it loads with the page, and clicking a row runs `be ws open`, which focuses the workspace when it is already open. The Jira tree loads with the page the first time (after that, use its refresh link); the PR tables start empty; each table's `refresh` link fetches just that table, and a failed lookup (e.g. `jira.*` or `ws.dir` isn't set) shows its error in that table. The PR tables have dropdowns to show one check status (`pass`, `fail`, `pending`, `none`) or draft value (`no`, `yes`), or `all`; they default to `pass` and `no`, like `be pr ls`, and while a dropdown shows one value its column is hidden. Each table can be collapsed with the arrow by its heading (remembered by your browser). Each table also has its own filter checkboxes (not by Renovate, except on your PRs; the Jira tree has none). Filters apply in the page and are remembered by your browser; the PR tables also have a search box matching the repo or title (case-insensitive). Keys match `be pr ls -i`: `j`/`k` or arrows move, enter reviews a PR, opens an issue, or opens a workspace, `o` opens in the browser, `t` (or `1`–`4`) switches page, `m` switches table within the page, `a` toggles the current table's filters (dropdowns between `all` and their defaults), `r` marks your draft ready, `u` enables auto-merge on your PR, `x` checks your PR, `c` collapses the current table, `/` focuses the search box (escape or enter leaves it). Your PRs also have a checkbox each (the header one checks every shown row) and a bulk bar whose ready, auto-merge, and merge buttons act on the checked PRs, each counting and acting on only the checked PRs it applies to (the rest are reported as skipped); bulk merge asks to confirm first. Filtering a row out unchecks it. The `config` link in the header opens `/config`, which lists every setting with its file value, source, and help, and saves or unsets each one on its own (map entries such as `jira.projects` each get a row, plus a row to add one; `interactive` and `server.log_level` are dropdowns; `jira.token` is hidden until you click show; saving an empty value removes it). A setting whose env var is set can still be saved, with a note that the env var wins. Saving `pr.dir`, `server.log_level`, `pr.agent`, `claude.pr.model`, or `cursor.pr.model` takes effect immediately unless `--parent`, `--log-level`, `--agent`, `--claude-model`, or `--cursor-model` was given |

### `be ws`

| Command                                                                                      | Replaces                     | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------------------------------------------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `be ws create [WORK_DIR] [REPOS] [--dir DIR] [--extra-dirs] [-d DESCRIPTION] [--model] [--window W] [-i\|-I]` | `scripts/workspace_setup.py` | Clone comma-separated `REPOS` into `WORK_DIR`, open a split cmux workspace with Claude, and save the layout. A relative `WORK_DIR` is created under `--dir`. Writes `workspace.yml` at the root with the workspace `name`, `description`, and `extra_dirs`. If `WORK_DIR`'s name starts with an issue key in a `jira.projects` project (e.g. `ACME-123-login`), it fetches the issue summary, saves it as `issue_name`, and uses it as the cmux workspace name; if the lookup fails it prints a warning and continues. See [Jira](#jira). `-i` prompts for the name, repos, extra dirs, and description, offering any you passed as defaults; `WORK_DIR` is required without it |
| `be ws open NAME [--dir DIR] [--model MODEL] [--window W]` |                              | Open the cmux layout that `ws create` saved for `NAME`, and start Claude in the main pane. The cmux workspace is named after `issue_name` when `workspace.yml` has one. If a workspace with that name is already open in any cmux window, it brings that window forward and selects the workspace instead of opening a duplicate (this also applies to enter in `ws list -i` and `jira list -i`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `be ws get NAME [--dir DIR]`                                                                 |                              | Show a workspace's name, description, repos, and extra dirs as YAML. The name, description, and extra dirs come from `workspace.yml`; repos are the git checkouts directly under the workspace                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `be ws list [-i\|-I] [--dir DIR] [--window W]` |                              | List workspace directories in `ws.dir` (alias: `be ws ls`). Needs `ws.dir` or `--dir`. `-i` shows each workspace with its `issue_name` and description from `workspace.yml`, and moves through the list; enter opens the selected workspace, `g` shows it (as `ws get` does), `j` looks up its Jira issue again and saves the summary as `issue_name` in `workspace.yml` (used as the cmux name on the next `ws open`), `d` deletes it and its cmux layout after you confirm, and `q` quits                                                                                                                                                                                                                                                                         |
| `be ws delete NAME [--dir DIR] [--keep-layout] [--dry-run] [-y]`                             |                              | Delete a workspace directory and its saved cmux layout (alias: `be ws rm`). It shows what it will remove and asks first. It refuses the `--dir` parent, `/`, your home directory or a parent of it, and symlinks. If cmux can't delete the layout, the directory is still removed and a warning is printed                                                                                                                                                                                                                                                                                                                                                                     |

### `be kube`

Ported from the `bk` CLI (left as is in `~/notes/bk`). Uses the current
kubeconfig context, as kubectl does. Needs the `kube` extra (see
[Install](#install)).

| Command                              | What it does                                                                                                                                                                                                                                     |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `be kube pool NODE_POOL`             | Table of the pods on every node in the GKE node pool (`cloud.google.com/gke-nodepool` label), with namespace and ready containers                                                                                                                |
| `be kube secret NAME [-n NAMESPACE]` | Print a secret's keys with base64-decoded values. The namespace defaults to the current context's namespace (as set by `kns`), then `default`                                                                                                    |
| `be kube rm-fin RESOURCE...`         | Remove `metadata.finalizers` from a resource stuck deleting (alias: `rm_fin`). Arguments go straight to `kubectl patch`, so `pod/foo`, `pod foo -n ns`, or any CRD works. Shells out to `kubectl`, so it doesn't need the `kube` extra           |
| `be kube get-all [KUBECTL_ARGS...]`  | Run `kubectl get` for every listable namespaced resource type in the current namespace (alias: `kall`). Extra arguments, such as `-n ns` or `-l app=foo`, go to each `kubectl get`. Shells out to `kubectl`, so it doesn't need the `kube` extra |

### `be backup`

Replaces `backup_util.py`. These commands read their own YAML config,
`./encrypted_backup.yml` by default, not `~/.be/config`. GCS auth uses Application Default Credentials and
S3 uses the standard AWS credential chain. `upload` and `download` need the
`backup` extra (see [Install](#install)).

| Command                                                         | What it does                                                                                                                                                             |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `be backup setup [--config PATH]`                               | Prompt for the key path, source dir, `storage_uri` (`gs://bucket/object` or `s3://bucket/object`), and ignore globs; write the config YAML and optionally generate a key |
| `be backup gen-key [--config PATH] [--key-path PATH] [--force]` | Write a Fernet key (mode 600) to `--key-path` or the config's `key_path`                                                                                                 |
| `be backup upload [--config PATH] [--dry-run]`                  | Archive `source_dir` as tar.gz (skipping the `ignore` globs, the config, and the key), encrypt it, and upload it to `storage_uri`. `--dry-run` lists the files instead   |
| `be backup download [--config PATH] [--dest DIR]`               | Download, decrypt, and extract the archive into `--dest` (default: current directory)                                                                                    |

### `be compare`

| Command                              | Replaces                  | What it does                                                                                                                                                                                                                                                |
| ------------------------------------ | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `be compare dirs SOURCE TARGET [-m]` | `scripts/compare_dirs.py` | List files in `TARGET` that aren't in `SOURCE`, by path relative to each root; `-m` lists files in both instead. `SOURCE` and `TARGET` fall back to the `SOURCE` and `TARGET` env vars. The list goes to stdout and progress to stderr, so it pipes cleanly |

### `be convert`

| Command                               | Replaces                 | What it does                                                                                                                                                                                                   |
| ------------------------------------- | ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `be convert json-csv SRC [-o OUTPUT]` | `scripts/json_to_csv.py` | Convert a JSON array of objects to CSV with a header row. Columns are the union of every object's keys, and values are quoted as needed. Writes `SRC` with a `.csv` suffix by default; `-o -` writes to stdout |
| `be convert base64 SRC [-d]`          | `scripts/to_base64.py`   | Print `SRC` (a file, or `-` for stdin) base64-encoded; `-d` decodes instead                                                                                                                                    |

### `be dns`

| Command                                                                                               | Replaces               | What it does                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `be dns r53-cf DOMAIN [--dry-run] [--skip-nameserver-update] [--hosted-zone-id ID] [--account-id ID]` | `scripts/r53_to_cf.py` | Migrate `DOMAIN` from Route53 to Cloudflare: create the Cloudflare zone if needed, copy the Route53 records into it (skipping NS, SOA, and records Cloudflare already has), then point the Route53 Domains registration at Cloudflare's nameservers. Aliases become CNAMEs, except `dualstack.` and `s3-website` targets, which are skipped for manual review. `--dry-run` creates and changes nothing, not even the zone |
| `be dns flush-local`                                                                                  |                        | Flush the local DNS cache with `sudo dscacheutil -flushcache` and `sudo killall -HUP mDNSResponder`. macOS only; errors on other systems                                                                                                                                                                                                                                                                                  |

`r53-cf` needs `CLOUDFLARE_API_TOKEN` with Zone > DNS Read and Edit. AWS uses
the standard credential chain. It also needs the `dns` extra (see [Install](#install)).

### `be config`

Inspect and edit the config file. See [`be config` commands](#be-config-commands).

## Configuration

Each setting is resolved in this order, first match wins:

1. command-line flag
2. environment variable
3. config file
4. built-in default

The config file is TOML at `~/.be/config`. Set `BE_CONFIG` to use a different path.

```toml
work_org = "acme"
interactive = "true"

[git]
email = "me@acme.com"
name = "Bailey Everts"

[pr]
dir = "~/prs"

[ws]
dir = "~/workspaces"

[claude]
model = "claude-opus-5-5"

[cmux]
bin = "/Applications/cmux.app/Contents/Resources/bin/cmux"

[jira]
url = "https://acme.atlassian.net"

[jira.projects]
ACME = "Acme"
OPS = "Operations"
```

### Settings

| Config key              | Env var                 | Used by                                               | Purpose                                                                                            | Default                                                                     |
| ----------------------- | ----------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `work_org`              | `WORK_ORG`              | `git clone`, `pr review`, `ws create`, `jira list -i` (`--org`) | GitHub org for bare repo names                                                                     | none; needed for bare names                                                 |
| `interactive` | `BE_INTERACTIVE` | `pr list`, `jira list`, `ws list`, `ws create` (`-i`/`-I`) | `true` makes `-i` the default when stdin and stdout are a terminal, so piped or scripted runs stay plain. `-I`/`--no-interactive` turns it off for one run. `ws create` only prompts by default when `WORK_DIR` is missing. Accepts `true`/`false`, `yes`/`no`, `on`/`off`, `1`/`0` | `false` |
| `git.email`             | `GIT_EMAIL`             | `git author` (`--email`)                              | Value for `git config user.email`                                                                  | none; required                                                              |
| `git.name`              | `GIT_NAME`              | `git author` (`--name`)                               | Value for `git config user.name`                                                                   | none; required                                                              |
| `pr.dir`                | `PRS_DIR`               | `pr review`, `pr clean` (`--parent`)                  | Parent directory for PR checkouts                                                                  | current directory for `review`; `clean` requires it                         |
| `pr.agent`              | `BE_PR_AGENT`           | `pr review`, `pr list -i`, `server` (`--agent`)       | Agent CLI that runs `/pr-review`: `claude` or `cursor` (Cursor's `agent`)                               | `claude`                                                                    |
| `claude.pr.model`       | `BE_CLAUDE_PR_MODEL`    | `pr review`, `pr list -i`, `server` (`--claude-model`) | Model passed as `claude --model` when the review agent is Claude                                      | none; Claude starts without `--model`                                       |
| `cursor.pr.model`       | `BE_CURSOR_PR_MODEL`    | `pr review`, `pr list -i`, `server` (`--cursor-model`) | Model passed as `agent --model` when the review agent is Cursor                                       | none; Cursor starts without `--model`                                       |
| `ws.dir`                | `WS_DIR`                | `ws create`, `ws open`, `ws get`, `ws list`, `jira list -i` (`--dir`) | Parent directory for a relative workspace path. `list` requires it                                 | current directory for `create`, `open`, and `get`; `list` requires it       |
| `claude.model`          | `BE_CLAUDE_MODEL`       | `ws create`, `ws open`, `jira list -i` (`--model`)    | Model passed as `claude --model`                                                                   | `claude-opus-5-5`                                                           |
| `cmux.bin`              | `BE_CMUX_BIN`           | `pr review`, `ws create`, `ws open`, `ws list -i`     | Path to the cmux binary                                                                            | `cmux` on `PATH`, then `/Applications/cmux.app/Contents/Resources/bin/cmux` |
| `cmux.window` | `BE_CMUX_WINDOW` | `ws create`, `ws open`, `ws list -i`, `jira list -i` (`--window`) | cmux window that new workspaces open in. `pick` lists the windows, labelled by their selected workspace, and asks (it doesn't ask when there is only one); a window index, ref, or UUID is passed to cmux as is | inside cmux, the window `be` runs in; outside cmux (e.g. iTerm), `pick` |
| `server.log_level` | `BE_SERVER_LOG_LEVEL` | `server` (`--log-level`) | What `be server` logs to stderr: `debug` (also each table fetch and `gh` call), `info` (also each request, fetched table and action), `warning` (failed fetches and actions, and GitHub rate-limit or gateway-error retries) or `error` | `warning` |
| `cloudflare.account_id` | `CLOUDFLARE_ACCOUNT_ID` | `dns r53-cf` (`--account-id`)                         | Cloudflare account that new zones are created in                                                   | none; Cloudflare picks the token's account                                  |
| `jira.url`              | `JIRA_URL`              | `ws create`, `jira ls`, `server`                      | Base URL of the Jira site, e.g. `https://example.atlassian.net`                                    | none                                                                        |
| `jira.email`            | `JIRA_EMAIL`            | `ws create`, `jira ls`, `server`                      | Atlassian account email for the Jira API                                                           | none                                                                        |
| `jira.token`            | `JIRA_API_TOKEN`        | `ws create`, `jira ls`, `server`                      | Atlassian API token for the Jira API. Masked in `be config list`                                   | none                                                                        |
| `jira.projects`         | `JIRA_PROJECTS`         | `ws create`                                           | Map of Jira project key to description. The env var is a JSON object, e.g. `{"OPS": "Operations"}` | none                                                                        |
| –                       | `BE_CONFIG`             | everything                                            | Path to the config file                                                                            | `~/.be/config`                                                              |

Running `be` outside cmux (e.g. from iTerm) needs cmux to accept outside
processes on its control socket. The default mode, `cmuxOnly`, refuses them. Set
it in `~/.config/cmux/cmux.json` and run `cmux reload-config`:

```json
"automation": { "socketControlMode": "allowAll" }
```

### `be config` commands

| Command                        | What it does                                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------------------------- |
| `be config path`               | Print the config file path                                                                        |
| `be config list`               | Show every setting, its effective value, and its source (`env:<VAR>`, `file`, `default`, `unset`) |
| `be config get KEY [--source]` | Print a setting's effective value; exits 1 if unset                                               |
| `be config set KEY VALUE`      | Write a value to the file; warns if an env var will override it                                   |
| `be config unset KEY`          | Remove a value from the file                                                                      |
| `be config init [--force]`     | Write a commented template, prefilled from current env vars                                       |
| `be config edit`               | Open the file in `$EDITOR` (creating it from the template) and validate it                        |

Map settings such as `jira.projects` are edited one entry at a time:
`be config set jira.projects.OPS "Operations"`, `be config unset jira.projects.OPS`.
`be config get jira.projects` prints every entry as `KEY<tab>description`.

The settings can also be edited in the browser on `be server`'s config page (`/config`).

`set` and `unset` rewrite the file, which drops any comments in it. So does saving on the config page. Use
`be config edit` if you want to keep hand-written comments.

### Jira

`ws create` and `jira ls` look up Jira issues with an Atlassian API token and
Basic auth. They need `jira.url`, `jira.email`, and `jira.token`; `ws create`
also needs `jira.projects`. Create a
token at id.atlassian.com under Security > API tokens, copy it, then:

```bash
be config set jira.token "$(pbpaste)" && pbcopy </dev/null
```

The token is stored in plain text in the config file, which `be` keeps
readable only by you (mode 600). `be config list` masks it; `be config get
jira.token` prints it.

`WORK_ORG`, `GIT_EMAIL`, `GIT_NAME`, and `PRS_DIR` are the same variables the
shell aliases and scripts already read, so an existing shell config works
without changes.

## Development

```bash
cd cli && python3 -m pytest
```

`tests/test_layout.py` checks that `be ws create` builds the same cmux layout
as `scripts/workspace_setup.py`.
