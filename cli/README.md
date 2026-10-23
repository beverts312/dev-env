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
| `be pr review REPO NUMBER [--parent DIR]`     | `scripts/pr_review.py` | Clone or reuse a checkout (alias: `be pr r`), then open a cmux workspace running `claude '/pr-review <slug> <number>'`, with the pull request open in a browser pane beside it. The workspace goes in the `prs` workspace group, which is created on first use                   |
| `be pr clean [--parent DIR] [--dry-run] [-y]` |                        | Delete everything inside the PR directory, keeping the directory itself. It lists what it will remove and asks first. It refuses to run if no PR directory is configured, or if the directory is `/`, your home directory, or a parent of it. Symlinks are removed, not followed |
| `be pr list [-i] [-a] [-m] [--parent DIR]` | | List open PRs that request your review, directly or through a team (alias: `be pr ls`); `-m`/`--mine` lists open PRs you opened instead, with the same filters. By default only ready (non-draft) PRs with passing checks that aren't by Renovate (`renovate`) are shown, with a count of the hidden ones on stderr; `-a`/`--all` shows every PR. Shows columns for number, repo, author, combined check status (`pass`, `fail`, `pending`, `none`), and title. Uses `gh`. `-i` moves through the list; enter runs `be pr review` on the selected PR, `o` opens it on GitHub, `m` toggles between review requests and your PRs, `a` toggles the filters (like `--all`), `q` quits |

### `be jira`

| Command                 | What it does                                                                                                                                                                                                                                                                  |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `be jira list [-i] [-a]` | List Jira issues assigned to you whose status is in the In Progress category (alias: `be jira ls`), most recently updated first, showing the issue key, type, and summary. Features are hidden by default, with a count of them on stderr; `-a`/`--all` shows them. Needs `jira.url`, `jira.email`, and `jira.token`; see [Jira](#jira). `-i` moves through the list; enter opens the selected issue in your browser, `a` toggles the filter (like `--all`), `q` quits |

### `be server`

| Command | What it does |
| ------- | ------------ |
| `be server [--host H] [--port P] [--parent DIR] [--no-open]` | Serve a local web page (default `http://127.0.0.1:8765`, opened in your browser) with tables matching `be pr ls`, `be pr ls --mine`, and `be jira ls`. Each PR row has a review button (runs `be pr review`) and links to GitHub; each issue links to Jira. If the Jira lookup fails (e.g. `jira.*` isn't set), its table shows the error and the PR tables still load. `show all` toggles the filters (including hidden Features) and `refresh` fetches the lists again. Keys match `be pr ls -i`: `j`/`k` or arrows move, enter reviews a PR or opens an issue, `o` opens in the browser, `m` switches table, `a` toggles the filters |

### `be ws`

| Command                                                                                      | Replaces                     | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------------------------------------------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `be ws create [WORK_DIR] [REPOS] [--dir DIR] [--extra-dirs] [-d DESCRIPTION] [--model] [--window W] [-i]` | `scripts/workspace_setup.py` | Clone comma-separated `REPOS` into `WORK_DIR`, open a split cmux workspace with Claude, and save the layout. A relative `WORK_DIR` is created under `--dir`. Writes `workspace.yml` at the root with the workspace `name`, `description`, and `extra_dirs`. If `WORK_DIR`'s name starts with an issue key in a `jira.projects` project (e.g. `ACME-123-login`), it fetches the issue summary, saves it as `issue_name`, and uses it as the cmux workspace name; if the lookup fails it prints a warning and continues. See [Jira](#jira). `-i` prompts for the name, repos, extra dirs, and description, offering any you passed as defaults; `WORK_DIR` is required without it |
| `be ws open NAME [--dir DIR] [--model MODEL] [--window W]` |                              | Open the cmux layout that `ws create` saved for `NAME`, and start Claude in the main pane. The cmux workspace is named after `issue_name` when `workspace.yml` has one                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `be ws get NAME [--dir DIR]`                                                                 |                              | Show a workspace's name, description, repos, and extra dirs as YAML. The name, description, and extra dirs come from `workspace.yml`; repos are the git checkouts directly under the workspace                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `be ws list [-i] [--dir DIR] [--window W]` |                              | List workspace directories in `ws.dir` (alias: `be ws ls`). Needs `ws.dir` or `--dir`. `-i` shows each workspace with its `issue_name` and description from `workspace.yml`, and moves through the list; enter opens the selected workspace, `g` shows it (as `ws get` does), `j` looks up its Jira issue again and saves the summary as `issue_name` in `workspace.yml` (used as the cmux name on the next `ws open`), `d` deletes it and its cmux layout after you confirm, and `q` quits                                                                                                                                                                                                                                                                         |
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
| `work_org`              | `WORK_ORG`              | `git clone`, `pr review`, `ws create` (`--org`)       | GitHub org for bare repo names                                                                     | none; needed for bare names                                                 |
| `git.email`             | `GIT_EMAIL`             | `git author` (`--email`)                              | Value for `git config user.email`                                                                  | none; required                                                              |
| `git.name`              | `GIT_NAME`              | `git author` (`--name`)                               | Value for `git config user.name`                                                                   | none; required                                                              |
| `pr.dir`                | `PRS_DIR`               | `pr review`, `pr clean` (`--parent`)                  | Parent directory for PR checkouts                                                                  | current directory for `review`; `clean` requires it                         |
| `ws.dir`                | `WS_DIR`                | `ws create`, `ws open`, `ws get`, `ws list` (`--dir`) | Parent directory for a relative workspace path. `list` requires it                                 | current directory for `create`, `open`, and `get`; `list` requires it       |
| `claude.model`          | `BE_CLAUDE_MODEL`       | `ws create`, `ws open` (`--model`)                    | Model passed as `claude --model`                                                                   | `claude-opus-5-5`                                                           |
| `cmux.bin`              | `BE_CMUX_BIN`           | `pr review`, `ws create`, `ws open`, `ws list -i`     | Path to the cmux binary                                                                            | `cmux` on `PATH`, then `/Applications/cmux.app/Contents/Resources/bin/cmux` |
| `cmux.window` | `BE_CMUX_WINDOW` | `ws create`, `ws open`, `ws list -i` (`--window`) | cmux window that new workspaces open in. `pick` lists the windows, labelled by their selected workspace, and asks (it doesn't ask when there is only one); a window index, ref, or UUID is passed to cmux as is | inside cmux, the window `be` runs in; outside cmux (e.g. iTerm), `pick` |
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

`set` and `unset` rewrite the file, which drops any comments in it. Use
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
