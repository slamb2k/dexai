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
#   --dry-run     Show what would be done without making changes
#   --help        Show this help message
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
        --help)
            echo "DexAI Installation Script"
            echo ""
            echo "Usage: bash install.sh [options]"
            echo ""
            echo "Options:"
            echo "  --dry-run     Show what would be done without making changes"
            echo "  --help        Show this help message"
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
        read -p "Would you like to install $name now? [Y/n] " -n 1 -r REPLY </dev/tty
        echo ""
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            return 0  # Yes, install
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
        read -p "Would you like to install Docker now? [Y/n] " -n 1 -r REPLY </dev/tty
        echo ""
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
# Install Core Python Dependencies
# ==============================================================================

log_info "Installing core dependencies..."

case "$PKG_MANAGER" in
    uv)
        run_cmd uv pip install -e "."
        ;;
    pip3)
        run_cmd pip3 install -e "."
        ;;
    pip)
        run_cmd pip install -e "."
        ;;
    "python3 -m pip")
        run_cmd python3 -m pip install -e "."
        ;;
esac

log_success "Core Python dependencies installed"

# ==============================================================================
# Auto-detect and Install Optional Dependencies
# ==============================================================================

log_info "Detecting enabled features from configuration..."

EXTRAS_TO_INSTALL=""

# Check channels.yaml for enabled messaging channels
CHANNELS_CONFIG="$DEXAI_DIR/args/channels.yaml"
if [ -f "$CHANNELS_CONFIG" ]; then
    if grep -q "telegram:" "$CHANNELS_CONFIG" && grep -A1 "telegram:" "$CHANNELS_CONFIG" | grep -q "enabled: true"; then
        EXTRAS_TO_INSTALL="$EXTRAS_TO_INSTALL telegram"
        log_info "  Telegram enabled"
    fi
    if grep -q "discord:" "$CHANNELS_CONFIG" && grep -A1 "discord:" "$CHANNELS_CONFIG" | grep -q "enabled: true"; then
        EXTRAS_TO_INSTALL="$EXTRAS_TO_INSTALL discord"
        log_info "  Discord enabled"
    fi
    if grep -q "slack:" "$CHANNELS_CONFIG" && grep -A1 "slack:" "$CHANNELS_CONFIG" | grep -q "enabled: true"; then
        EXTRAS_TO_INSTALL="$EXTRAS_TO_INSTALL slack"
        log_info "  Slack enabled"
    fi
fi

# Check office_integration.yaml for office features
OFFICE_CONFIG="$DEXAI_DIR/args/office_integration.yaml"
if [ -f "$OFFICE_CONFIG" ]; then
    if grep -q "enabled: true" "$OFFICE_CONFIG"; then
        EXTRAS_TO_INSTALL="$EXTRAS_TO_INSTALL office"
        log_info "  Office integration enabled"
    fi
fi

# Install detected extras
if [ -n "$EXTRAS_TO_INSTALL" ]; then
    EXTRAS_TO_INSTALL=$(echo "$EXTRAS_TO_INSTALL" | xargs)
    EXTRAS_CSV=$(echo "$EXTRAS_TO_INSTALL" | tr ' ' ',')
    log_info "Installing optional dependencies: $EXTRAS_CSV..."

    case "$PKG_MANAGER" in
        uv)
            run_cmd uv pip install -e ".[$EXTRAS_CSV]"
            ;;
        pip3)
            run_cmd pip3 install -e ".[$EXTRAS_CSV]"
            ;;
        pip)
            run_cmd pip install -e ".[$EXTRAS_CSV]"
            ;;
        "python3 -m pip")
            run_cmd python3 -m pip install -e ".[$EXTRAS_CSV]"
            ;;
    esac

    log_success "Optional dependencies installed"
else
    log_info "No optional features enabled in configuration"
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

    log_info "Building and starting containers..."

    # Build images
    if ! $DOCKER_COMPOSE_CMD build; then
        log_error "Failed to build Docker images"
        return 1
    fi

    # Start containers
    if ! $DOCKER_COMPOSE_CMD up -d; then
        log_error "Failed to start containers"
        return 1
    fi

    log_success "Docker deployment complete!"
    echo ""
    echo "Services running:"
    echo "  - Backend:  http://localhost:8080"
    echo "  - Frontend: http://localhost:3000"
    echo ""
    echo "Useful commands:"
    echo -e "  ${BLUE}cd $DEXAI_DIR && $DOCKER_COMPOSE_CMD logs -f${NC}  # View logs"
    echo -e "  ${BLUE}cd $DEXAI_DIR && $DOCKER_COMPOSE_CMD down${NC}      # Stop services"
    echo -e "  ${BLUE}cd $DEXAI_DIR && $DOCKER_COMPOSE_CMD ps${NC}        # Check status"
    echo ""

    # Wait for services to be healthy
    log_info "Waiting for services to start..."
    sleep 5

    return 0
}

# Function to launch the setup wizard
launch_wizard() {
    echo ""
    log_info "Launching setup wizard..."
    echo ""

    # Check if running in Docker - wizard runs differently
    if [ "${DOCKER_DEPLOYMENT:-false}" = true ]; then
        echo "Opening setup wizard in your browser..."
        echo ""
        echo -e "  ${CYAN}http://localhost:3000/setup${NC}"
        echo ""

        # Try to open browser
        if check_command xdg-open; then
            xdg-open "http://localhost:3000/setup" 2>/dev/null || true
        elif check_command open; then
            open "http://localhost:3000/setup" 2>/dev/null || true
        fi

        echo "Complete the setup wizard to configure your channels and API keys."
    else
        # Run TUI wizard for local install
        python3 -m tools.setup.tui.main
    fi
}

# Main deployment flow
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
            echo "  Docker deployment:"
            echo -e "    ${BLUE}cd $DEXAI_DIR${NC}"
            echo -e "    ${BLUE}docker compose up -d${NC}"
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

log_success "Installation complete!"
