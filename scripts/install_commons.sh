#!/usr/bin/env bash
set -euo pipefail

PYENV_PYTHON_VERSION="3.14"
NVM_VERSION="v0.40.3"
NODE_VERSION="24"
PNPM_VERSION="11"

prompt_yes() {
    local prompt=$1
    local response

    if [ ! -t 0 ]; then
        return 0
    fi

    read -r -p "${prompt} [Y/n]: " response
    response=${response:-Y}
    case "${response}" in
        [yY] | [yY][eE][sS] | "") return 0 ;;
        *) return 1 ;;
    esac
}

detect_os() {
    case "$(uname -s)" in
        Darwin)
            HOST_OS="macos"
            ;;
        Linux)
            HOST_OS="linux"
            if [ -f /etc/os-release ]; then
                # shellcheck disable=SC1091
                . /etc/os-release
                LINUX_ID="${ID:-unknown}"
                LINUX_LIKE="${ID_LIKE:-}"
            else
                LINUX_ID="unknown"
                LINUX_LIKE=""
            fi
            ;;
        *)
            HOST_OS="unsupported"
            ;;
    esac
}

ensure_homebrew() {
    if command -v brew >/dev/null 2>&1; then
        echo "Homebrew is already installed."
        return
    fi

    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    if [ -x /opt/homebrew/bin/brew ]; then
        # shellcheck disable=SC1091
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x /usr/local/bin/brew ]; then
        # shellcheck disable=SC1091
        eval "$(/usr/local/bin/brew shellenv)"
    fi
}

ensure_git() {
    if command -v git >/dev/null 2>&1; then
        echo "git is already installed."
        return
    fi

    echo "Installing git..."
    case "${HOST_OS}" in
        macos)
            brew install git
            ;;
        linux)
            case "${LINUX_ID}" in
                ubuntu | debian | linuxmint | pop)
                    sudo apt-get update
                    sudo apt-get install -y git
                    ;;
                fedora | rhel | centos | rocky | alma | ol)
                    if command -v dnf >/dev/null 2>&1; then
                        sudo dnf install -y git
                    else
                        sudo yum install -y git
                    fi
                    ;;
                amzn)
                    sudo yum install -y git
                    ;;
                arch | manjaro)
                    sudo pacman -S --needed --noconfirm git
                    ;;
                opensuse* | sles)
                    sudo zypper install -y git
                    ;;
                alpine)
                    sudo apk add --no-cache git
                    ;;
                *)
                    echo "Unsupported Linux distribution (${LINUX_ID}). Install git manually."
                    return 1
                    ;;
            esac
            ;;
        *)
            echo "Unsupported OS for git installation."
            return 1
            ;;
    esac
}

init_pyenv() {
    if command -v pyenv >/dev/null 2>&1; then
        return
    fi

    export PYENV_ROOT="${PYENV_ROOT:-${HOME}/.pyenv}"
    export PATH="${PYENV_ROOT}/bin:${PATH}"
}

install_pyenv_build_deps() {
    case "${HOST_OS}" in
        macos)
            if ! xcode-select -p >/dev/null 2>&1; then
                echo "Installing Xcode Command Line Tools..."
                xcode-select --install || true
                echo "Complete the Xcode Command Line Tools install, then re-run this script if pyenv build fails."
            fi

            brew install openssl@3 readline sqlite3 xz tcl-tk@8 libb2 zstd zlib pkgconfig
            ;;
        linux)
            case "${LINUX_ID}" in
                ubuntu | debian | linuxmint | pop)
                    sudo apt-get update
                    sudo apt-get install -y make build-essential libssl-dev zlib1g-dev \
                        libbz2-dev libreadline-dev libsqlite3-dev curl git \
                        libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev \
                        libffi-dev liblzma-dev libzstd-dev
                    ;;
                fedora | rhel | centos | rocky | alma | ol)
                    if command -v dnf >/dev/null 2>&1; then
                        sudo dnf install -y make gcc patch zlib-devel bzip2 bzip2-devel \
                            readline-devel sqlite sqlite-devel openssl-devel tk-devel \
                            libffi-devel xz-devel libuuid-devel gdbm-libs libnsl2 libzstd-devel
                    else
                        sudo yum install -y gcc make patch zlib-devel bzip2 bzip2-devel \
                            readline-devel sqlite sqlite-devel openssl-devel tk-devel \
                            libffi-devel xz-devel zstd-devel
                    fi
                    ;;
                amzn)
                    sudo yum install -y gcc make patch zlib-devel bzip2 bzip2-devel \
                        readline-devel sqlite sqlite-devel openssl11-devel tk-devel \
                        libffi-devel xz-devel zstd-devel
                    ;;
                arch | manjaro)
                    sudo pacman -S --needed --noconfirm base-devel openssl zlib xz tk zstd
                    ;;
                opensuse* | sles)
                    sudo zypper install -y gcc automake bzip2 libbz2-devel xz xz-devel \
                        openssl-devel ncurses-devel readline-devel zlib-devel tk-devel \
                        libffi-devel sqlite3-devel gdbm-devel make findutils patch libzstd-devel
                    ;;
                alpine)
                    sudo apk add --no-cache git bash build-base libffi-dev openssl-dev \
                        bzip2-dev zlib-dev xz-dev readline-dev sqlite-dev tk-dev zstd-dev
                    ;;
                *)
                    echo "Unsupported Linux distribution (${LINUX_ID}). Install pyenv build dependencies manually:"
                    echo "https://github.com/pyenv/pyenv/wiki#suggested-build-environment"
                    ;;
            esac
            ;;
        *)
            echo "Unsupported OS for pyenv build dependencies."
            ;;
    esac
}

install_pyenv() {
    if command -v pyenv >/dev/null 2>&1; then
        echo "pyenv is already installed."
        init_pyenv
        return
    fi

    case "${HOST_OS}" in
        macos)
            brew install pyenv
            ;;
        linux)
            curl -fsSL https://pyenv.run | bash
            ;;
        *)
            echo "Cannot install pyenv on unsupported OS."
            return 1
            ;;
    esac

    init_pyenv
}

setup_pyenv_python() {
    init_pyenv
    eval "$(pyenv init -)"

    if [ "${HOST_OS}" = "macos" ]; then
        export PATH="$(brew --prefix openssl@3)/bin:${PATH}"
        export LDFLAGS="-L$(brew --prefix openssl@3)/lib -L$(brew --prefix readline)/lib -L$(brew --prefix sqlite3)/lib -L$(brew --prefix xz)/lib -L$(brew --prefix zlib)/lib -L$(brew --prefix tcl-tk@8)/lib"
        export CPPFLAGS="-I$(brew --prefix openssl@3)/include -I$(brew --prefix readline)/include -I$(brew --prefix sqlite3)/include -I$(brew --prefix xz)/include -I$(brew --prefix zlib)/include -I$(brew --prefix tcl-tk@8)/include"
        export PKG_CONFIG_PATH="$(brew --prefix openssl@3)/lib/pkgconfig:$(brew --prefix readline)/lib/pkgconfig:$(brew --prefix sqlite3)/lib/pkgconfig:$(brew --prefix xz)/lib/pkgconfig:$(brew --prefix zlib)/lib/pkgconfig:$(brew --prefix tcl-tk@8)/lib/pkgconfig"
    fi

    echo "Installing Python ${PYENV_PYTHON_VERSION} with pyenv..."
    pyenv install -s "${PYENV_PYTHON_VERSION}"
    pyenv global "${PYENV_PYTHON_VERSION}"

    echo "Installing virtualenv..."
    python -m pip install --upgrade pip
    python -m pip install virtualenv
}

init_nvm() {
    export NVM_DIR="${NVM_DIR:-${HOME}/.nvm}"
    if [ -s "${NVM_DIR}/nvm.sh" ]; then
        # shellcheck disable=SC1091
        . "${NVM_DIR}/nvm.sh"
    fi
}

install_nvm() {
    if [ -s "${HOME}/.nvm/nvm.sh" ]; then
        echo "nvm is already installed."
        init_nvm
        return
    fi

    echo "Installing nvm ${NVM_VERSION}..."
    curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh" | bash
    init_nvm
}

setup_node_pnpm() {
    init_nvm

    echo "Installing Node.js ${NODE_VERSION} with nvm..."
    nvm install "${NODE_VERSION}"
    nvm alias default "${NODE_VERSION}"
    nvm use default

    echo "Installing pnpm ${PNPM_VERSION}..."
    npm install -g "pnpm@${PNPM_VERSION}"
}

install_gcloud_interactive_script() {
    curl -fsSL https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir="${HOME}/google-cloud-sdk"
}

install_gcloud() {
    if command -v gcloud >/dev/null 2>&1; then
        echo "gcloud is already installed."
        return
    fi

    echo "Installing Google Cloud CLI..."
    case "${HOST_OS}" in
        macos)
            brew install --cask google-cloud-sdk
            ;;
        linux)
            case "${LINUX_ID}" in
                ubuntu | debian | linuxmint | pop)
                    sudo apt-get update
                    sudo apt-get install -y apt-transport-https ca-certificates gnupg curl
                    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
                        sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
                    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | \
                        sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null
                    sudo apt-get update
                    sudo apt-get install -y google-cloud-cli
                    ;;
                fedora | rhel | centos | rocky | alma | ol | amzn)
                    install_gcloud_interactive_script
                    ;;
                *)
                    install_gcloud_interactive_script
                    ;;
            esac
            ;;
        *)
            echo "Unsupported OS for gcloud installation."
            return 1
            ;;
    esac
}

install_aws_cli_bundle() {
    local tmp_dir arch

    if ! command -v unzip >/dev/null 2>&1; then
        echo "unzip is required to install AWS CLI."
        return 1
    fi

    arch=$(uname -m)
    tmp_dir=$(mktemp -d)
    trap 'rm -rf "${tmp_dir}"' RETURN

    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${arch}.zip" -o "${tmp_dir}/awscliv2.zip"
    unzip -q "${tmp_dir}/awscliv2.zip" -d "${tmp_dir}"
    sudo "${tmp_dir}/aws/install"
}

install_aws_cli() {
    if command -v aws >/dev/null 2>&1; then
        echo "AWS CLI is already installed."
        return
    fi

    echo "Installing AWS CLI..."
    case "${HOST_OS}" in
        macos)
            brew install awscli
            ;;
        linux)
            install_aws_cli_bundle
            ;;
        *)
            echo "Unsupported OS for AWS CLI installation."
            return 1
            ;;
    esac
}

main() {
    detect_os

    case "${HOST_OS}" in
        macos)
            ensure_homebrew
            ;;
        linux)
            echo "Detected Linux (${LINUX_ID:-unknown})."
            ;;
        *)
            echo "Unsupported OS: $(uname -s)"
            exit 1
            ;;
    esac

    ensure_git

    if prompt_yes "Install pyenv?"; then
        install_pyenv_build_deps
        install_pyenv
        setup_pyenv_python
        echo "pyenv setup complete."
    fi

    if prompt_yes "Install nvm?"; then
        install_nvm
        setup_node_pnpm
        echo "nvm setup complete."
    fi

    if prompt_yes "Install Google Cloud CLI?"; then
        install_gcloud
        echo "gcloud setup complete."
    fi

    if prompt_yes "Install AWS CLI?"; then
        install_aws_cli
        echo "AWS CLI setup complete."
    fi

    echo
    echo "Done. Restart your shell or source your shell rc file for PATH changes to take effect."
}

main "$@"
