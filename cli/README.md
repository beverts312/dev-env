# be

Personal workflow CLI built on [Click](https://click.palletsprojects.com/).
It wraps the `wclone`/`gauthor` shell functions in `aliases/git.sh`,
`scripts/pr_review.py`, and `scripts/workspace_setup.py`. Those originals are
left as they are.

## Install

```bash
uv tool install --editable ./cli
```

Or into a virtualenv:

```bash
python3 -m pip install -e './cli[test]'   # needs Python 3.11+
```

## Commands

| Command | Replaces | What it does |
|---|---|---|
| `be git clone REPO [DEST]` | `wclone` | Clone `REPO` (bare name under `WORK_ORG`, or `owner/repo`) with submodules |
| `be git author [--email] [--name] [--local]` | `gauthor` | Set `user.email` / `user.name` (global by default, `--local` for the current repo) |
| `be pr review REPO NUMBER [--parent DIR]` | `scripts/pr_review.py` | Clone or reuse a checkout, then open a cmux workspace running `claude '/pr-review <slug> <number>'` |
| `be pr clean [--parent DIR] [--dry-run] [-y]` | | Delete everything inside the PR directory, keeping the directory itself. It lists what it will remove and asks first. It refuses to run if no PR directory is configured, or if the directory is `/`, your home directory, or a parent of it. Symlinks are removed, not followed |
| `be ws setup WORK_DIR [REPOS] [--extra-dirs] [--model]` | `scripts/workspace_setup.py` | Clone comma-separated `REPOS` into `WORK_DIR`, open a split cmux workspace with Claude, and save the layout |

| `be config ...` | | Inspect and edit the config file (see below) |

`be <command> --help` lists every option, its env var, and its config key.

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

[claude]
model = "claude-opus-5-5"

[cmux]
bin = "/Applications/cmux.app/Contents/Resources/bin/cmux"
```

### Settings

| Config key | Env var | Used by | Purpose | Default |
|---|---|---|---|---|
| `work_org` | `WORK_ORG` | `git clone`, `pr review`, `ws setup` (`--org`) | GitHub org for bare repo names | none; needed for bare names |
| `git.email` | `GIT_EMAIL` | `git author` (`--email`) | Value for `git config user.email` | none; required |
| `git.name` | `GIT_NAME` | `git author` (`--name`) | Value for `git config user.name` | none; required |
| `pr.dir` | `PRS_DIR` | `pr review`, `pr clean` (`--parent`) | Parent directory for PR checkouts | current directory for `review`; `clean` requires it |
| `claude.model` | `BE_CLAUDE_MODEL` | `ws setup` (`--model`) | Model passed as `claude --model` | `claude-opus-5-5` |
| `cmux.bin` | `BE_CMUX_BIN` | `pr review`, `ws setup` | Path to the cmux binary | `cmux` on `PATH`, then `/Applications/cmux.app/Contents/Resources/bin/cmux` |
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

`tests/test_layout.py` checks that `be ws setup` builds the same cmux layout
as `scripts/workspace_setup.py`.
