#!/bin/bash
# ==============================================================================
# DexAI Installation Script — Prerequisites Only
# ==============================================================================
#
# This script installs system prerequisites and sets up the Python environment.
# Configuration (API keys, channels, vault) is handled by `dexai setup`.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/slamb2k/dexai/main/install.sh | bash
#
# Or locally:
#   bash install.sh
#
# Options:
#   --dry-run    Show what would be done without making changes
#   --dir PATH   Override install directory (default: $HOME/dexai)
#   --help       Show this help message
#
# ==============================================================================

set -euo pipefail

# ==============================================================================
# Configuration
# ==============================================================================

DEXAI_REPO="https://github.com/slamb2k/dexai.git"
DEXAI_DIR="${DEXAI_DIR:-$HOME/dexai}"
PYTHON_MIN_VERSION="3.11"
DRY_RUN=false

# Colors (disabled when not connected to a terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' NC=''
fi

# ==============================================================================
# Argument Parsing
# ==============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --dir)
            DEXAI_DIR="$2"
            shift 2
            ;;
        --dir=*)
            DEXAI_DIR="${1#*=}"
            shift
            ;;
        --help|-h)
            echo "DexAI Prerequisite Installer"
            echo ""
            echo "Usage: bash install.sh [options]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would be done without making changes"
            echo "  --dir PATH   Override install directory (default: \$HOME/dexai)"
            echo "  --help       Show this help message"
            echo ""
            echo "After installation, run: dexai setup"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}" >&2
            echo "Run 'bash install.sh --help' for usage." >&2
            exit 1
            ;;
    esac
done

# ==============================================================================
# Helper Functions
# ==============================================================================

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} $*"
    else
        "$@"
    fi
}

check_command() {
    command -v "$1" >/dev/null 2>&1
}

version_gte() {
    # Returns 0 if $1 >= $2
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

# ==============================================================================
# Cleanup Trap
# ==============================================================================

cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ] && [ "$DRY_RUN" = false ]; then
        log_error "Installation failed (exit code $exit_code)."
        log_error "Fix the issue above and re-run this script."
    fi
    exit $exit_code
}
trap cleanup EXIT

# ==============================================================================
# Step 1: Detect OS
# ==============================================================================

detect_os() {
    local uname_out
    uname_out="$(uname -s)"
    case "$uname_out" in
        Linux*)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                OS_TYPE="wsl"
            else
                OS_TYPE="linux"
            fi
            ;;
        Darwin*)
            OS_TYPE="macos"
            ;;
        *)
            log_error "Unsupported OS: $uname_out"
            exit 1
            ;;
    esac
    log_info "Detected OS: $OS_TYPE"
}

# ==============================================================================
# Step 2: Check / Install System Prerequisites
# ==============================================================================

check_git() {
    if check_command git; then
        log_success "git found"
        return 0
    fi
    log_error "git is not installed."
    case "$OS_TYPE" in
        macos) echo "  Install with: brew install git" ;;
        *)     echo "  Install with: sudo apt install git" ;;
    esac
    exit 1
}

check_curl() {
    if check_command curl; then
        log_success "curl found"
        return 0
    fi
    log_error "curl is not installed."
    case "$OS_TYPE" in
        macos) echo "  Install with: brew install curl" ;;
        *)     echo "  Install with: sudo apt install curl" ;;
    esac
    exit 1
}

check_python() {
    if ! check_command python3; then
        log_error "Python 3 not found. Python $PYTHON_MIN_VERSION+ is required."
        case "$OS_TYPE" in
            macos) echo "  Install with: brew install python@3.12" ;;
            *)     echo "  Install with: sudo apt install python3.12 python3.12-venv" ;;
        esac
        exit 1
    fi

    local py_version
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if version_gte "$py_version" "$PYTHON_MIN_VERSION"; then
        log_success "Python $py_version found"
    else
        log_error "Python $PYTHON_MIN_VERSION+ required, found $py_version"
        exit 1
    fi
}

check_uv() {
    if check_command uv; then
        log_success "uv package manager found"
        return 0
    fi

    log_info "Installing uv (fast Python package manager)..."
    if run_cmd curl -LsSf https://astral.sh/uv/install.sh | sh; then
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        if check_command uv; then
            log_success "uv installed successfully"
            return 0
        fi
    fi

    log_error "Failed to install uv."
    echo "  Manual install: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

check_docker() {
    # Docker is optional — just report status
    if check_command docker && docker info >/dev/null 2>&1; then
        log_success "Docker found and running (optional)"
    else
        log_info "Docker not found or not running (optional — needed only for container deployment)"
    fi
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    echo ""
    check_git
    check_curl
    check_python
    check_uv
    check_docker
    echo ""
    log_success "All required prerequisites met"
}

# ==============================================================================
# Step 3: Clone or Update Repository
# ==============================================================================

setup_repository() {
    if [ -d "$DEXAI_DIR" ]; then
        log_info "DexAI directory exists at $DEXAI_DIR"
        if [ -d "$DEXAI_DIR/.git" ]; then
            log_info "Updating existing repository..."
            run_cmd git -C "$DEXAI_DIR" pull --ff-only 2>/dev/null \
                || log_warn "Could not update — continuing with existing version"
        fi
    else
        log_info "Cloning DexAI to $DEXAI_DIR..."
        run_cmd git clone "$DEXAI_REPO" "$DEXAI_DIR"
    fi

    if [ "$DRY_RUN" = true ] && [ ! -d "$DEXAI_DIR" ]; then
        log_info "Dry run: would work in $DEXAI_DIR"
    else
        cd "$DEXAI_DIR"
        log_success "Working in $DEXAI_DIR"
    fi
}

# ==============================================================================
# Step 4: Create Virtual Environment and Install Dependencies
# ==============================================================================

setup_python_env() {
    local venv_dir="$DEXAI_DIR/.venv"

    # Create venv if it does not exist
    if [ ! -d "$venv_dir" ]; then
        log_info "Creating virtual environment..."
        if ! run_cmd uv venv "$venv_dir"; then
            log_error "Failed to create virtual environment."
            echo "  Try: uv venv $venv_dir"
            exit 1
        fi
        log_success "Virtual environment created"
    else
        log_success "Virtual environment exists"
    fi

    # Activate venv
    if [ "$DRY_RUN" = false ]; then
        # shellcheck disable=SC1091
        source "$venv_dir/bin/activate"
    fi

    # Install all Python dependencies
    log_info "Installing Python dependencies (this may take a minute)..."
    run_cmd uv pip install -e ".[all]"
    log_success "Python dependencies installed"
}

# ==============================================================================
# Step 5: Create Minimal .env if Missing
# ==============================================================================

ensure_env_file() {
    local env_file="$DEXAI_DIR/.env"

    if [ -f "$env_file" ]; then
        log_success ".env file exists"
        return 0
    fi

    log_info "Creating .env file from template..."
    if [ -f "$DEXAI_DIR/.env.example" ]; then
        run_cmd cp "$DEXAI_DIR/.env.example" "$env_file"
    else
        run_cmd touch "$env_file"
    fi

    # Set restrictive permissions
    if [ "$DRY_RUN" = false ]; then
        chmod 600 "$env_file" 2>/dev/null || true
    fi

    log_success ".env file created"
}

# ==============================================================================
# Step 6: Create Data Directories
# ==============================================================================

ensure_data_dirs() {
    if [ "$DRY_RUN" = false ]; then
        mkdir -p "$DEXAI_DIR/data"
        mkdir -p "$DEXAI_DIR/memory/logs"
        chmod 700 "$DEXAI_DIR/data" 2>/dev/null || true
    else
        echo -e "${YELLOW}[DRY-RUN]${NC} Would create data/ and memory/logs/ directories"
    fi
    log_success "Data directories ready"
}

# ==============================================================================
# Main
# ==============================================================================

main() {
    echo ""
    echo -e "${BOLD}DexAI Prerequisite Installer${NC}"
    echo "==============================="
    echo ""

    detect_os
    check_prerequisites
    setup_repository
    setup_python_env
    ensure_env_file
    ensure_data_dirs

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Prerequisites installed successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""

    if [ "$DRY_RUN" = true ]; then
        log_info "Dry run complete. No changes were made."
        exit 0
    fi

    echo -e "Next step: configure your installation."
    echo ""
    echo -e "  ${CYAN}cd $DEXAI_DIR${NC}"
    echo -e "  ${CYAN}source .venv/bin/activate${NC}"
    echo -e "  ${CYAN}dexai setup${NC}"
    echo ""
    echo "Or start the dashboard directly:"
    echo -e "  ${CYAN}dexai dashboard${NC}"
    echo ""
}

main "$@"
