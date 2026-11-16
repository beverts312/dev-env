#!/usr/bin/env bash
# Runs once after the dev container is created: installs be's Python and web deps,
# builds the web app, and puts the `be` CLI on PATH (what configure.py's install_cli does).
set -euo pipefail

cd "$(dirname "$0")/.."

# Docker creates the node_modules volume's mount point as root
sudo chown "$(id -u):$(id -g)" be/web/node_modules

git config --global --add safe.directory "$PWD"

uv sync --project be --all-extras

pnpm -C be/web install --frozen-lockfile
pnpm -C be/web build

uv tool install --force --editable ./be

echo
echo "Ready. Try: be --help, be server --host 0.0.0.0, pnpm -C be/web dev --host"
