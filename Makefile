# ─── LLM Platform Makefile ────────────────────────────────────

.PHONY: help install install-dev dev dev-up dev-down dev-logs test test-unit test-integration test-cov lint lint-fix format type-check pre-commit migrate migrate-create migrate-up migrate-down shell shell-db shell-redis clean clean-pyc clean-cache clean-all build build-prod docker-up docker-down docker-logs

# Default target
.DEFAULT_GOAL := help

# Variables
POETRY := poetry
DOCKER_COMPOSE := docker compose
PYTEST := $(POETRY) run pytest
RUFF := $(POETRY) run ruff
MYPY := $(POETRY) run mypy
ALEMBIC := $(POETRY) run alembic

# ─── Help ─────────────────────────────────────────────────────
help:  ## Show this help message
	@echo "LLM Platform — Available Commands"
	@echo "==================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

# ─── Installation ─────────────────────────────────────────────
install:  ## Install all dependencies with Poetry
	$(POETRY) install --no-root

install-dev:  ## Install dependencies including dev extras
	$(POETRY) install --no-root --with dev

install-prod:  ## Install production dependencies only
	$(POETRY) install --no-root --only main --no-dev

update:  ## Update all dependencies to latest compatible versions
	$(POETRY) update

# ─── Development Server ───────────────────────────────────────
dev:  ## Start development server with docker compose
	$(DOCKER_COMPOSE) up --build

dev-up:  ## Start all services in detached mode
	$(DOCKER_COMPOSE) up --build -d

dev-down:  ## Stop all services and remove containers
	$(DOCKER_COMPOSE) down

dev-down-volumes:  ## Stop all services and remove volumes (DESTRUCTIVE)
	$(DOCKER_COMPOSE) down -v

dev-restart: dev-down dev-up  ## Restart all services

dev-logs:  ## Follow logs from all services
	$(DOCKER_COMPOSE) logs -f

dev-logs-app:  ## Follow logs from app service only
	$(DOCKER_COMPOSE) logs -f app

dev-logs-worker:  ## Follow logs from worker service only
	$(DOCKER_COMPOSE) logs -f worker

dev-rebuild:  ## Rebuild and restart app service
	$(DOCKER_COMPOSE) up --build -d --no-deps app

dev-shell:  ## Open a shell inside the app container
	$(DOCKER_COMPOSE) exec app /bin/bash

# ─── Testing ──────────────────────────────────────────────────
test:  ## Run all tests
	$(PYTEST) tests/ -v

test-unit:  ## Run unit tests only
	$(PYTEST) tests/ -v -m "unit"

test-integration:  ## Run integration tests only
	$(PYTEST) tests/ -v -m "integration"

test-e2e:  ## Run end-to-end tests only
	$(PYTEST) tests/ -v -m "e2e"

test-cov:  ## Run tests with coverage report
	$(PYTEST) tests/ -v --cov=src --cov-report=term-missing --cov-report=html

test-cov-xml:  ## Run tests with XML coverage report (for CI)
	$(PYTEST) tests/ -v --cov=src --cov-report=xml --cov-report=term-missing

test-watch:  ## Run tests in watch mode (rerun on file change)
	$(PYTEST) tests/ -v --looponfail

test-parallel:  ## Run tests in parallel
	$(PYTEST) tests/ -v -n auto

# ─── Code Quality ─────────────────────────────────────────────
lint:  ## Run linter (ruff)
	$(RUFF) check src/ tests/

lint-fix:  ## Run linter and auto-fix issues
	$(RUFF) check src/ tests/ --fix

format:  ## Run code formatter (ruff)
	$(RUFF) format src/ tests/

format-check:  ## Check formatting without applying changes
	$(RUFF) format src/ tests/ --check

type-check:  ## Run mypy type checker
	$(MYPY) src/

check: lint format-check type-check  ## Run all code quality checks

fix: lint-fix format  ## Auto-fix all fixable issues

# ─── Pre-commit ───────────────────────────────────────────────
pre-commit-install:  ## Install pre-commit hooks
	$(POETRY) run pre-commit install

pre-commit-run:  ## Run pre-commit on all files
	$(POETRY) run pre-commit run --all-files

pre-commit-update:  ## Update pre-commit hook versions
	$(POETRY) run pre-commit autoupdate

# ─── Database Migrations ─────────────────────────────────────
migrate-create:  ## Create a new migration (usage: make migrate-create msg="description")
	$(ALEMBIC) revision --autogenerate -m "$(msg)"

migrate-up:  ## Apply all pending migrations
	$(ALEMBIC) upgrade head

migrate-down:  ## Rollback last migration
	$(ALEMBIC) downgrade -1

migrate-down-to:  ## Rollback to a specific revision (usage: make migrate-down-to rev="abc123")
	$(ALEMBIC) downgrade $(rev)

migrate-history:  ## Show migration history
	$(ALEMBIC) history

migrate-current:  ## Show current migration revision
	$(ALEMBIC) current

migrate-stamp:  ## Stamp database with revision without running migrations
	$(ALEMBIC) stamp head

migrate-sql:  ## Generate SQL for pending migrations (dry run)
	$(ALEMBIC) upgrade head --sql

# ─── Shell ────────────────────────────────────────────────────
shell:  ## Open a Python shell with app context
	$(POETRY) run python -c "from src.core.config import settings; print('Settings loaded:', settings.app_name)"

shell-db:  ## Open database shell (psql)
	docker compose exec postgres psql -U llm_platform -d llm_platform

shell-redis:  ## Open Redis CLI
	docker compose exec redis redis-cli -a $(REDIS_PASSWORD)

# ─── Cleanup ──────────────────────────────────────────────────
clean: clean-pyc clean-cache  ## Remove Python and cache artifacts

clean-pyc:  ## Remove Python bytecode files
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

clean-cache:  ## Remove cache directories
	rm -rf .coverage coverage.xml htmlcov/ dist/ build/

clean-all: clean clean-docker  ## Full cleanup including Docker artifacts

clean-docker:  ## Remove Docker containers, volumes, and images
	$(DOCKER_COMPOSE) down -v --rmi all --remove-orphans 2>/dev/null || true
	docker system prune -f 2>/dev/null || true

# ─── Docker Build ─────────────────────────────────────────────
build:  ## Build Docker image (development target)
	$(DOCKER_COMPOSE) build

build-prod:  ## Build Docker image for production
	DOCKER_BUILDKIT=1 docker build --target production -t llm-platform:latest .

build-no-cache:  ## Build Docker image without cache
	$(DOCKER_COMPOSE) build --no-cache

# ─── Docker Operations ────────────────────────────────────────
docker-up:  ## Start all services
	$(DOCKER_COMPOSE) up -d

docker-down:  ## Stop all services
	$(DOCKER_COMPOSE) down

docker-logs:  ## Tail all docker logs
	$(DOCKER_COMPOSE) logs -f --tail=100

docker-ps:  ## List running containers
	$(DOCKER_COMPOSE) ps

docker-prune:  ## Prune unused Docker resources
	docker system prune -af --volumes

# ─── Utility ──────────────────────────────────────────────────
generate-secret:  ## Generate a random secret key for JWT
	@openssl rand -hex 64

env-init:  ## Initialize .env from .env.example if it doesn't exist
	@if [ ! -f .env ]; then cp .env.example .env && echo ".env created from .env.example"; else echo ".env already exists"; fi

deps-check:  ## Check for outdated dependencies
	$(POETRY) show --outdated

deps-audit:  ## Audit dependencies for security vulnerabilities
	$(POETRY) run pip-audit

tree:  ## Show dependency tree
	$(POETRY) show --tree

loc:  ## Count lines of code
	@find src/ -name "*.py" | xargs wc -l | tail -1
