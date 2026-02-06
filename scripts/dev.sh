#!/bin/bash
# =============================================================================
# DexAI Development Server
# =============================================================================
# Flexible development server with multiple modes
#
# Usage:
#   ./scripts/dev.sh              # Local frontend + Docker backend (default)
#   ./scripts/dev.sh local        # Local frontend + Docker backend
#   ./scripts/dev.sh local-all    # Local frontend + Local backend
#   ./scripts/dev.sh docker       # Docker frontend + Docker backend
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/tools/dashboard/frontend"

# Parse mode argument (default: local)
MODE="${1:-local}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Validate mode
if [[ ! "$MODE" =~ ^(local|local-all|docker|docker-dev)$ ]]; then
    echo -e "${RED}Invalid mode: $MODE${NC}"
    echo "Valid modes: local, local-all, docker, docker-dev"
    echo ""
    echo "  local      - Local frontend + Docker backend (default)"
    echo "  local-all  - Local frontend + Local backend"
    echo "  docker     - Docker frontend + Docker backend (production)"
    echo "  docker-dev - Docker with hot reload (Agent SDK compatible)"
    exit 1
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  DexAI Development Server${NC}"
echo -e "${BLUE}  Mode: ${GREEN}$MODE${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo

# Check for required tools based on mode
check_requirements() {
    local missing=()

    case "$MODE" in
        local|local-all)
            if ! command -v npm &> /dev/null; then
                missing+=("npm (Node.js)")
            fi
            ;;
    esac

    case "$MODE" in
        local|docker)
            if ! command -v docker &> /dev/null; then
                missing+=("docker")
            fi
            ;;
    esac

    case "$MODE" in
        local-all)
            if ! command -v uv &> /dev/null && ! command -v python3 &> /dev/null; then
                missing+=("uv or python3")
            fi
            ;;
    esac

    if [ ${#missing[@]} -ne 0 ]; then
        echo -e "${RED}Missing requirements: ${missing[*]}${NC}"
        exit 1
    fi
}

# =============================================================================
# Stop functions - clean up conflicting services before starting
# =============================================================================

# Stop Docker backend
stop_docker_backend() {
    if docker compose ps backend 2>/dev/null | grep -qE "(Up|running)"; then
        echo "      Stopping Docker backend..."
        docker compose stop backend > /dev/null 2>&1
    fi
}

# Stop Docker frontend
stop_docker_frontend() {
    if docker compose ps frontend 2>/dev/null | grep -qE "(Up|running)"; then
        echo "      Stopping Docker frontend..."
        docker compose stop frontend > /dev/null 2>&1
    fi
}

# Stop any process on a given port
stop_process_on_port() {
    local port=$1
    local name=$2

    # Get all PIDs listening on this port using ss (more reliable than lsof)
    # ss output format: users:(("node",pid=12345,fd=22))
    # Use || true to prevent exit on no matches (grep returns 1 when no match)
    local pids=$(ss -tlnp 2>/dev/null | grep ":$port " | grep -oP 'pid=\K[0-9]+' | sort -u || true)

    # Fallback to lsof if ss didn't find anything
    if [ -z "$pids" ]; then
        pids=$(lsof -ti :$port 2>/dev/null || true)
    fi

    if [ -n "$pids" ]; then
        echo "      Stopping $name on port $port (PIDs: $pids)..."
        for pid in $pids; do
            kill $pid 2>/dev/null || true
        done
        # Wait for processes to die
        sleep 2

        # Force kill if still running
        local remaining=$(ss -tlnp 2>/dev/null | grep ":$port " | grep -oP 'pid=\K[0-9]+' | sort -u || true)
        if [ -n "$remaining" ]; then
            echo "      Force killing remaining processes..."
            for pid in $remaining; do
                kill -9 $pid 2>/dev/null || true
            done
            sleep 1
        fi
    fi
}

# Stop conflicting services based on target mode
stop_conflicting_services() {
    echo -e "${YELLOW}[0/3]${NC} Stopping conflicting services..."
    cd "$PROJECT_ROOT"

    case "$MODE" in
        local)
            # Need Docker backend (port 8080), local frontend (port 3000)
            # Stop Docker frontend first, then any remaining process on 3000
            stop_docker_frontend
            stop_process_on_port 3000 "frontend"
            ;;
        local-all)
            # Need local backend (port 8080), local frontend (port 3000)
            # Stop all Docker services and any processes on both ports
            stop_docker_backend
            stop_docker_frontend
            stop_process_on_port 8080 "backend"
            stop_process_on_port 3000 "frontend"
            ;;
        docker)
            # Need Docker backend (port 8080), Docker frontend (port 3000)
            # Stop any local processes on both ports first
            stop_process_on_port 8080 "backend"
            stop_process_on_port 3000 "frontend"
            ;;
    esac

    echo "      Ready"
}

# Start backend in Docker
start_backend_docker() {
    echo -e "${GREEN}[1/3]${NC} Starting backend in Docker..."
    cd "$PROJECT_ROOT"

    # Check if backend is already running
    if docker compose ps backend 2>/dev/null | grep -qE "(Up|running)"; then
        echo "      Backend already running"
    else
        docker compose up -d backend
        echo "      Waiting for backend to be healthy..."

        # Wait for health check (max 30 seconds)
        for i in {1..30}; do
            if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
                echo -e "      ${GREEN}Backend ready!${NC}"
                break
            fi
            sleep 1
        done
    fi
}

# Start backend locally
start_backend_local() {
    echo -e "${GREEN}[1/3]${NC} Starting backend locally..."
    cd "$PROJECT_ROOT"

    # Check if backend is already running
    if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
        echo "      Backend already running"
        return
    fi

    # Start backend in background
    if command -v uv &> /dev/null; then
        echo "      Using uv to run backend..."
        uv run uvicorn tools.dashboard.backend.main:app --host 0.0.0.0 --port 8080 --reload &
    else
        echo "      Using python3 to run backend..."
        python3 -m uvicorn tools.dashboard.backend.main:app --host 0.0.0.0 --port 8080 --reload &
    fi
    BACKEND_PID=$!

    echo "      Waiting for backend to be healthy..."
    for i in {1..30}; do
        if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
            echo -e "      ${GREEN}Backend ready! (PID: $BACKEND_PID)${NC}"
            return
        fi
        sleep 1
    done
    echo -e "${RED}      Backend failed to start${NC}"
    exit 1
}

# Install frontend dependencies if needed
setup_frontend_local() {
    echo -e "${GREEN}[2/3]${NC} Checking frontend dependencies..."
    cd "$FRONTEND_DIR"

    if [ ! -d "node_modules" ]; then
        echo "      Installing dependencies (first time setup)..."
        npm install
    else
        echo "      Dependencies already installed"
    fi
}

# Start frontend dev server locally
start_frontend_local() {
    local backend_type="$1"
    echo -e "${GREEN}[3/3]${NC} Starting frontend dev server..."
    echo
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${GREEN}Backend:${NC}  http://localhost:8080 ($backend_type)"
    echo -e "  ${GREEN}Frontend:${NC} http://localhost:3000 (Local - hot reload)"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
    echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop"
    if [ "$backend_type" = "Docker" ]; then
        echo -e "  Run ${YELLOW}docker compose down${NC} to stop the backend"
    fi
    echo

    cd "$FRONTEND_DIR"
    npm run dev
}

# Start frontend in Docker
start_frontend_docker() {
    echo -e "${GREEN}[2/2]${NC} Starting frontend in Docker..."
    cd "$PROJECT_ROOT"

    docker compose up -d frontend

    echo "      Waiting for frontend to be ready..."
    for i in {1..60}; do
        if curl -s http://localhost:3000 > /dev/null 2>&1; then
            echo -e "      ${GREEN}Frontend ready!${NC}"
            break
        fi
        sleep 1
    done

    echo
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${GREEN}Backend:${NC}  http://localhost:8080 (Docker)"
    echo -e "  ${GREEN}Frontend:${NC} http://localhost:3000 (Docker)"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
    echo -e "  Services running in background"
    echo -e "  View logs: ${YELLOW}docker compose logs -f${NC}"
    echo -e "  Stop all:  ${YELLOW}docker compose down${NC}"
    echo
}

# Cleanup on exit
cleanup() {
    echo
    echo -e "${YELLOW}Shutting down...${NC}"

    # Kill local backend if running
    if [ -n "$BACKEND_PID" ]; then
        echo "      Stopping local backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null || true
    fi

    case "$MODE" in
        local)
            echo -e "Docker backend still running. Stop with: ${BLUE}docker compose down${NC}"
            ;;
        docker)
            echo -e "Docker services still running. Stop with: ${BLUE}docker compose down${NC}"
            ;;
        local-all)
            echo -e "${GREEN}All services stopped.${NC}"
            ;;
    esac
}

trap cleanup EXIT

# Main execution based on mode
check_requirements
stop_conflicting_services

case "$MODE" in
    local)
        # Local frontend + Docker backend (default)
        start_backend_docker
        setup_frontend_local
        start_frontend_local "Docker"
        ;;
    local-all)
        # Local frontend + Local backend
        start_backend_local
        setup_frontend_local
        start_frontend_local "Local"
        ;;
    docker)
        # Docker frontend + Docker backend
        echo -e "${GREEN}[1/2]${NC} Starting backend in Docker..."
        cd "$PROJECT_ROOT"
        docker compose up -d backend
        echo "      Waiting for backend to be healthy..."
        for i in {1..30}; do
            if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
                echo -e "      ${GREEN}Backend ready!${NC}"
                break
            fi
            sleep 1
        done
        start_frontend_docker
        ;;
    docker-dev)
        # Docker with hot reload - Agent SDK compatible
        echo -e "${GREEN}[1/2]${NC} Starting backend in Docker (dev mode with hot reload)..."
        cd "$PROJECT_ROOT"

        # Build and start with dev overrides
        docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build backend

        echo "      Waiting for backend to be healthy..."
        for i in {1..60}; do
            if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
                echo -e "      ${GREEN}Backend ready!${NC}"
                break
            fi
            sleep 1
        done

        setup_frontend_local

        echo
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "  ${GREEN}Backend:${NC}  http://localhost:8080 (Docker with hot reload)"
        echo -e "  ${GREEN}Frontend:${NC} http://localhost:3000 (Local - hot reload)"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo
        echo -e "  ${YELLOW}Agent SDK works in this mode!${NC}"
        echo -e "  Edit files locally - backend auto-reloads in Docker"
        echo
        echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop frontend"
        echo -e "  Run ${YELLOW}docker compose -f docker-compose.yml -f docker-compose.dev.yml down${NC} to stop backend"
        echo

        cd "$FRONTEND_DIR"
        npm run dev
        ;;
esac
