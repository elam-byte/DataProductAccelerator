# Data Product Accelerator — Codebase Guide

## What this project does
`dpa` is a CLI tool that reads a YAML config and automatically provisions every resource needed to run a governed data product on an OSS lakehouse: MinIO storage, Iceberg tables, OpenMetadata registration, Great Expectations quality suites, dbt transformation stubs, and Dagster orchestration assets.

## Running commands
```bash
uv run dpa --help
uv run dpa validate examples/customer_360.yml
uv run dpa deploy examples/customer_360.yml --dry-run
uv run dpa deploy examples/customer_360.yml
uv run dpa status customer_360
uv run dpa catalog list
uv run dpa teardown customer_360
```

## Starting the local stack
```bash
make up          # starts MinIO + Iceberg REST + Dagster (default profile)
make up-full     # also starts OpenMetadata + Spark
make demo        # deploys all example products
```

## Key files
- `dpa/models/data_product.py` — Pydantic domain models (DataProductConfig, TableModel, etc.)
- `dpa/models/enums.py` — DataTier, ColumnType, QualityRuleType, PartitionTransform
- `dpa/provisioners/` — one file per concern: storage, iceberg, metadata, quality, dbt, orchestration
- `dpa/provisioners/base.py` — Provisioner ABC + ProvisionResult dataclass
- `dpa/commands/deploy.py` — main orchestration; calls provisioners in order
- `dpa/config/__init__.py` — load_product_config() — YAML → DataProductConfig
- `dpa/config/settings.py` — Pydantic BaseSettings from .env (DPA_ prefix)
- `dpa/catalog/store.py` — SQLite-backed catalog for tracking deployed products
- `docker-compose.yml` — all OSS services; `--profile full` adds OM + Spark

## Architecture principle
Each Provisioner is a pure function: DataProductConfig → ProvisionResult. No cross-provisioner side effects. The deploy command is a simple orchestrator — it has no business logic.

## Adding a new provisioner
1. Create `dpa/provisioners/<name>.py` implementing `Provisioner` ABC
2. Add `provision()` and `teardown()` methods
3. Wire into `dpa/commands/deploy.py` (see the `_run_*_provisioner` pattern)

## Testing
```bash
uv run pytest tests/unit/ -v                    # no services required
uv run pytest tests/integration/ -m integration  # requires make up first
```

## Environment variables
All settings live in `.env` with `DPA_` prefix. Copy `.env.example` to `.env` to get started. Production deployments should use Vault or AWS Secrets Manager instead of `.env`.
