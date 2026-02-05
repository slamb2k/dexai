#!/bin/bash
# ==============================================================================
# DexAI Installation Script
# ==============================================================================
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/slamb2k/dexai/main/install.sh | bash
#
# Or locally:
#   bash install.sh
#
# Options:
#   --dry-run                    Show what would be done without making changes
#   --tailscale-key KEY          Tailscale auth key for automatic VPN setup
#   --tailscale-hostname NAME    Tailscale machine name (default: dexai)
#   --help                       Show this help message
#
# ==============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration
DEXAI_REPO="https://github.com/slamb2k/dexai.git"
DEXAI_DIR="${DEXAI_DIR:-$HOME/dexai}"
PYTHON_MIN_VERSION="3.11"
MANUAL_DOCS_URL="https://github.com/slamb2k/dexai/blob/main/docs/installation.md"

# Flags
DRY_RUN=false
INTERACTIVE=false

# CLI-provided values (for non-interactive installs)
CLI_TAILSCALE_KEY=""
CLI_TAILSCALE_HOSTNAME=""

# Check if we can interact with terminal (fails in non-TTY contexts like Claude Code)
# Test by checking if /dev/tty is a readable character device
if [ -c /dev/tty ] && [ -r /dev/tty ]; then
    # Double-check by trying to write to it (empty string)
    if (printf '' >/dev/tty) 2>/dev/null; then
        INTERACTIVE=true
    fi
fi

# Detected tools (set during checks)
PKG_MANAGER=""
JS_PKG_MANAGER=""
DOCKER_COMPOSE_CMD=""
HAS_DOCKER=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --tailscale-key)
            CLI_TAILSCALE_KEY="$2"
            shift 2
            ;;
        --tailscale-key=*)
            CLI_TAILSCALE_KEY="${1#*=}"
            shift
            ;;
        --tailscale-hostname)
            CLI_TAILSCALE_HOSTNAME="$2"
            shift 2
            ;;
        --tailscale-hostname=*)
            CLI_TAILSCALE_HOSTNAME="${1#*=}"
            shift
            ;;
        --help)
            echo "DexAI Installation Script"
            echo ""
            echo "Usage: bash install.sh [options]"
            echo ""
            echo "Options:"
            echo "  --dry-run                    Show what would be done without making changes"
            echo "  --tailscale-key KEY          Tailscale auth key for automatic VPN setup"
            echo "  --tailscale-hostname NAME    Tailscale machine name (default: dexai)"
            echo "  --help                       Show this help message"
            echo ""
            echo "Examples:"
            echo "  bash install.sh --tailscale-key tskey-auth-xxx"
            echo "  bash install.sh --tailscale-key tskey-auth-xxx --tailscale-hostname my-dexai"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# ==============================================================================
# Helper Functions
# ==============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

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

prompt_install() {
    local name="$1"
    local install_cmd="$2"
    local install_url="$3"

    echo ""
    echo -e "${YELLOW}$name is not installed.${NC}"
    echo ""
    if [ -n "$install_cmd" ]; then
        echo "  Install automatically: $install_cmd"
    fi
    if [ -n "$install_url" ]; then
        echo "  Manual install: $install_url"
    fi
    echo ""

    if [ -n "$install_cmd" ]; then
        if [ "$INTERACTIVE" = true ]; then
            read -p "Would you like to install $name now? [Y/n] " -n 1 -r REPLY </dev/tty
            echo ""
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                return 0  # Yes, install
            fi
        else
            # Non-interactive: default to yes for dependency installation
            log_info "Non-interactive mode: auto-installing $name"
            return 0
        fi
    fi
    return 1  # No, skip
}

# ==============================================================================
# Prerequisite Checks (Always Required)
# ==============================================================================

log_info "Checking prerequisites..."

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Linux*)     OS_TYPE="linux" ;;
    Darwin*)    OS_TYPE="macos" ;;
    *)          log_error "Unsupported OS: $OS"; exit 1 ;;
esac
log_info "Detected OS: $OS_TYPE"

# Check Python version (always required)
if check_command python3; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if version_gte "$PYTHON_VERSION" "$PYTHON_MIN_VERSION"; then
        log_success "Python $PYTHON_VERSION found"
    else
        log_error "Python $PYTHON_MIN_VERSION+ required, found $PYTHON_VERSION"
        exit 1
    fi
else
    log_error "Python 3 not found. Please install Python $PYTHON_MIN_VERSION or later."
    if [ "$OS_TYPE" = "macos" ]; then
        echo "  Install with: brew install python@3.11"
    else
        echo "  Install with: sudo apt install python3.11 python3.11-venv"
    fi
    exit 1
fi

# Check git (always required)
if check_command git; then
    log_success "Git found"
else
    log_error "Git not found. Please install git."
    if [ "$OS_TYPE" = "macos" ]; then
        echo "  Install with: brew install git"
    else
        echo "  Install with: sudo apt install git"
    fi
    exit 1
fi

# ==============================================================================
# Detect Python Package Manager
# ==============================================================================

detect_python_pkg_manager() {
    if check_command uv; then
        PKG_MANAGER="uv"
        log_success "uv package manager found (fastest)"
        return 0
    elif check_command pip3; then
        PKG_MANAGER="pip3"
        log_warn "uv not found, using pip3 (slower)"
        return 0
    elif check_command pip; then
        PKG_MANAGER="pip"
        log_warn "uv not found, using pip (slower)"
        return 0
    elif python3 -m pip --version >/dev/null 2>&1; then
        PKG_MANAGER="python3 -m pip"
        log_warn "No standalone pip found, using python3 -m pip (slower)"
        return 0
    fi
    return 1
}

if ! detect_python_pkg_manager; then
    log_warn "No Python package manager found"
    if prompt_install "uv (fast Python package manager)" \
        "curl -LsSf https://astral.sh/uv/install.sh | sh" \
        "https://docs.astral.sh/uv/getting-started/installation/"; then
        log_info "Installing uv..."
        if curl -LsSf https://astral.sh/uv/install.sh | sh; then
            export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
            if check_command uv; then
                PKG_MANAGER="uv"
                log_success "uv installed successfully"
            else
                log_error "uv installed but not found in PATH. Please restart your terminal and re-run this script."
                exit 1
            fi
        else
            log_error "Failed to install uv"
            exit 1
        fi
    else
        log_error "No package manager available. Install uv or pip to continue."
        exit 1
    fi
fi

# ==============================================================================
# Detect JavaScript Package Manager (for local frontend)
# ==============================================================================

detect_js_pkg_manager() {
    if check_command bun; then
        JS_PKG_MANAGER="bun"
        log_success "bun package manager found (fastest)"
        return 0
    elif check_command pnpm; then
        JS_PKG_MANAGER="pnpm"
        log_success "pnpm package manager found"
        return 0
    elif check_command npm; then
        JS_PKG_MANAGER="npm"
        log_success "npm package manager found"
        return 0
    fi
    return 1
}

offer_js_pkg_manager() {
    log_warn "No JavaScript package manager found (npm/pnpm/bun)"
    if prompt_install "bun (fast JavaScript runtime & package manager)" \
        "curl -fsSL https://bun.sh/install | bash" \
        "https://bun.sh/docs/installation"; then
        log_info "Installing bun..."
        if curl -fsSL https://bun.sh/install | bash; then
            export BUN_INSTALL="$HOME/.bun"
            export PATH="$BUN_INSTALL/bin:$PATH"
            if check_command bun; then
                JS_PKG_MANAGER="bun"
                log_success "bun installed successfully"
                return 0
            else
                log_error "bun installed but not found in PATH. Please restart your terminal."
                return 1
            fi
        else
            log_error "Failed to install bun"
            return 1
        fi
    fi
    return 1
}

# ==============================================================================
# Detect Docker and Docker Compose
# ==============================================================================

detect_docker() {
    if ! check_command docker; then
        return 1
    fi

    # Check if Docker daemon is running
    if ! docker info >/dev/null 2>&1; then
        log_warn "Docker found but daemon is not running"
        return 1
    fi

    HAS_DOCKER=true
    log_success "Docker found and running"
    return 0
}

detect_docker_compose() {
    # Prefer docker compose v2 (plugin)
    if docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker compose"
        log_success "Docker Compose v2 found (docker compose)"
        return 0
    fi

    # Fall back to docker-compose v1 (standalone)
    if check_command docker-compose; then
        DOCKER_COMPOSE_CMD="docker-compose"
        log_success "Docker Compose v1 found (docker-compose)"
        return 0
    fi

    return 1
}

offer_docker_install() {
    log_warn "Docker is not installed or not running"
    echo ""
    echo "Docker is required for container-based deployment."
    echo ""
    if [ "$OS_TYPE" = "macos" ]; then
        echo "  Install Docker Desktop: https://docs.docker.com/desktop/install/mac-install/"
        echo "  Or with Homebrew: brew install --cask docker"
    else
        echo "  Install Docker Engine: https://docs.docker.com/engine/install/"
        echo "  Quick install: curl -fsSL https://get.docker.com | sh"
    fi
    echo ""

    if [ "$OS_TYPE" = "linux" ]; then
        if [ "$INTERACTIVE" = true ]; then
            read -p "Would you like to install Docker now? [Y/n] " -n 1 -r REPLY </dev/tty
            echo ""
        else
            # Non-interactive: skip Docker auto-install (requires sudo)
            log_info "Non-interactive mode: skipping Docker auto-install"
            REPLY="n"
        fi
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            log_info "Installing Docker..."
            if curl -fsSL https://get.docker.com | sh; then
                # Add current user to docker group
                if [ -n "${SUDO_USER:-}" ]; then
                    sudo usermod -aG docker "$SUDO_USER"
                else
                    sudo usermod -aG docker "$USER"
                fi
                log_success "Docker installed"
                log_warn "You may need to log out and back in for group changes to take effect"

                # Start docker service
                if check_command systemctl; then
                    sudo systemctl enable docker
                    sudo systemctl start docker
                fi

                HAS_DOCKER=true
                return 0
            else
                log_error "Failed to install Docker"
                return 1
            fi
        fi
    fi
    return 1
}

# ==============================================================================
# Clone or Update Repository
# ==============================================================================

if [ -d "$DEXAI_DIR" ]; then
    log_info "DexAI directory exists at $DEXAI_DIR"
    if [ -d "$DEXAI_DIR/.git" ]; then
        log_info "Updating existing repository..."
        run_cmd git -C "$DEXAI_DIR" pull --ff-only || log_warn "Could not update, continuing with existing version"
    fi
else
    log_info "Cloning DexAI to $DEXAI_DIR..."
    run_cmd git clone "$DEXAI_REPO" "$DEXAI_DIR"
fi

# Change to project directory (use current dir if dry-run and target doesn't exist)
if [ "$DRY_RUN" = true ] && [ ! -d "$DEXAI_DIR" ]; then
    log_info "Working in $DEXAI_DIR (dry-run, using current directory)"
else
    cd "$DEXAI_DIR"
    log_success "Working in $DEXAI_DIR"
fi

# ==============================================================================
# Create Virtual Environment
# ==============================================================================

VENV_DIR="$DEXAI_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    log_info "Creating virtual environment..."

    # Prefer uv venv (faster, no system venv dependency)
    if [ "$PKG_MANAGER" = "uv" ]; then
        run_cmd uv venv "$VENV_DIR"
    else
        # Fall back to python3 -m venv
        if ! run_cmd python3 -m venv "$VENV_DIR" 2>/dev/null; then
            log_error "Failed to create virtual environment."
            log_error "On Debian/Ubuntu, install the venv package:"
            echo "  sudo apt install python3.$(python3 -c 'import sys; print(sys.version_info.minor)')-venv"
            echo ""
            echo "Or install uv (recommended - no system venv needed):"
            echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            exit 1
        fi
    fi

    log_success "Virtual environment created"
else
    log_success "Virtual environment exists"
fi

# Activate venv
if [ "$DRY_RUN" = false ]; then
    source "$VENV_DIR/bin/activate"
fi

# ==============================================================================
# Install Core Python Dependencies + Channels
# ==============================================================================

log_info "Installing core dependencies with channel support..."

# Install with channels extra so all messaging platforms are available during setup
case "$PKG_MANAGER" in
    uv)
        run_cmd uv pip install -e ".[channels]"
        ;;
    pip3)
        run_cmd pip3 install -e ".[channels]"
        ;;
    pip)
        run_cmd pip install -e ".[channels]"
        ;;
    "python3 -m pip")
        run_cmd python3 -m pip install -e ".[channels]"
        ;;
esac

log_success "Core dependencies installed (includes Telegram, Discord, Slack)"

# ==============================================================================
# Install Additional Optional Dependencies (if configured)
# ==============================================================================

# Note: Channel dependencies (Telegram, Discord, Slack) are already installed above.
# This section handles other optional features like Office integration.

EXTRAS_TO_INSTALL=""

# Check office_integration.yaml for office features
OFFICE_CONFIG="$DEXAI_DIR/args/office_integration.yaml"
if [ -f "$OFFICE_CONFIG" ]; then
    if grep -q "enabled: true" "$OFFICE_CONFIG"; then
        EXTRAS_TO_INSTALL="office"
        log_info "Office integration enabled in config"
    fi
fi

# Install detected extras
if [ -n "$EXTRAS_TO_INSTALL" ]; then
    log_info "Installing optional dependencies: $EXTRAS_TO_INSTALL..."

    case "$PKG_MANAGER" in
        uv)
            run_cmd uv pip install -e ".[$EXTRAS_TO_INSTALL]"
            ;;
        pip3)
            run_cmd pip3 install -e ".[$EXTRAS_TO_INSTALL]"
            ;;
        pip)
            run_cmd pip install -e ".[$EXTRAS_TO_INSTALL]"
            ;;
        "python3 -m pip")
            run_cmd python3 -m pip install -e ".[$EXTRAS_TO_INSTALL]"
            ;;
    esac

    log_success "Optional dependencies installed"
fi

# ==============================================================================
# Generate Master Key (if not exists)
# ==============================================================================

ENV_FILE="$DEXAI_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    log_info "Creating .env file from template..."
    if [ -f "$DEXAI_DIR/.env.example" ]; then
        run_cmd cp "$DEXAI_DIR/.env.example" "$ENV_FILE"
    else
        run_cmd touch "$ENV_FILE"
    fi
fi

# Check for master key
if ! grep -q "^DEXAI_MASTER_KEY=" "$ENV_FILE" 2>/dev/null || grep -q "^DEXAI_MASTER_KEY=$" "$ENV_FILE" 2>/dev/null; then
    log_info "Generating secure master key..."
    if [ "$DRY_RUN" = false ]; then
        MASTER_KEY=$(openssl rand -hex 32)
        if grep -q "^DEXAI_MASTER_KEY=" "$ENV_FILE"; then
            sed -i.bak "s/^DEXAI_MASTER_KEY=.*/DEXAI_MASTER_KEY=$MASTER_KEY/" "$ENV_FILE"
            rm -f "$ENV_FILE.bak"
        else
            echo "DEXAI_MASTER_KEY=$MASTER_KEY" >> "$ENV_FILE"
        fi
        log_success "Master key generated"
    else
        echo -e "${YELLOW}[DRY-RUN]${NC} Would generate master key"
    fi
else
    log_success "Master key already configured"
fi

# ==============================================================================
# Initialize Databases
# ==============================================================================

log_info "Initializing databases..."

if [ "$DRY_RUN" = false ]; then
    mkdir -p "$DEXAI_DIR/data"
    mkdir -p "$DEXAI_DIR/memory/logs"

    python3 -c "
import sys
sys.path.insert(0, '$DEXAI_DIR')

# Initialize dashboard database
try:
    from tools.dashboard.backend.database import init_db
    init_db()
    print('  Dashboard database initialized')
except Exception as e:
    print(f'  Warning: Could not initialize dashboard database: {e}')

# Initialize memory database
try:
    from tools.memory.memory_db import get_connection
    conn = get_connection()
    conn.close()
    print('  Memory database initialized')
except Exception as e:
    print(f'  Warning: Could not initialize memory database: {e}')

# Initialize security databases (vault)
try:
    from tools.security.vault import get_connection as get_vault_connection
    conn = get_vault_connection()
    conn.close()
    print('  Vault initialized')
except Exception as e:
    print(f'  Warning: Could not initialize vault: {e}')

print('Database initialization complete')
"
    log_success "Databases initialized"
else
    echo -e "${YELLOW}[DRY-RUN]${NC} Would initialize databases"
fi

# ==============================================================================
# Set File Permissions
# ==============================================================================

log_info "Setting file permissions..."

if [ "$DRY_RUN" = false ]; then
    chmod 700 "$DEXAI_DIR/data" 2>/dev/null || true
    chmod 600 "$ENV_FILE" 2>/dev/null || true
    log_success "Permissions set"
else
    echo -e "${YELLOW}[DRY-RUN]${NC} Would set restrictive permissions on data/ and .env"
fi

# ==============================================================================
# Installation Complete - Choose Deployment Method
# ==============================================================================

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  DexAI Base Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [ "$DRY_RUN" = true ]; then
    log_info "Dry run complete. No changes were made."
    exit 0
fi

# ==============================================================================
# Deployment Choice Menu
# ==============================================================================

show_deployment_menu() {
    echo -e "${BOLD}How would you like to run DexAI?${NC}"
    echo ""
    echo -e "  ${CYAN}1)${NC} ${BOLD}Local Development${NC}"
    echo "     Run backend and frontend directly on your machine."
    echo "     Best for development and testing."
    echo ""
    echo -e "  ${CYAN}2)${NC} ${BOLD}Docker Compose${NC}"
    echo "     Run everything in containers."
    echo "     Best for production and easy management."
    echo ""
    echo -e "  ${CYAN}3)${NC} ${BOLD}Exit (Manual Setup)${NC}"
    echo "     Exit now and set up manually later."
    echo "     Documentation: $MANUAL_DOCS_URL"
    echo ""
}

# Function to install and run locally
install_local() {
    log_info "Setting up local development environment..."

    # Check/install JS package manager for frontend
    if ! detect_js_pkg_manager; then
        if ! offer_js_pkg_manager; then
            log_warn "Skipping frontend installation (no JS package manager)"
            log_warn "You can install the frontend later with: cd tools/dashboard/frontend && npm install"
        fi
    fi

    # Install frontend dependencies if we have a JS package manager
    FRONTEND_DIR="$DEXAI_DIR/tools/dashboard/frontend"
    if [ -n "$JS_PKG_MANAGER" ] && [ -d "$FRONTEND_DIR" ]; then
        log_info "Installing frontend dependencies..."

        case "$JS_PKG_MANAGER" in
            bun)
                run_cmd bun install --cwd "$FRONTEND_DIR"
                ;;
            pnpm)
                run_cmd pnpm install --dir "$FRONTEND_DIR"
                ;;
            npm)
                run_cmd npm install --prefix "$FRONTEND_DIR"
                ;;
        esac

        log_success "Frontend dependencies installed"
    fi

    log_success "Local environment ready!"
    echo ""
    echo "To start development servers later, run:"
    echo -e "  ${BLUE}cd $DEXAI_DIR && source .venv/bin/activate && make dev${NC}"
    echo ""

    return 0
}

# Function to deploy with Docker Compose
install_docker() {
    log_info "Setting up Docker deployment..."

    # Check Docker
    if ! detect_docker; then
        if ! offer_docker_install; then
            log_error "Docker is required for container deployment."
            return 1
        fi
    fi

    # Check Docker Compose
    if ! detect_docker_compose; then
        log_error "Docker Compose not found."
        echo ""
        echo "Docker Compose is required. Install options:"
        if [ "$OS_TYPE" = "macos" ]; then
            echo "  Docker Desktop includes Docker Compose"
            echo "  Install: https://docs.docker.com/desktop/install/mac-install/"
        else
            echo "  Install Docker Compose plugin:"
            echo "    sudo apt install docker-compose-plugin"
            echo "  Or standalone:"
            echo "    sudo curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-linux-\$(uname -m) -o /usr/local/bin/docker-compose"
            echo "    sudo chmod +x /usr/local/bin/docker-compose"
        fi
        return 1
    fi

    # Ask about remote access setup
    DOCKER_PROFILES=""
    SETUP_URL="http://localhost:3000/setup"
    TAILSCALE_CONFIGURED=false
    TS_HOSTNAME="${CLI_TAILSCALE_HOSTNAME:-dexai}"

    # Check if Tailscale was configured via CLI
    if [ -n "$CLI_TAILSCALE_KEY" ]; then
        log_info "Tailscale auth key provided via CLI"
        DOCKER_PROFILES="--profile tailscale"

        # Save to .env
        if ! grep -q "^TAILSCALE_AUTHKEY=" "$ENV_FILE" 2>/dev/null; then
            echo "TAILSCALE_AUTHKEY=$CLI_TAILSCALE_KEY" >> "$ENV_FILE"
        else
            sed -i.bak "s/^TAILSCALE_AUTHKEY=.*/TAILSCALE_AUTHKEY=$CLI_TAILSCALE_KEY/" "$ENV_FILE"
            rm -f "$ENV_FILE.bak"
        fi

        # Save hostname to .env
        if ! grep -q "^TAILSCALE_HOSTNAME=" "$ENV_FILE" 2>/dev/null; then
            echo "TAILSCALE_HOSTNAME=$TS_HOSTNAME" >> "$ENV_FILE"
        else
            sed -i.bak "s/^TAILSCALE_HOSTNAME=.*/TAILSCALE_HOSTNAME=$TS_HOSTNAME/" "$ENV_FILE"
            rm -f "$ENV_FILE.bak"
        fi

        log_success "Tailscale configured: hostname=$TS_HOSTNAME"
        TAILSCALE_CONFIGURED=true
    fi

    if [ "$INTERACTIVE" = true ]; then
        echo ""
        echo -e "${BOLD}Remote Access Setup (optional)${NC}"
        echo ""
        echo "  Caddy provides a reverse proxy with automatic HTTPS."
        echo "  Tailscale provides secure private network access."
        echo ""

        # Ask about Caddy
        read -p "Enable Caddy reverse proxy? (recommended for remote access) [y/N] " -n 1 -r REPLY </dev/tty
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if [ -n "$DOCKER_PROFILES" ]; then
                DOCKER_PROFILES="$DOCKER_PROFILES --profile proxy"
            else
                DOCKER_PROFILES="--profile proxy"
            fi

            # Get domain/hostname
            echo ""
            read -p "Enter hostname or domain (e.g., dexai.example.com or my-server): " DOMAIN </dev/tty
            if [ -n "$DOMAIN" ]; then
                export DEXAI_DOMAIN="$DOMAIN"
                # Add to .env if not already there
                if ! grep -q "^DEXAI_DOMAIN=" "$ENV_FILE" 2>/dev/null; then
                    echo "DEXAI_DOMAIN=$DOMAIN" >> "$ENV_FILE"
                else
                    sed -i.bak "s/^DEXAI_DOMAIN=.*/DEXAI_DOMAIN=$DOMAIN/" "$ENV_FILE"
                    rm -f "$ENV_FILE.bak"
                fi
                log_success "Domain set to: $DOMAIN"
                SETUP_URL="http://$DOMAIN/setup"
            fi
        fi

        # Ask about Tailscale (skip if already configured via CLI)
        if [ "$TAILSCALE_CONFIGURED" = false ]; then
            echo ""
            read -p "Enable Tailscale for secure private access? [y/N] " -n 1 -r REPLY </dev/tty
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                if [ -n "$DOCKER_PROFILES" ]; then
                    DOCKER_PROFILES="$DOCKER_PROFILES --profile tailscale"
                else
                    DOCKER_PROFILES="--profile tailscale"
                fi

                echo ""
                echo -e "${YELLOW}Tailscale Setup${NC}"
                echo ""
                echo "You'll need a Tailscale auth key from: https://login.tailscale.com/admin/settings/keys"
                echo ""
                read -p "Enter Tailscale auth key (or press Enter to skip): " TS_KEY </dev/tty
                if [ -n "$TS_KEY" ]; then
                    # Add to .env
                    if ! grep -q "^TAILSCALE_AUTHKEY=" "$ENV_FILE" 2>/dev/null; then
                        echo "TAILSCALE_AUTHKEY=$TS_KEY" >> "$ENV_FILE"
                    else
                        sed -i.bak "s/^TAILSCALE_AUTHKEY=.*/TAILSCALE_AUTHKEY=$TS_KEY/" "$ENV_FILE"
                        rm -f "$ENV_FILE.bak"
                    fi
                    log_success "Tailscale auth key configured"

                    # Get Tailscale hostname
                    echo ""
                    read -p "Enter Tailscale machine name (default: dexai): " TS_INPUT_HOSTNAME </dev/tty
                    if [ -n "$TS_INPUT_HOSTNAME" ]; then
                        TS_HOSTNAME="$TS_INPUT_HOSTNAME"
                    fi

                    # Save hostname to .env
                    if ! grep -q "^TAILSCALE_HOSTNAME=" "$ENV_FILE" 2>/dev/null; then
                        echo "TAILSCALE_HOSTNAME=$TS_HOSTNAME" >> "$ENV_FILE"
                    else
                        sed -i.bak "s/^TAILSCALE_HOSTNAME=.*/TAILSCALE_HOSTNAME=$TS_HOSTNAME/" "$ENV_FILE"
                        rm -f "$ENV_FILE.bak"
                    fi

                    log_success "Tailscale hostname set to: $TS_HOSTNAME"
                    TAILSCALE_CONFIGURED=true
                else
                    log_warn "Tailscale will start but needs manual authentication"
                    echo "Run: docker exec -it dexai-tailscale tailscale up"
                fi
            fi
        else
            log_info "Tailscale already configured via CLI (hostname: $TS_HOSTNAME)"
        fi
    fi

    log_info "Building and starting containers..."

    # Build images
    if ! $DOCKER_COMPOSE_CMD $DOCKER_PROFILES build; then
        log_error "Failed to build Docker images"
        return 1
    fi

    # Start containers
    if ! $DOCKER_COMPOSE_CMD $DOCKER_PROFILES up -d; then
        log_error "Failed to start containers"
        return 1
    fi

    log_success "Docker deployment complete!"
    echo ""
    echo "Services running:"
    if [[ "$DOCKER_PROFILES" == *"proxy"* ]]; then
        echo "  - DexAI: http://${DEXAI_DOMAIN:-localhost} (via Caddy)"
        echo "    Caddy routes /api/* to backend, /* to frontend"
    else
        echo "  - Backend:  http://localhost:8080"
        echo "  - Frontend: http://localhost:3000"
    fi
    if [[ "$DOCKER_PROFILES" == *"tailscale"* ]]; then
        echo "  - Tailscale: hostname=$TS_HOSTNAME"

        # Wait for Tailscale to connect and get the actual URL
        log_info "Waiting for Tailscale to connect..."
        sleep 3

        # Try to get the Tailscale FQDN
        TAILSCALE_FQDN=""
        for i in {1..10}; do
            TAILSCALE_FQDN=$(docker exec dexai-tailscale tailscale status --json 2>/dev/null | grep -o '"DNSName":"[^"]*"' | head -1 | cut -d'"' -f4 | sed 's/\.$//' || true)
            if [ -n "$TAILSCALE_FQDN" ]; then
                break
            fi
            sleep 2
        done

        if [ -n "$TAILSCALE_FQDN" ]; then
            log_success "Tailscale connected!"
            echo ""
            echo -e "  ${GREEN}Tailscale URL:${NC} ${CYAN}https://$TAILSCALE_FQDN${NC}"
            SETUP_URL="https://$TAILSCALE_FQDN/setup"
        else
            echo ""
            echo -e "${YELLOW}Note:${NC} Tailscale is starting up."
            echo "  Expected URL: https://$TS_HOSTNAME.<your-tailnet>.ts.net"
            echo ""
            echo "  To check status: docker exec dexai-tailscale tailscale status"
            if [ -z "$CLI_TAILSCALE_KEY" ] && [ "$TAILSCALE_CONFIGURED" = false ]; then
                echo "  To authenticate: docker exec -it dexai-tailscale tailscale up"
            fi
        fi

        if [[ "$DOCKER_PROFILES" != *"proxy"* ]]; then
            echo ""
            echo -e "${CYAN}Tailscale Serve is configured as reverse proxy:${NC}"
            echo "  Routes /api/* to backend, /* to frontend automatically"
        fi
    fi
    echo ""
    echo "Useful commands:"
    echo -e "  ${BLUE}cd $DEXAI_DIR && $DOCKER_COMPOSE_CMD $DOCKER_PROFILES logs -f${NC}  # View logs"
    echo -e "  ${BLUE}cd $DEXAI_DIR && $DOCKER_COMPOSE_CMD $DOCKER_PROFILES down${NC}      # Stop services"
    echo -e "  ${BLUE}cd $DEXAI_DIR && $DOCKER_COMPOSE_CMD $DOCKER_PROFILES ps${NC}        # Check status"
    if [[ "$DOCKER_PROFILES" == *"tailscale"* ]]; then
        echo -e "  ${BLUE}docker exec dexai-tailscale tailscale status${NC}             # Tailscale status"
    fi
    echo ""

    # Export setup URL for wizard launcher
    export SETUP_URL

    return 0
}

# Function to open URL in browser (cross-platform)
open_browser() {
    local url="$1"

    # Try various methods to open browser
    if check_command xdg-open; then
        # Linux with X11/Wayland
        xdg-open "$url" 2>/dev/null &
        return 0
    elif check_command open; then
        # macOS
        open "$url" 2>/dev/null &
        return 0
    elif check_command wslview; then
        # WSL (Windows Subsystem for Linux)
        wslview "$url" 2>/dev/null &
        return 0
    elif [ -n "${BROWSER:-}" ]; then
        # Use $BROWSER env var if set
        "$BROWSER" "$url" 2>/dev/null &
        return 0
    elif check_command sensible-browser; then
        # Debian/Ubuntu fallback
        sensible-browser "$url" 2>/dev/null &
        return 0
    fi

    return 1
}

# Function to launch the setup wizard
launch_wizard() {
    echo ""
    log_info "Launching setup wizard..."
    echo ""

    # Check if running in Docker - wizard runs differently
    if [ "${DOCKER_DEPLOYMENT:-false}" = true ]; then
        # Use SETUP_URL if set, otherwise default
        local wizard_url="${SETUP_URL:-http://localhost:3000/setup}"

        echo "Opening setup wizard in your browser..."
        echo ""
        echo -e "  ${CYAN}$wizard_url${NC}"
        echo ""

        # Give services a moment to be fully ready
        sleep 2

        # Try to open browser
        if open_browser "$wizard_url"; then
            log_success "Browser opened"
        else
            log_warn "Could not open browser automatically"
            echo "Please open this URL manually: $wizard_url"
        fi

        echo ""
        echo "Complete the setup wizard to configure your channels and API keys."
    else
        # Run TUI wizard for local install
        python3 -m tools.setup.tui.main
    fi
}

# Main deployment flow
if [ "$INTERACTIVE" = true ]; then
    show_deployment_menu

    while true; do
        read -p "Enter your choice [1-3]: " choice </dev/tty
        case $choice in
            1)
                if install_local; then
                    DOCKER_DEPLOYMENT=false
                    launch_wizard
                fi
                break
                ;;
            2)
                if install_docker; then
                    DOCKER_DEPLOYMENT=true
                    launch_wizard
                else
                    echo ""
                    log_warn "Docker setup failed. Choose another option or fix the issues above."
                    echo ""
                    show_deployment_menu
                fi
                break
                ;;
            3)
            echo ""
            log_info "Exiting. You can complete setup manually."
            echo ""
            echo "Manual setup documentation:"
            echo -e "  ${CYAN}$MANUAL_DOCS_URL${NC}"
            echo ""
            echo "Quick start commands:"
            echo ""
            echo "  Local development:"
            echo -e "    ${BLUE}cd $DEXAI_DIR${NC}"
            echo -e "    ${BLUE}source .venv/bin/activate${NC}"
            echo -e "    ${BLUE}make dev${NC}"
            echo ""
            echo "  Docker deployment (basic):"
            echo -e "    ${BLUE}cd $DEXAI_DIR${NC}"
            echo -e "    ${BLUE}docker compose up -d${NC}"
            echo ""
            echo "  Docker with Caddy reverse proxy:"
            echo -e "    ${BLUE}DEXAI_DOMAIN=your-hostname docker compose --profile proxy up -d${NC}"
            echo ""
            echo "  Docker with Tailscale:"
            echo -e "    ${BLUE}TAILSCALE_AUTHKEY=tskey-... TAILSCALE_HOSTNAME=my-dexai docker compose --profile tailscale up -d${NC}"
            echo ""
            echo "  Docker with both Caddy + Tailscale:"
            echo -e "    ${BLUE}docker compose --profile proxy --profile tailscale up -d${NC}"
            echo ""
            echo "  Setup wizard:"
            echo -e "    ${BLUE}python -m tools.setup.tui.main${NC}"
            echo ""
            break
            ;;
        *)
            echo -e "${RED}Invalid choice. Please enter 1, 2, or 3.${NC}"
            ;;
    esac
    done
else
    # Non-interactive mode
    if [ -n "$CLI_TAILSCALE_KEY" ]; then
        # Tailscale key provided: use Docker deployment
        log_info "Non-interactive mode with Tailscale: using Docker deployment"
        if install_docker; then
            DOCKER_DEPLOYMENT=true
            echo ""
            log_info "Setup wizard available at: $SETUP_URL"
        fi
    else
        # No Tailscale key: default to local development
        log_info "Non-interactive mode: defaulting to local development setup"
        if install_local; then
            DOCKER_DEPLOYMENT=false
            # Skip wizard in non-interactive mode
            log_info "Run 'python -m tools.setup.tui.main' to complete setup"
        fi
    fi
fi

log_success "Installation complete!"
