# Data Product Accelerator (`dpa`)

> A self-service CLI that deploys a fully governed **Data Product** on an OSS lakehouse from a single YAML file.

```
dpa deploy examples/customer_360.yml
```

One command provisions MinIO storage, Iceberg tables, OpenMetadata governance, Great Expectations quality suites, dbt transformation stubs, and Dagster orchestration assets — all wired together from a single source-of-truth config.

---

## The Core Idea

A **Data Product** is a contract. The YAML file _is_ that contract:

```yaml
name: customer_360
version: "1.0.0"
owner:
  team: data-platform
  email: data-platform@company.com
sla:
  freshness_hours: 24
tables:
  - name: customers
    tier: gold
    schema:
      - name: customer_id
        type: string
        nullable: false
      - name: email
        type: string
        pii: true          # → PII.Sensitive tag auto-applied in OpenMetadata
    quality_rules:
      - not_null: [customer_id]
      - email_format: [email]
```

`dpa deploy` is the enforcement mechanism — every downstream system gets provisioned from that contract.

---

## Architecture

```
┌────────────────────────────────────���────────────────────┐
│                     YAML Config                         │
│           DataProductConfig (Pydantic v2)               │
│   Validation is the first gate — deploy fails fast      │
└──────────────────────┬───────────────────────��──────────┘
                       │
         ┌─────────────▼─────────────┐
         │     dpa deploy            │
         │  (Typer CLI orchestrator) │
         └──┬──┬──┬──┬──┬──┬────────┘
            │  │  │  │  │  │
   ┌────────▼┐ │  │  │  │  │
   │ storage │ │  │  │  │  │  boto3 → MinIO
   └─────────┘ │  │  │  │  │
        ┌──────▼─┐ │  │  │  │
        │iceberg │ │  │  │  │  PyIceberg REST → Iceberg catalog
        └────────┘ │  │  │  │
             ┌─────▼──┐ │  │  │
             │metadata│ │  │  │  httpx → OpenMetadata API
             └────────┘ │  │  │
                  ┌─────▼─┐ │  │
                  │quality│ │  │  JSON writer → Great Expectations
                  └───────┘ │  │
                       ┌────▼─┐ │
                       │ dbt  │ │  Jinja2 → dbt model stubs
                       └──────┘ │
                          ┌─────▼──────┐
                          │orchestrate │  Jinja2+ast.parse → Dagster @assets
                          └────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  DeploymentManifest    │
                    │  (SQLite local catalog)│
                    └────────────────────────┘
```

### Provisioner Pattern

Each provisioner is a pure function:

```
DataProductConfig → ProvisionResult
```

No provisioner has side effects on another. The deploy command is a pure orchestrator — it has no business logic of its own. This means:

- Each provisioner is **independently testable** (mock only its service)
- Each provisioner is **independently skippable** (`--skip-metadata`, `--skip-quality`, etc.)
- Provisioners can be run **in parallel** in a future version

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Object Storage** | [MinIO](https://min.io/) | S3-compatible OSS; drop-in replacement for AWS S3 in production |
| **Table Format** | [Apache Iceberg](https://iceberg.apache.org/) | Truly open; ACID transactions, schema evolution, time travel; vendor-neutral |
| **Iceberg Catalog** | [Iceberg REST Catalog](https://github.com/tabular-io/iceberg-rest-fixture) | Decouples catalog from compute; PyIceberg and Spark both speak REST |
| **Processing** | [Apache Spark 3.5](https://spark.apache.org/) | In docker-compose for architecture completeness; not called during `dpa deploy` |
| **Transformation** | [dbt-core](https://docs.getdbt.com/) | SQL-based transformations; stubs generated from YAML, ready to implement |
| **Governance** | [OpenMetadata](https://open-metadata.org/) | Fully OSS metadata catalog with PII tagging, lineage, and ownership |
| **Quality** | [Great Expectations](https://greatexpectations.io/) | Column-level expectation framework; suites auto-generated from YAML rules |
| **Orchestration** | [Dagster](https://dagster.io/) | Asset-centric model maps directly to data products; visual asset graph |
| **CLI** | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) | Type-hint-driven; reads like documentation; beautiful terminal output |
| **Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Schema validation at the config layer; errors caught before any API call |
| **Catalog** | SQLite via [SQLModel](https://sqlmodel.tiangolo.com/) | Zero-dependency local state; tracks what was deployed and when |

---

## Quickstart

### Prerequisites

- Docker + Docker Compose
- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (installed automatically by bootstrap)

### 1. Clone and install

```bash
git clone https://github.com/your-username/DataProductAccelerator
cd DataProductAccelerator
pip install uv   # or: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --extra dev
cp .env.example .env
```

### 2. Start the OSS stack

```bash
make up
```

This starts MinIO + Iceberg REST + Dagster. Services are ready when `make up` returns.

```
MinIO console:   http://localhost:9001  (minioadmin / minioadmin)
Iceberg REST:    http://localhost:8181/v1/config
Dagster UI:      http://localhost:3000
```

To also start OpenMetadata and Spark:

```bash
make up-full
# OpenMetadata UI: http://localhost:8585  (takes ~3 minutes to start)
# Spark Master UI: http://localhost:8080
```

### 3. Validate a config

```bash
uv run dpa validate examples/customer_360.yml
```

Output:

```
───────────── Validating Data Product Config ─────────────
✓  Config is valid: customer_360 v1.0.0

             Data Product: customer_360 v1.0.0
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Table           ┃ Tier   ┃ Columns ┃ PII Fields   ┃ Rules ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━┩
│ raw_customers   │ BRONZE │ 7       │ email, phone │ 2     │
│ customers       │ SILVER │ 8       │ email, phone │ 4     │
│ customer_summary│ GOLD   │ 10      │ email        │ 4     │
└─────────────────┴────────┴─────────┴──────────────┴───────┘
```

### 4. Deploy

```bash
uv run dpa deploy examples/customer_360.yml
```

What gets created:

| Resource | Location |
|---|---|
| MinIO bucket | `http://localhost:9001` → `dpa-customer-360` |
| Iceberg tables | 3 tables in namespace `customer_360` |
| OpenMetadata entities | `http://localhost:8585` → search "customer_360" |
| GE suites | `ge_project/expectations/customer_360__*.json` |
| dbt stubs | `dbt_project/models/generated/customer_360/*.sql` |
| Dagster assets | `dagster_pipelines/generated/customer_360_assets.py` |

### 5. Inspect

```bash
uv run dpa status customer_360
uv run dpa catalog list
```

### 6. Deploy the demo set

```bash
make demo   # deploys customer_360 + order_events
```

---

## CLI Reference

```
dpa validate <config.yml>                         Validate config without deploying
dpa validate <config.yml> --run-quality           Also execute GE checkpoint

dpa deploy <config.yml>                           Full deploy
dpa deploy <config.yml> --dry-run                 Show what would be created
dpa deploy <config.yml> --skip-metadata           Skip OpenMetadata registration
dpa deploy <config.yml> --skip-quality            Skip GE suite generation
dpa deploy <config.yml> --skip-dbt                Skip dbt stub generation
dpa deploy <config.yml> --skip-orchestration      Skip Dagster asset generation
dpa deploy <config.yml> --force                   Re-deploy even if version exists

dpa status <product_name>                         Show deployment status + resources
dpa teardown <product_name>                       Remove all provisioned resources
dpa teardown <product_name> --force               Skip confirmation prompt

dpa catalog list                                  List all deployed products
dpa catalog list --format json                    JSON output
dpa catalog show <product_name>                   Full detail view
```

---

## Config Reference

```yaml
name: my_product          # lowercase, underscores only, must start with letter
version: "1.0.0"          # semver — x.y.z

description: "Optional human-readable description."

owner:
  team: data-platform      # team name (used for OpenMetadata ownership)
  email: team@company.com  # EmailStr validated
  slack_channel: "#data-platform"   # optional

sla:
  freshness_hours: 24      # max acceptable data age (1–8760)
  availability_pct: 99.9   # target uptime %

tags:
  - domain:customer        # free-form tags applied to all tables in OpenMetadata

tables:
  - name: my_table
    tier: bronze            # bronze | silver | gold
    description: "Optional."

    schema:
      - name: column_name   # must be a valid SQL identifier
        type: string        # string | integer | long | double | float | boolean
                            # timestamp | date | decimal | binary | array | map | struct
        nullable: true      # default: true
        pii: false          # true → PII.Sensitive tag in OpenMetadata
        description: "Optional column description."
        decimal_precision: 18   # required when type: decimal
        decimal_scale: 4        # required when type: decimal

    partition_by:
      - column: created_at
        transform: day      # identity | year | month | day | hour | bucket | truncate
        num_buckets: 16     # required when transform: bucket

    quality_rules:
      # Shorthand (column list):
      - not_null: [column_name]
      - unique: [column_name]
      - email_format: [email_column]

      # Shorthand with params:
      - accepted_values:
          columns: [status]
          params:
            values: [active, inactive, pending]

      - min_value:
          columns: [count]
          params:
            min: 0

      - regex:
          columns: [phone]
          params:
            pattern: '^\+?[1-9]\d{7,14}$'
```

---

## Key Design Decisions & Tradeoffs

### 1. PyIceberg for DDL — not dbt-spark

**Choice:** `IcebergProvisioner` uses PyIceberg REST catalog for table creation. dbt is used only as a transformation layer (generates SQL stubs).

**Why not dbt-spark for DDL?**
- dbt-spark requires a live Spark thrift server just to run `CREATE TABLE` — that couples provisioning to compute being available
- PyIceberg talks directly to the REST catalog: `catalog.create_table(identifier, schema, location)` — no Spark JVM needed
- PyIceberg exposes partition specs, sort orders, and table properties as Python objects, which is useful for interview-level depth conversations

**Tradeoff:** PyIceberg is less familiar to most dbt-centric data engineers. The learning curve is real, but the separation of concerns (catalog owns schema, compute owns transformation) is architecturally correct and is the direction the OSS Iceberg ecosystem is heading.

---

### 2. OpenMetadata REST API directly — not `metadata-ingestion` SDK

**Choice:** `MetadataProvisioner` uses a thin `httpx`-based client, not the official Python SDK.

**Why not the SDK?**
- `metadata-ingestion` installs 80+ transitive dependencies including Airflow providers — it will conflict with virtually every other Python project
- The SDK version must exactly match the running server version (0.13, 1.x, and 1.3 are all breaking API changes)
- REST directly gives complete control over the request shape and is trivially mockable in tests with `respx`

**Tradeoff:** More boilerplate (~150 lines for the client class). Worth it for a stable, testable integration. The ADR documents this decision explicitly, which signals engineering maturity.

---

### 3. Dagster for orchestration — not Airflow or APScheduler

**Choice:** Generate Dagster `@asset` definitions per table.

**Why Dagster?**
- Asset-centric model maps directly to data products — each table _is_ an asset, and the lineage between bronze → silver → gold is first-class
- The Dagster UI running locally shows the asset graph for every deployed product — this is a 30-second interview moment that no simpler scheduler can replicate
- `freshness_policy` derived from `sla.freshness_hours` means the SLA is enforced in the orchestrator, not just documented

**Why not Airflow?** Airflow is task-centric (runs DAGs), not asset-centric. The mental model doesn't map as naturally to the concept of "a data product as a set of materializable assets." Airflow would require more boilerplate to express the same intent.

**Tradeoff:** Dagster adds ~1GB to docker-compose. Mitigated by the `--profile full` flag and the Dagster service being separated from the core provisioning path.

---

### 4. Generate GE suite JSON directly — not the GE Python API

**Choice:** `QualityProvisioner` writes expectation suite JSON files. It does not call the GE Python API.

**Why?**
- GE v0.18+ (the "fluent API") is a complete rewrite from v0.15. Documentation is fragmented; most StackOverflow answers are for the old API
- Writing JSON directly is stable across GE minor versions
- The JSON format is readable, auditable, and testable without running GE at all

**Tradeoff:** Cannot use advanced GE features like custom expectation classes. For the scope of this project (auto-generated column rules from YAML), this is not a constraint.

---

### 5. Embedded Spark — not called by `dpa deploy`

**Choice:** `docker-compose.yml` includes a Spark cluster (`--profile full`), but `dpa deploy` never calls Spark. The Iceberg DDL path uses PyIceberg only.

**Why?**
- A cold JVM start inside a CLI tool takes 15–30 seconds. The deploy command would hang visibly before any progress appeared. This kills the demo experience.
- PyIceberg handles all DDL against the REST catalog without Spark
- The Spark cluster exists in docker-compose to show the production architecture — it's the right place to run dbt transformations at scale

**Tradeoff:** `dpa run` (which would actually materialize data) requires Spark to be running. This is the right separation: provisioning ≠ execution.

---

### 6. SQLite for local catalog

**Choice:** `DeploymentManifest` is persisted in a SQLite database at `.dpa/catalog.db`.

**Why?**
- Zero setup, zero services — the catalog works in CI, offline, and before docker-compose is started
- Tracks what was deployed, when, and to which bucket/namespace — `dpa diff` can compare current config against the deployed state
- SQLModel gives a typed ORM layer with one import

**Tradeoff:** Not shareable across machines. In a team setting this would be replaced with a remote store (PostgreSQL, Dynamo, etc.). The abstraction in `dpa/catalog/store.py` makes this a one-file swap.

---

## Project Structure

```
dpa/
├── main.py                   Typer app entrypoint
├── models/
│   ├── data_product.py       DataProductConfig + all nested Pydantic models
│   ├── enums.py              DataTier, ColumnType, QualityRuleType, PartitionTransform
│   └── manifest.py           DeploymentManifest — the audit trail
├── config/
│   ├── __init__.py           load_product_config() — YAML → validated model
│   └── settings.py           Pydantic BaseSettings (DPA_ env vars)
├── commands/
│   ├── deploy.py             Orchestrates all provisioners
│   ├── validate.py           Config validation + optional GE checkpoint run
│   ├── status.py             Rich status panel for a deployed product
│   ├── teardown.py           Reverse all provisioner actions
│   └── catalog.py            List + show deployed products
├── provisioners/
│   ├── base.py               Provisioner ABC + ProvisionResult dataclass
│   ├── storage.py            MinIO bucket + lifecycle (boto3)
│   ├── iceberg.py            Iceberg tables via PyIceberg REST catalog
│   ├── metadata.py           OpenMetadata entities via httpx
│   ├── quality.py            Great Expectations suite JSON generator
│   ├── dbt.py                dbt model stub generator (Jinja2)
│   └── orchestration.py      Dagster @asset generator (Jinja2 + ast.parse)
├── catalog/
│   ├── store.py              SQLite persistence (SQLModel)
│   └── models.py             DeployedProduct ORM model
└── templates/
    ├── dbt_model.sql.j2      Bronze/silver/gold SQL stubs
    ├── dbt_source.yml.j2     dbt sources.yml
    ├── dbt_schema.yml.j2     dbt schema.yml with column tests
    └── dagster_asset.py.j2   Dagster @asset definitions
```

---

## Running Tests

```bash
# Unit tests — no services required (mocked boto3, mocked httpx)
make test

# Integration tests — requires make up first
make test-int
```

Test coverage targets:
- Pydantic model validation edge cases (duplicate names, invalid types, decimal constraints)
- Each provisioner in isolation with mocked service clients
- Full `dpa deploy` round-trip against the docker-compose stack

---

## What's Not Implemented (and Why)

| Feature | Status | Reason |
|---|---|---|
| Spark data execution | Architecture-only | Cold JVM in CLI = 30s hang; separate concern from provisioning |
| OpenMetadata lineage | Not implemented | Requires source + sink entities to pre-exist; complex ordering dependency |
| Schema evolution | Detect only (`dpa diff`) | Iceberg `update_schema()` against REST catalog has edge cases that would consume a week |
| Secret management | README note only | Production would use Vault or AWS Secrets Manager; hardcoded in `.env.example` by design for local dev |
| dbt execution | Generate stubs only | dbt-spark against remote Spark adds 10 minutes of setup for no demo value |
| Multi-user catalog | SQLite only | Single-user local tool; team deployment would swap to PostgreSQL in `store.py` |

---

## Local Services

| Service | URL | Credentials | Purpose |
|---|---|---|---|
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin | Browse buckets and objects |
| Iceberg REST | http://localhost:8181 | — | Iceberg catalog API |
| Dagster UI | http://localhost:3000 | — | Asset graph + materialization runs |
| OpenMetadata | http://localhost:8585 | admin / admin | Governance catalog (`--profile full`) |
| Spark Master UI | http://localhost:8080 | — | Spark cluster overview (`--profile full`) |

---

## Environment Variables

All settings have the `DPA_` prefix. Copy `.env.example` to `.env` to get started.

| Variable | Default | Description |
|---|---|---|
| `DPA_MINIO_ENDPOINT` | `http://localhost:9000` | MinIO S3 API endpoint |
| `DPA_MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `DPA_MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `DPA_ICEBERG_CATALOG_URI` | `http://localhost:8181` | Iceberg REST catalog URI |
| `DPA_ICEBERG_WAREHOUSE` | `s3://iceberg-warehouse/` | S3 path for table data |
| `DPA_OPENMETADATA_URL` | `http://localhost:8585` | OpenMetadata API base URL |
| `DPA_OPENMETADATA_TOKEN` | _(empty)_ | JWT — generate with `docker exec openmetadata-server ...` |
| `DPA_CATALOG_DB_PATH` | `./.dpa/catalog.db` | SQLite catalog path |
| `DPA_DAGSTER_HOME` | `./dagster_pipelines` | Dagster workspace root |
| `DPA_GE_PROJECT_ROOT` | `./ge_project` | Great Expectations root |
| `DPA_DBT_PROJECT_ROOT` | `./dbt_project` | dbt project root |

---

## License

Apache 2.0
