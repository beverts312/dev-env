# Dev container for dev-env and the `be` CLI/web app.
# Versions match scripts/install_commons.sh; bump them here.
FROM ghcr.io/astral-sh/uv:0.13.8 AS uv

FROM debian:trixie-slim

ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=1000
ARG PYTHON_VERSION=3.14
ARG NODE_MAJOR=24
ARG PNPM_VERSION=11
ARG KUBECTL_MINOR=v1.37

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC

# Base packages and shell tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        sudo curl ca-certificates gnupg git openssh-client zsh locales \
        less vim tmux jq ripgrep fd-find fzf unzip procps bash-completion \
        build-essential \
    && sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen \
    && ln -s /usr/bin/fdfind /usr/local/bin/fd \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# Third-party apt repos: GitHub CLI, kubectl, Google Cloud CLI, Node.js.
# Google's repo also ships a `kubectl` (gcloud's version dispatcher) whose epoch outranks
# the upstream one, so pin kubectl to pkgs.k8s.io.
RUN install -d -m 0755 /etc/apt/keyrings \
    && arch="$(dpkg --print-architecture)" \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli.gpg \
    && echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && curl -fsSL "https://pkgs.k8s.io/core:/stable:/${KUBECTL_MINOR}/deb/Release.key" \
        | gpg --dearmor -o /etc/apt/keyrings/kubernetes.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/kubernetes.gpg] https://pkgs.k8s.io/core:/stable:/${KUBECTL_MINOR}/deb/ /" \
        > /etc/apt/sources.list.d/kubernetes.list \
    && printf 'Package: kubectl\nPin: origin pkgs.k8s.io\nPin-Priority: 1001\n' \
        > /etc/apt/preferences.d/kubectl \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /etc/apt/keyrings/cloud.google.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh kubectl google-cloud-cli nodejs \
    && npm install -g "pnpm@${PNPM_VERSION}" \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

# AWS CLI v2
RUN tmp="$(mktemp -d)" \
    && curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o "${tmp}/awscliv2.zip" \
    && unzip -q "${tmp}/awscliv2.zip" -d "${tmp}" \
    && "${tmp}/aws/install" \
    && rm -rf "${tmp}"

# uv (manages Python too)
COPY --from=uv /uv /uvx /usr/local/bin/

# Non-root user with passwordless sudo
RUN groupadd --gid "${USER_GID}" "${USERNAME}" \
    && useradd --uid "${USER_UID}" --gid "${USER_GID}" -m -s /bin/zsh "${USERNAME}" \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USERNAME}" \
    && chmod 0440 "/etc/sudoers.d/${USERNAME}" \
    && mkdir -p /workspaces && chown "${USERNAME}:${USERNAME}" /workspaces

USER ${USERNAME}
ENV HOME=/home/${USERNAME}
ENV PATH=${HOME}/.local/bin:${PATH} \
    CLAUDE_CONFIG_DIR=${HOME}/.claude \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=${HOME}/.venvs/be \
    DEV_ENV_HOME=/workspaces/dev-env

# Dirs that devcontainer.json mounts volumes or host config onto, so they're owned by the user
RUN mkdir -p ~/.claude ~/.kube ~/.aws ~/.config/gh ~/.config/gcloud ~/.venvs ~/.local/bin \
    && touch ~/.zshrc

# Python and Claude Code, both in ~/.local/bin
RUN uv python install "${PYTHON_VERSION}" --default \
    && curl -fsSL https://claude.ai/install.sh | bash

WORKDIR /workspaces/dev-env
CMD ["zsh"]
