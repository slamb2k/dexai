#!/bin/bash
# ==============================================================================
# DexAI Installation Script — Docker-First
# ==============================================================================
#
# Default: builds and starts DexAI via Docker Compose.
# Use --local for a development setup (venv + npm, no containers).
#
# Configuration (API keys, channels) is deferred to the running dashboard.
# This script handles infrastructure only.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/slamb2k/dexai/main/install.sh | bash
#
# Or locally:
#   bash install.sh            # Docker mode (default)
#   bash install.sh --local    # Local dev mode
#
# Options:
#   --local      Local dev mode (venv + npm, no Docker)
#   --dry-run    Show what would be done without making changes
#   --dir PATH   Override install directory (default: $HOME/dexai)
#   --no-start   Scaffold only, don't start containers
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
LOCAL_MODE=false
NO_START=false
ENABLE_PROXY=false
ENABLE_TAILSCALE=false

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
        --local)
            LOCAL_MODE=true
            shift
            ;;
        --no-start)
            NO_START=true
            shift
            ;;
        --with-proxy)
            ENABLE_PROXY=true
            shift
            ;;
        --with-tailscale)
            ENABLE_TAILSCALE=true
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
            echo "DexAI Installer"
            echo ""
            echo "Usage: bash install.sh [options]"
            echo ""
            echo "Options:"
            echo "  --local           Local dev mode (venv + npm, no Docker)"
            echo "  --dry-run         Show what would be done without making changes"
            echo "  --dir PATH        Override install directory (default: \$HOME/dexai)"
            echo "  --no-start        Scaffold only, don't start containers"
            echo "  --with-proxy      Enable Caddy reverse proxy (HTTPS)"
            echo "  --with-tailscale  Enable Tailscale VPN access"
            echo "  --help            Show this help message"
            echo ""
            echo "Default: Docker mode (builds and starts containers)"
            echo "In interactive mode, you'll be prompted for optional services."
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

check_docker_required() {
    if ! check_command docker; then
        log_error "Docker is required for installation."
        case "$OS_TYPE" in
            macos) echo "  Install: https://docs.docker.com/desktop/install/mac-install/" ;;
            wsl)   echo "  Install: https://docs.docker.com/desktop/install/windows-install/" ;;
            *)     echo "  Install: https://docs.docker.com/engine/install/" ;;
        esac
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        log_error "Docker Compose v2 is required."
        exit 1
    fi
    log_success "Docker found and running"
}

check_docker_optional() {
    # Docker is optional in local mode — just report status
    if check_command docker && docker info >/dev/null 2>&1; then
        log_success "Docker found and running (optional)"
    else
        log_info "Docker not found or not running (optional — needed only for container deployment)"
    fi
}

check_node() {
    if ! check_command node || ! check_command npm; then
        log_error "Node.js 18+ and npm are required for local mode."
        echo "  Install from: https://nodejs.org/"
        exit 1
    fi
    local node_major
    node_major=$(node --version | tr -d 'v' | cut -d. -f1)
    if [ "$node_major" -lt 18 ] 2>/dev/null; then
        log_error "Node.js 18+ required, found $(node --version)"
        exit 1
    fi
    log_success "Node.js $(node --version) found"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    echo ""
    check_git
    check_curl

    if [ "$LOCAL_MODE" = true ]; then
        check_python
        check_uv
        check_node
        check_docker_optional
    else
        check_docker_required
    fi

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
    elif [ -f "$DEXAI_DIR/.env.example" ]; then
        log_info "Creating .env from template..."
        run_cmd cp "$DEXAI_DIR/.env.example" "$env_file"
        log_success ".env file created"
    else
        run_cmd touch "$env_file"
        log_success ".env file created (empty)"
    fi

    # Set restrictive permissions
    if [ "$DRY_RUN" = false ] && [ -f "$env_file" ]; then
        chmod 600 "$env_file" 2>/dev/null || true
    fi

    # Auto-generate master key if still placeholder
    if [ "$DRY_RUN" = false ] && [ -f "$env_file" ]; then
        local current_key=""
        current_key=$(grep -E "^DEXAI_MASTER_KEY=" "$env_file" 2>/dev/null | cut -d= -f2-) || true
        if [ "$current_key" = "your-secure-master-password-here" ] || [ -z "$current_key" ]; then
            local new_key
            new_key=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | od -A n -t x1 | tr -d ' \n')
            sed -i "s|^DEXAI_MASTER_KEY=.*|DEXAI_MASTER_KEY=${new_key}|" "$env_file" 2>/dev/null \
                || echo "DEXAI_MASTER_KEY=${new_key}" >> "$env_file"
            log_success "DEXAI_MASTER_KEY auto-generated"
        fi
    fi
}

# ==============================================================================
# Step 6: Scaffold User Config
# ==============================================================================

ensure_user_config() {
    local user_yaml="$DEXAI_DIR/args/user.yaml"

    if [ -f "$user_yaml" ]; then
        log_success "User config exists"
        return 0
    fi

    if [ -f "$DEXAI_DIR/args/user.yaml.example" ]; then
        log_info "Creating user config from template..."
        run_cmd cp "$DEXAI_DIR/args/user.yaml.example" "$user_yaml"
        log_success "User config created (configure via dashboard)"
    fi
}

# ==============================================================================
# Step 7: Create Data Directories
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
# Step 7: Optional Services (interactive prompts)
# ==============================================================================

set_env_var() {
    local key="$1"
    local value="$2"
    local env_file="$DEXAI_DIR/.env"

    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} Would set ${key} in .env"
        return 0
    fi

    # Replace existing line (commented or uncommented), or append
    if grep -qE "^[# ]*${key}=" "$env_file" 2>/dev/null; then
        sed -i "s|^[# ]*${key}=.*|${key}=${value}|" "$env_file"
    else
        echo "${key}=${value}" >> "$env_file"
    fi
}

prompt_optional_services() {
    # Only prompt in Docker mode, non-dry-run, interactive terminal
    if [ "$LOCAL_MODE" = true ] || [ "$DRY_RUN" = true ]; then
        return 0
    fi

    # Non-interactive (piped install) — skip prompts, use flags only
    if [ ! -t 0 ]; then
        return 0
    fi

    echo ""
    log_info "Optional services (Docker profiles):"
    echo ""

    # Caddy reverse proxy
    if [ "$ENABLE_PROXY" = false ]; then
        read -r -p "  Enable HTTPS via Caddy reverse proxy? [y/N] " response </dev/tty
        if [[ "$response" =~ ^[Yy] ]]; then
            ENABLE_PROXY=true
        fi
    fi

    if [ "$ENABLE_PROXY" = true ]; then
        local current_domain=""
        current_domain=$(grep -E "^DEXAI_DOMAIN=" "$DEXAI_DIR/.env" 2>/dev/null | cut -d= -f2-) || true
        if [ "$current_domain" = "localhost" ] || [ -z "$current_domain" ]; then
            read -r -p "  Enter your domain (e.g., dexai.example.com) [localhost]: " domain </dev/tty
            domain="${domain:-localhost}"
            set_env_var "DEXAI_DOMAIN" "$domain"
            log_success "Domain set to $domain"
        else
            log_success "Domain already configured: $current_domain"
        fi
    fi

    # Tailscale VPN
    if [ "$ENABLE_TAILSCALE" = false ]; then
        read -r -p "  Enable Tailscale VPN access? [y/N] " response </dev/tty
        if [[ "$response" =~ ^[Yy] ]]; then
            ENABLE_TAILSCALE=true
        fi
    fi

    if [ "$ENABLE_TAILSCALE" = true ]; then
        local current_tskey=""
        current_tskey=$(grep -E "^TAILSCALE_AUTHKEY=" "$DEXAI_DIR/.env" 2>/dev/null | cut -d= -f2-) || true
        if [ -z "$current_tskey" ]; then
            echo "  Generate a key at: https://login.tailscale.com/admin/settings/keys"
            read -r -p "  Enter your Tailscale auth key (tskey-auth-...): " tskey </dev/tty
            if [ -n "$tskey" ]; then
                set_env_var "TAILSCALE_AUTHKEY" "$tskey"
                log_success "Tailscale auth key configured"
            else
                log_warn "No Tailscale key provided — profile enabled but may fail to authenticate"
            fi
        else
            log_success "Tailscale auth key already configured"
        fi
    fi
}

# ==============================================================================
# Step 8: Docker Setup
# ==============================================================================

setup_docker() {
    # Build compose command with optional profiles
    local compose_profiles=""
    if [ "$ENABLE_PROXY" = true ]; then
        compose_profiles="$compose_profiles --profile proxy"
    fi
    if [ "$ENABLE_TAILSCALE" = true ]; then
        compose_profiles="$compose_profiles --profile tailscale"
    fi

    log_info "Building and starting DexAI containers..."
    if [ -n "$compose_profiles" ]; then
        log_info "Profiles:${compose_profiles}"
    fi

    if [ "$NO_START" = true ]; then
        log_info "Skipping container start (--no-start)"
        return 0
    fi

    # shellcheck disable=SC2086
    run_cmd docker compose $compose_profiles up -d --build

    if [ "$DRY_RUN" = true ]; then
        return 0
    fi

    # Wait for backend health
    log_info "Waiting for services to become healthy..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if curl -sf http://localhost:${DEXAI_BACKEND_PORT:-8080}/api/health >/dev/null 2>&1; then
            log_success "Backend is healthy"
            break
        fi
        retries=$((retries - 1))
        sleep 2
    done
    if [ $retries -eq 0 ]; then
        log_warn "Backend timed out. Check: docker compose logs backend"
    fi

    retries=30
    while [ $retries -gt 0 ]; do
        if curl -sf http://localhost:${DEXAI_FRONTEND_PORT:-3000} >/dev/null 2>&1; then
            log_success "Frontend is ready"
            break
        fi
        retries=$((retries - 1))
        sleep 2
    done
    if [ $retries -eq 0 ]; then
        log_warn "Frontend timed out. Check: docker compose logs frontend"
    fi
}

# ==============================================================================
# Step 5b: Local Setup
# ==============================================================================

setup_local() {
    setup_python_env
    setup_frontend
}

setup_frontend() {
    local frontend_dir="$DEXAI_DIR/tools/dashboard/frontend"
    if [ ! -d "$frontend_dir" ]; then
        log_warn "Frontend directory not found, skipping"
        return 0
    fi
    log_info "Installing frontend dependencies..."
    run_cmd npm --prefix "$frontend_dir" install
    log_success "Frontend dependencies installed"
}

# ==============================================================================
# Main
# ==============================================================================

main() {
    echo ""
    echo -e "${BOLD}DexAI Installer${NC}"
    echo "========================"
    echo ""

    detect_os
    check_prerequisites
    setup_repository
    ensure_env_file
    ensure_user_config
    ensure_data_dirs

    if [ "$LOCAL_MODE" = true ]; then
        setup_local
    else
        prompt_optional_services
        setup_docker
    fi

    echo ""
    if [ "$DRY_RUN" = true ]; then
        log_info "Dry run complete. No changes were made."
    elif [ "$LOCAL_MODE" = true ]; then
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}  Local setup complete!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo -e "Start development servers:"
        echo -e "  ${CYAN}cd $DEXAI_DIR${NC}"
        echo -e "  ${CYAN}./scripts/dev.sh${NC}"
        echo ""
        echo -e "For HTTPS (Caddy) or VPN (Tailscale), use Docker mode:"
        echo -e "  ${CYAN}bash install.sh --with-proxy --with-tailscale${NC}"
    else
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}  DexAI is running!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo -e "  Dashboard:  ${CYAN}http://localhost:${DEXAI_FRONTEND_PORT:-3000}${NC}"
        echo -e "  API:        ${CYAN}http://localhost:${DEXAI_BACKEND_PORT:-8080}${NC}"
        if [ "$ENABLE_PROXY" = true ]; then
            echo -e "  HTTPS:      ${CYAN}https://$(grep -E '^DEXAI_DOMAIN=' "$DEXAI_DIR/.env" 2>/dev/null | cut -d= -f2- || echo 'localhost')${NC}"
        fi
        echo ""
        echo -e "Next: open the dashboard to configure API keys."

        # Show add-later hints only for services not already enabled
        if [ "$ENABLE_PROXY" = false ] || [ "$ENABLE_TAILSCALE" = false ]; then
            echo ""
            echo -e "Add services later:"
            if [ "$ENABLE_PROXY" = false ]; then
                echo -e "  ${CYAN}bash install.sh --with-proxy${NC}              Enable Caddy (HTTPS)"
            fi
            if [ "$ENABLE_TAILSCALE" = false ]; then
                echo -e "  ${CYAN}bash install.sh --with-tailscale${NC}          Enable Tailscale (VPN)"
            fi
        fi
        echo ""
        echo -e "Useful commands:"
        echo -e "  ${CYAN}docker compose logs -f${NC}       View logs"
        echo -e "  ${CYAN}docker compose down${NC}          Stop services"
        echo -e "  ${CYAN}docker compose up -d${NC}         Restart"
    fi
    echo ""
}

main "$@"
