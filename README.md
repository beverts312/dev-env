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
