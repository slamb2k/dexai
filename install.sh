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
#   --no-docker   Skip Docker installation
#   --no-wizard   Skip setup wizard at the end
#   --help        Show this help message
#
# ==============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEXAI_REPO="https://github.com/slamb2k/dexai.git"
DEXAI_DIR="${DEXAI_DIR:-$HOME/dexai}"
PYTHON_MIN_VERSION="3.11"

# Flags
DRY_RUN=false
NO_DOCKER=false
NO_WIZARD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --no-docker)
            NO_DOCKER=true
            shift
            ;;
        --no-wizard)
            NO_WIZARD=true
            shift
            ;;
        --help)
            echo "DexAI Installation Script"
            echo ""
            echo "Usage: bash install.sh [options]"
            echo ""
            echo "Options:"
            echo "  --dry-run     Show what would be done without making changes"
            echo "  --no-docker   Skip Docker installation"
            echo "  --no-wizard   Skip setup wizard at the end"
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

# ==============================================================================
# Prerequisite Checks
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

# Check Python version
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

# Check git
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

# Check Docker (optional)
if [ "$NO_DOCKER" = false ]; then
    if check_command docker; then
        log_success "Docker found"
    else
        log_warn "Docker not found. Docker deployment will not be available."
        log_warn "Install Docker for container-based deployment."
    fi
fi

# Check uv (preferred), pip3, pip, or python -m pip
if check_command uv; then
    PKG_MANAGER="uv"
    log_success "uv package manager found (fastest)"
elif check_command pip3; then
    PKG_MANAGER="pip3"
    log_warn "uv not found, using pip3 (slower)"
    echo "  Install uv for faster installs: curl -LsSf https://astral.sh/uv/install.sh | sh"
elif check_command pip; then
    PKG_MANAGER="pip"
    log_warn "uv not found, using pip (slower)"
    echo "  Install uv for faster installs: curl -LsSf https://astral.sh/uv/install.sh | sh"
elif python3 -m pip --version >/dev/null 2>&1; then
    PKG_MANAGER="python3 -m pip"
    log_warn "No standalone pip found, using python3 -m pip (slower)"
    echo "  Install uv for faster installs: curl -LsSf https://astral.sh/uv/install.sh | sh"
else
    log_warn "No Python package manager found (pip not installed)"
    echo ""
    read -p "Would you like to install uv (fast Python package manager)? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        log_info "Installing uv..."
        if curl -LsSf https://astral.sh/uv/install.sh | sh; then
            # Source the shell config to get uv in PATH
            export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
            if check_command uv; then
                PKG_MANAGER="uv"
                log_success "uv installed successfully"
            else
                log_error "uv installed but not found in PATH. Please restart your terminal and re-run this script."
                exit 1
            fi
        else
            log_error "Failed to install uv. Please install manually:"
            echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            echo "  Or install pip: python3 -m ensurepip --upgrade"
            exit 1
        fi
    else
        log_error "No package manager available. Install uv or pip:"
        echo "  Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "  Or install pip: python3 -m ensurepip --upgrade"
        exit 1
    fi
fi

# Check bun (preferred), pnpm, npm, or offer to install bun
if check_command bun; then
    JS_PKG_MANAGER="bun"
    log_success "bun package manager found (fastest)"
elif check_command pnpm; then
    JS_PKG_MANAGER="pnpm"
    log_warn "bun not found, using pnpm"
    echo "  Install bun for faster installs: curl -fsSL https://bun.sh/install | bash"
elif check_command npm; then
    JS_PKG_MANAGER="npm"
    log_warn "bun not found, using npm (slower)"
    echo "  Install bun for faster installs: curl -fsSL https://bun.sh/install | bash"
else
    log_warn "No JavaScript package manager found (npm/pnpm/bun not installed)"
    echo ""
    read -p "Would you like to install bun (fast JavaScript runtime & package manager)? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        log_info "Installing bun..."
        if curl -fsSL https://bun.sh/install | bash; then
            # Add bun to PATH for this session
            export BUN_INSTALL="$HOME/.bun"
            export PATH="$BUN_INSTALL/bin:$PATH"
            if check_command bun; then
                JS_PKG_MANAGER="bun"
                log_success "bun installed successfully"
            else
                log_error "bun installed but not found in PATH. Please restart your terminal and re-run this script."
                exit 1
            fi
        else
            log_error "Failed to install bun. Please install manually:"
            echo "  curl -fsSL https://bun.sh/install | bash"
            echo "  Or install Node.js/npm: https://nodejs.org/"
            exit 1
        fi
    else
        log_warn "Skipping frontend dependencies (no JS package manager)"
        JS_PKG_MANAGER=""
    fi
fi

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

cd "$DEXAI_DIR"
log_success "Working in $DEXAI_DIR"

# ==============================================================================
# Create Virtual Environment
# ==============================================================================

VENV_DIR="$DEXAI_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    log_info "Creating virtual environment..."
    run_cmd python3 -m venv "$VENV_DIR"
    log_success "Virtual environment created"
else
    log_success "Virtual environment exists"
fi

# Activate venv
if [ "$DRY_RUN" = false ]; then
    source "$VENV_DIR/bin/activate"
fi

# ==============================================================================
# Install Dependencies
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
    # Check individual channels
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
    EXTRAS_TO_INSTALL=$(echo "$EXTRAS_TO_INSTALL" | xargs)  # trim whitespace
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
# Install Frontend Dependencies
# ==============================================================================

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
elif [ -z "$JS_PKG_MANAGER" ]; then
    log_warn "Skipping frontend dependencies (no JS package manager)"
elif [ ! -d "$FRONTEND_DIR" ]; then
    log_warn "Frontend directory not found, skipping frontend dependencies"
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
        # Add or update the key
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

# Initialize security databases
try:
    from tools.security.vault import init_vault
    init_vault()
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
# Completion
# ==============================================================================

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  DexAI Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Configure your API keys in .env:"
echo "     ${BLUE}nano $ENV_FILE${NC}"
echo ""
echo "  2. Run the setup wizard:"
echo "     ${BLUE}cd $DEXAI_DIR && python tools/wizard/wizard.py${NC}"
echo ""
echo "  3. Start the dashboard:"
echo "     ${BLUE}cd $DEXAI_DIR && make dev${NC}"
echo ""
echo "  4. Or use Docker:"
echo "     ${BLUE}cd $DEXAI_DIR && docker compose up -d${NC}"
echo ""

# Launch wizard unless skipped
if [ "$NO_WIZARD" = false ] && [ "$DRY_RUN" = false ]; then
    echo ""
    read -p "Would you like to run the setup wizard now? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python3 "$DEXAI_DIR/tools/wizard/wizard.py"
    fi
fi

log_success "Installation complete!"
