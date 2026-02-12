# ==============================================================================
# DexAI Makefile
# ==============================================================================
# Build automation for DexAI development and deployment
#
# Usage:
#   make install      Install dependencies
#   make dev          Start development servers
#   make test         Run tests
#   make build        Build Docker images
#   make deploy       Deploy with Docker Compose
#   make help         Show all available targets
# ==============================================================================

.PHONY: help install dev test lint build deploy deploy-tailscale clean logs status \
        db-init db-migrate wizard frontend backend channels

# Default target
.DEFAULT_GOAL := help

# Colors
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m

# ==============================================================================
# Help
# ==============================================================================

help: ## Show this help message
	@echo "$(BLUE)DexAI - ADHD-Optimized AI Assistant$(NC)"
	@echo ""
	@echo "$(GREEN)Usage:$(NC)"
	@echo "  make <target>"
	@echo ""
	@echo "$(GREEN)Targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-18s$(NC) %s\n", $$1, $$2}'

# ==============================================================================
# Installation
# ==============================================================================

install: ## Install Python dependencies
	@echo "$(BLUE)Installing dependencies...$(NC)"
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install -e .; \
	else \
		pip install -e .; \
	fi
	@echo "$(GREEN)Dependencies installed$(NC)"

install-dev: ## Install development dependencies
	@echo "$(BLUE)Installing dev dependencies...$(NC)"
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install -e ".[dev]"; \
	else \
		pip install -e ".[dev]"; \
	fi
	@echo "$(GREEN)Dev dependencies installed$(NC)"

# ==============================================================================
# Development
# ==============================================================================

dev: ## Start development servers (backend + frontend)
	@echo "$(BLUE)Starting development servers...$(NC)"
	@trap 'kill 0' EXIT; \
	python -m uvicorn tools.dashboard.backend.main:app --host 127.0.0.1 --port 8080 --reload & \
	cd tools/dashboard/frontend && \
	if command -v bun >/dev/null 2>&1; then bun run dev; \
	elif command -v pnpm >/dev/null 2>&1; then pnpm run dev; \
	else npm run dev; fi & \
	wait

backend: ## Start backend only
	@echo "$(BLUE)Starting backend server...$(NC)"
	python -m uvicorn tools.dashboard.backend.main:app --host 127.0.0.1 --port 8080 --reload

frontend: ## Start frontend only
	@echo "$(BLUE)Starting frontend server...$(NC)"
	@cd tools/dashboard/frontend && \
	if command -v bun >/dev/null 2>&1; then bun run dev; \
	elif command -v pnpm >/dev/null 2>&1; then pnpm run dev; \
	else npm run dev; fi

channels: ## Start all channel adapters
	@echo "$(BLUE)Starting channel adapters...$(NC)"
	python tools/channels/router.py --start

wizard: ## Run the dashboard for setup
	@echo "$(BLUE)Starting dashboard (setup is chat-based)...$(NC)"
	dexai dashboard

# ==============================================================================
# Testing & Linting
# ==============================================================================

test: ## Run tests
	@echo "$(BLUE)Running tests...$(NC)"
	pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	pytest tests/ -v --cov=tools --cov-report=html --cov-report=term

lint: ## Run linters
	@echo "$(BLUE)Running linters...$(NC)"
	ruff check .
	@echo "$(GREEN)Lint passed$(NC)"

lint-fix: ## Run linters and auto-fix
	@echo "$(BLUE)Running linters with auto-fix...$(NC)"
	ruff check --fix .
	@echo "$(GREEN)Lint fixes applied$(NC)"

typecheck: ## Run type checker
	@echo "$(BLUE)Running type checker...$(NC)"
	mypy tools/ --ignore-missing-imports

format: ## Format code
	@echo "$(BLUE)Formatting code...$(NC)"
	ruff format .
	@echo "$(GREEN)Code formatted$(NC)"

# ==============================================================================
# Docker
# ==============================================================================

build: ## Build Docker images
	@echo "$(BLUE)Building Docker images...$(NC)"
	docker compose build
	@echo "$(GREEN)Build complete$(NC)"

deploy: ## Deploy with Docker Compose
	@echo "$(BLUE)Deploying with Docker Compose...$(NC)"
	docker compose up -d
	@echo "$(GREEN)Deployed! Check status with 'make status'$(NC)"

deploy-tailscale: ## Deploy with Docker Compose + Tailscale
	@echo "$(BLUE)Deploying with Tailscale...$(NC)"
	docker compose --profile tailscale up -d
	@echo "$(GREEN)Deployed with Tailscale!$(NC)"

down: ## Stop Docker containers
	@echo "$(BLUE)Stopping containers...$(NC)"
	docker compose down

logs: ## Show Docker logs
	docker compose logs -f

status: ## Show deployment status
	@echo "$(BLUE)Container Status:$(NC)"
	@docker compose ps
	@echo ""
	@echo "$(BLUE)Health Check:$(NC)"
	@curl -s http://localhost:8080/api/health 2>/dev/null | python -m json.tool || echo "Backend not running"

# ==============================================================================
# Database
# ==============================================================================

db-init: ## Initialize all databases
	@echo "$(BLUE)Initializing databases...$(NC)"
	@python -c "from tools.dashboard.backend.database import init_db; init_db(); print('Dashboard DB initialized')"
	@python -c "from tools.memory.memory_db import get_connection; get_connection().close(); print('Memory DB initialized')"
	@python -c "from tools.security.vault import init_vault; init_vault(); print('Vault initialized')"
	@echo "$(GREEN)All databases initialized$(NC)"

db-migrate: ## Run database migrations
	@echo "$(BLUE)Running migrations...$(NC)"
	@python -m tools.ops.migrate
	@echo "$(GREEN)Migrations complete$(NC)"

db-backup: ## Backup databases (WAL-safe, compressed)
	@echo "$(BLUE)Backing up databases...$(NC)"
	@python -m tools.ops.backup
	@echo "$(GREEN)Databases backed up to backups/$(NC)"

db-enable-wal: ## Enable WAL mode on all databases
	@echo "$(BLUE)Enabling WAL mode...$(NC)"
	@python -m tools.ops.backup --enable-wal
	@echo "$(GREEN)WAL mode enabled$(NC)"

# ==============================================================================
# Cleanup
# ==============================================================================

clean: ## Clean build artifacts
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ 2>/dev/null || true
	@echo "$(GREEN)Clean complete$(NC)"

clean-docker: ## Remove Docker volumes and images
	@echo "$(YELLOW)Warning: This will remove all DexAI Docker data$(NC)"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] && \
		docker compose down -v --rmi local || echo "Cancelled"

# ==============================================================================
# Security
# ==============================================================================

check-secrets: ## Check for accidentally committed secrets
	@echo "$(BLUE)Checking for secrets...$(NC)"
	@git diff --cached --name-only | xargs -I {} grep -l -E "(api_key|secret|password|token)" {} 2>/dev/null && \
		echo "$(YELLOW)Warning: Potential secrets found in staged files$(NC)" || \
		echo "$(GREEN)No obvious secrets found$(NC)"

rotate-master-key: ## Rotate master key and re-encrypt all secrets
	@echo "$(YELLOW)Warning: This will re-encrypt all vault secrets with a new master key$(NC)"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] && \
		(NEW_KEY=$$(openssl rand -hex 32) && \
		echo "New master key: $$NEW_KEY" && \
		python tools/security/vault.py --action rotate-key --old-key "$$DEXAI_MASTER_KEY" --new-key "$$NEW_KEY" && \
		echo "$(GREEN)Secrets re-encrypted. Update DEXAI_MASTER_KEY in .env to: $$NEW_KEY$(NC)") || echo "Cancelled"

# ==============================================================================
# Utilities
# ==============================================================================

shell: ## Start a Python shell with project context
	@python -c "import sys; sys.path.insert(0, '.'); import code; code.interact(local=dict(globals(), **locals()))"

repl: ## Start IPython REPL if available
	@ipython -i -c "import sys; sys.path.insert(0, '.')" 2>/dev/null || python -i -c "import sys; sys.path.insert(0, '.')"

env-check: ## Verify environment configuration
	@echo "$(BLUE)Checking environment...$(NC)"
	@python -c "\
import os; \
from pathlib import Path; \
env_file = Path('.env'); \
print('✓ .env exists' if env_file.exists() else '✗ .env missing'); \
print('✓ DEXAI_MASTER_KEY set' if os.getenv('DEXAI_MASTER_KEY') else '✗ DEXAI_MASTER_KEY not set'); \
print('✓ ANTHROPIC_API_KEY set' if os.getenv('ANTHROPIC_API_KEY') else '✗ ANTHROPIC_API_KEY not set'); \
"
