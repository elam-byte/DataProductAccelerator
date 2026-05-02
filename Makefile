.PHONY: help up up-full down logs validate deploy demo test lint fmt

# ── defaults ──────────────────────────────────────────────────────────────────
PRODUCT ?= customer_360

help:
	@echo ""
	@echo "Data Product Accelerator — Make targets"
	@echo ""
	@echo "  make up            Start the minimal stack (MinIO + Iceberg REST + Dagster)"
	@echo "  make up-full       Start the full stack (+ OpenMetadata + Spark)"
	@echo "  make down          Stop all services and remove containers"
	@echo "  make logs          Tail all service logs"
	@echo ""
	@echo "  make validate      Validate examples/customer_360.yml (PRODUCT=name to override)"
	@echo "  make deploy        Deploy examples/customer_360.yml (PRODUCT=name to override)"
	@echo "  make demo          Deploy all example products"
	@echo ""
	@echo "  make test          Run unit tests"
	@echo "  make test-int      Run integration tests (requires make up first)"
	@echo "  make lint          Run ruff linter"
	@echo "  make fmt           Auto-format with ruff"
	@echo ""

# ── docker stack ──────────────────────────────────────────────────────────────
up:
	docker compose up -d --wait
	@echo ""
	@echo "  MinIO console:   http://localhost:9001  (minioadmin / minioadmin)"
	@echo "  Iceberg REST:    http://localhost:8181"
	@echo "  Dagster UI:      http://localhost:3000"
	@echo ""

up-full:
	docker compose --profile full up -d --wait
	@echo ""
	@echo "  OpenMetadata:    http://localhost:8585"
	@echo "  Spark Master UI: http://localhost:8080"
	@echo ""

down:
	docker compose --profile full down

logs:
	docker compose logs -f

# ── dpa commands ──────────────────────────────────────────────────────────────
validate:
	uv run dpa validate examples/$(PRODUCT).yml

deploy:
	uv run dpa deploy examples/$(PRODUCT).yml

demo:
	uv run dpa deploy examples/customer_360.yml
	uv run dpa deploy examples/order_events.yml
	uv run dpa catalog list

# ── testing ───────────────────────────────────────────────────────────────────
test:
	uv run pytest tests/unit/ -v

test-int:
	uv run pytest tests/integration/ -v -m integration

# ── code quality ──────────────────────────────────────────────────────────────
lint:
	uv run ruff check dpa/ tests/

fmt:
	uv run ruff format dpa/ tests/
	uv run ruff check --fix dpa/ tests/
