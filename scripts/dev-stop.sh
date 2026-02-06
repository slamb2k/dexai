#!/bin/bash
# Stop all DexAI development services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Stopping DexAI services..."

cd "$PROJECT_ROOT"

# Stop Docker services
docker compose down

echo "All services stopped."
