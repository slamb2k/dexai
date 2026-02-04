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

# Check uv (preferred) or pip
if check_command uv; then
    PKG_MANAGER="uv"
    log_success "uv package manager found"
elif check_command pip3; then
    PKG_MANAGER="pip3"
    log_warn "uv not found, using pip3 (slower)"
    echo "  Install uv for faster installs: curl -LsSf https://astral.sh/uv/install.sh | sh"
else
    log_error "No Python package manager found. Install uv or pip."
    exit 1
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

log_info "Installing dependencies..."

if [ "$PKG_MANAGER" = "uv" ]; then
    run_cmd uv pip install -e "."
else
    run_cmd pip3 install -e "."
fi

log_success "Dependencies installed"

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
