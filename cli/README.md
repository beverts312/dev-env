# be

Personal workflow CLI built on [Click](https://click.palletsprojects.com/).
It wraps the `wclone`/`gauthor` shell functions in `aliases/git.sh`,
`scripts/pr_review.py`, and `scripts/workspace_setup.py`. Those originals are
left as they are. `be backup` replaces `backup_util.py`, which has been removed.

## Install

```bash
uv tool install --editable ./cli
```

Or into a virtualenv:

```bash
python3 -m pip install -e './cli[test]'   # needs Python 3.11+
```

`be backup upload` and `download` also need the `backup` extra for the GCS
and S3 clients: `uv tool install --editable './cli[backup]'`.

## Commands

`be <command> --help` lists every option, its env var, and its config key.

### `be git`

| Command | Replaces | What it does |
|---|---|---|
| `be git clone REPO [DEST]` | `wclone` | Clone `REPO` (bare name under `WORK_ORG`, or `owner/repo`) with submodules |
| `be git author [--email] [--name] [--local]` | `gauthor` | Set `user.email` / `user.name` (global by default, `--local` for the current repo) |

### `be pr`

| Command | Replaces | What it does |
|---|---|---|
| `be pr review REPO NUMBER [--parent DIR]` | `scripts/pr_review.py` | Clone or reuse a checkout (alias: `be pr r`), then open a cmux workspace running `claude '/pr-review <slug> <number>'`, with the pull request open in a browser pane beside it. The workspace goes in the `prs` workspace group, which is created on first use |
| `be pr clean [--parent DIR] [--dry-run] [-y]` | | Delete everything inside the PR directory, keeping the directory itself. It lists what it will remove and asks first. It refuses to run if no PR directory is configured, or if the directory is `/`, your home directory, or a parent of it. Symlinks are removed, not followed |

### `be ws`

| Command | Replaces | What it does |
|---|---|---|
| `be ws create [WORK_DIR] [REPOS] [--dir DIR] [--extra-dirs] [-d DESCRIPTION] [--model] [-i]` | `scripts/workspace_setup.py` | Clone comma-separated `REPOS` into `WORK_DIR`, open a split cmux workspace with Claude, and save the layout. A relative `WORK_DIR` is created under `--dir`. Writes `workspace.yml` at the root with the workspace `name`, `description`, and `extra_dirs`. `-i` prompts for the name, repos, extra dirs, and description, offering any you passed as defaults; `WORK_DIR` is required without it |
| `be ws open NAME [--dir DIR] [--model MODEL]` | | Open the cmux layout that `ws create` saved for `NAME`, and start Claude in the main pane |
| `be ws get NAME [--dir DIR]` | | Show a workspace's name, description, repos, and extra dirs as YAML. The name, description, and extra dirs come from `workspace.yml`; repos are the git checkouts directly under the workspace |
| `be ws list [-i] [--dir DIR]` | | List workspace directories in `ws.dir` (alias: `be ws ls`). Needs `ws.dir` or `--dir`. `-i` moves through the list; enter opens the selected workspace, `g` shows it (as `ws get` does), `d` deletes it and its cmux layout after you confirm, and `q` quits |
| `be ws delete NAME [--dir DIR] [--keep-layout] [--dry-run] [-y]` | | Delete a workspace directory and its saved cmux layout (alias: `be ws rm`). It shows what it will remove and asks first. It refuses the `--dir` parent, `/`, your home directory or a parent of it, and symlinks. If cmux can't delete the layout, the directory is still removed and a warning is printed |

### `be backup`

Replaces `backup_util.py`. These commands read their own YAML config,
`./encrypted_backup.yml` by default, not `~/.be/config`. GCS auth uses ADC and
S3 uses the standard AWS credential chain. `upload` and `download` need the
`backup` extra (see [Install](#install)).

| Command | What it does |
|---|---|
| `be backup setup [--config PATH]` | Prompt for the key path, source dir, `storage_uri` (`gs://bucket/object` or `s3://bucket/object`), and ignore globs; write the config YAML and optionally generate a key |
| `be backup gen-key [--config PATH] [--key-path PATH] [--force]` | Write a Fernet key (mode 600) to `--key-path` or the config's `key_path` |
| `be backup upload [--config PATH] [--dry-run]` | Archive `source_dir` as tar.gz (skipping the `ignore` globs, the config, and the key), encrypt it, and upload it to `storage_uri`. `--dry-run` lists the files instead |
| `be backup download [--config PATH] [--dest DIR]` | Download, decrypt, and extract the archive into `--dest` (default: current directory) |

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
```

### Settings

| Config key | Env var | Used by | Purpose | Default |
|---|---|---|---|---|
| `work_org` | `WORK_ORG` | `git clone`, `pr review`, `ws create` (`--org`) | GitHub org for bare repo names | none; needed for bare names |
| `git.email` | `GIT_EMAIL` | `git author` (`--email`) | Value for `git config user.email` | none; required |
| `git.name` | `GIT_NAME` | `git author` (`--name`) | Value for `git config user.name` | none; required |
| `pr.dir` | `PRS_DIR` | `pr review`, `pr clean` (`--parent`) | Parent directory for PR checkouts | current directory for `review`; `clean` requires it |
| `ws.dir` | `WS_DIR` | `ws create`, `ws open`, `ws get`, `ws list` (`--dir`) | Parent directory for a relative workspace path. `list` requires it | current directory for `create`, `open`, and `get`; `list` requires it |
| `claude.model` | `BE_CLAUDE_MODEL` | `ws create`, `ws open` (`--model`) | Model passed as `claude --model` | `claude-opus-5-5` |
| `cmux.bin` | `BE_CMUX_BIN` | `pr review`, `ws create`, `ws open`, `ws list -i` | Path to the cmux binary | `cmux` on `PATH`, then `/Applications/cmux.app/Contents/Resources/bin/cmux` |
| – | `BE_CONFIG` | everything | Path to the config file | `~/.be/config` |

### `be config` commands

| Command | What it does |
|---|---|
| `be config path` | Print the config file path |
| `be config list` | Show every setting, its effective value, and its source (`env:<VAR>`, `file`, `default`, `unset`) |
| `be config get KEY [--source]` | Print a setting's effective value; exits 1 if unset |
| `be config set KEY VALUE` | Write a value to the file; warns if an env var will override it |
| `be config unset KEY` | Remove a value from the file |
| `be config init [--force]` | Write a commented template, prefilled from current env vars |
| `be config edit` | Open the file in `$EDITOR` (creating it from the template) and validate it |

`set` and `unset` rewrite the file, which drops any comments in it. Use
`be config edit` if you want to keep hand-written comments.

`WORK_ORG`, `GIT_EMAIL`, `GIT_NAME`, and `PRS_DIR` are the same variables the
shell aliases and scripts already read, so an existing shell config works
without changes.

## Development

```bash
cd cli && python3 -m pytest
```

`tests/test_layout.py` checks that `be ws create` builds the same cmux layout
as `scripts/workspace_setup.py`.
