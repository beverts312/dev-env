# Bailey's Dev Env

Common things I use across machines.
## Dev container

`.devcontainer/` builds a Debian (trixie) container with git, Claude Code, Python 3.14 (via uv),
Node 24 + pnpm 11, `gh`, `kubectl`, `aws`, `gcloud`, and shell tools (ripgrep, fd, jq, fzf, tmux,
vim, zsh). Open the repo in VS Code or Cursor and choose **Reopen in Container**, or:

```bash
devcontainer up --workspace-folder .
```

On first create, `.devcontainer/post-create.sh` installs `be`'s Python and web dependencies,
builds the web app, and puts `be` on `PATH`. Then:

- `be server --host 0.0.0.0`: the server listens on 127.0.0.1 by default, which isn't reachable
  through the forwarded port (8765)
- `pnpm -C be/web dev --host`: the Vite dev server (5173)
- `cd be && uv run pytest`: the tests
- `claude`: log in once; its config is kept in the `dev-env-claude` volume across rebuilds

The host's `~/.kube`, `~/.aws`, `~/.config/gh`, and `~/.config/gcloud` are mounted into the
container (they're created on the host if missing). On macOS `gh` keeps its token in the
keychain, so export `GH_TOKEN` on the host instead; `ANTHROPIC_API_KEY` is passed through too.
`configure.py` isn't run in the container; run it by hand if you want `.benvrc` and the aliases.
Versions are `ARG`s at the top of `.devcontainer/Dockerfile`.

### Without VS Code: docker compose

`docker-compose.yml` runs the same image with `docker compose`. Copy `.env.example` to `.env`
(gitignored) and set your `USER_UID`/`USER_GID` (`id -u`, `id -g`) and `CLAUDE_DIR`, the Claude
config dir mounted at `~/.claude` (defaults to your host `~/.claude`). `~/.ssh` is mounted
read-only, plus the same kube, aws, gh, and gcloud dirs; each is a variable in `.env`. Every
variable in `.env` is also set in the container, so `GH_TOKEN` and `ANTHROPIC_API_KEY` go there.

```bash
cp .env.example .env
```

`.bash_profile` has two shortcuts that work from any directory:

- `devcb`: build the image (`docker compose build`)
- `devc`: start Claude in the container with the **current directory** as the workspace, mounted
  at `/workspaces/<directory name>`. Its arguments are `docker compose run` flags:
  `devc --service-ports` publishes ports 8765 and 5173 (on 127.0.0.1) for `be server` and Vite,
  and `devc --entrypoint zsh` opens a shell instead of Claude

```bash
devcb
```

```bash
cd ~/code/some-project && devc
```

Run from this repo without the shortcut, `docker compose run --rm dev` uses this repo as the
workspace; set `WORKSPACE_DIR` and `WORKSPACE_NAME` to pick another. This repo is also always
mounted at `/opt/dev-env` (`$DEV_ENV_HOME` in the container): the entrypoint,
`.devcontainer/entrypoint.sh`, runs from there and starts `claude`, so changes to it don't need
a rebuild. The container exits when Claude does.

`be` isn't installed in this flow; run `/opt/dev-env/.devcontainer/post-create.sh` in the
container to install it (each `run` starts a fresh container).
