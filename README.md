# Data Product Accelerator (`dpa`)

> A self-service CLI that deploys a fully governed **Data Product** on an OSS lakehouse from a single YAML file.

```
dpa deploy examples/customer_360.yml
```

---

## Problem Statement

Modern data teams are drowning in undiscovered, undocumented, and ungoverned data assets. Data engineers spend days manually wiring together storage, catalogues, quality checks, and pipelines every time a new dataset is needed. The result is a fractured landscape where:

- **No one knows what data exists** — tables are created without metadata, ownership, or descriptions
- **PII spreads silently** — sensitive fields land in production without tagging or access controls
- **Quality is an afterthought** — validation logic lives in ad-hoc scripts, not enforced as first-class constraints
- **Pipelines are undiscoverable** — a new analyst can't tell where a table comes from, how fresh it is, or who to contact when it breaks
- **Time-to-data is weeks** — provisioning a single governed dataset requires co-ordinating between infrastructure, platform, and governance teams

This problem is not new, but it is accelerating. As organisations move toward **Data Mesh** architectures — where domain teams own and publish their own data products — the need for a self-service, standardised deployment model becomes critical. Without it, governance becomes an audit trail of good intentions.

**The Data Product Accelerator (`dpa`) addresses this directly.** It encodes the full governance and engineering contract for a dataset into a single YAML file and automates every provisioning step — storage, table schema, metadata registration, quality rules, transformations, and orchestration — from that single source of truth. A domain team writes the config; the platform enforces the contract.

---

## Why This Matters

Data Products are the unit of value in a Data Mesh. But a Data Product without governance infrastructure is just a table with a good name. Real governance requires:

| Concern | Without `dpa` | With `dpa` |
|---|---|---|
| Schema definition | Manual DDL scripts, often lost | Pydantic-validated YAML, versioned in Git |
| PII handling | Discovered in audits (too late) | Declared at column level, auto-tagged in catalogue |
| Data quality | One-off scripts per team | Expectation suites auto-generated and enforced |
| Ownership | Undocumented or stale | Owner + team + SLA declared in config, registered in governance tool |
| Pipeline lineage | Tribal knowledge | Dagster asset graph generated and visible on deploy |
| Onboarding | Weeks of platform tickets | One YAML file + one command |

`dpa` is not a data catalogue or an orchestrator — it is the **deployment layer** that wires all of them together from a declared contract.

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

`dpa deploy` is the enforcement mechanism — every downstream system gets provisioned from that contract. Change the YAML and re-deploy; the contract updates across all systems.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     YAML Config                          │
│           DataProductConfig (Pydantic v2)                │
│   Validation is the first gate — deploy fails fast       │
└──────────────────────┬───────────────────────────────────┘
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
                          │orchestrate │  Jinja2 + ast.parse → Dagster @assets
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
- Provisioners can be run **in parallel** in a future version with `asyncio.gather`

---

## OSS Stack ↔ Azure Parallel Architecture

`dpa` is built entirely on open-source tools and runs locally with no cloud dependencies. Every component has a direct Azure-managed equivalent. The design intentionally mirrors what a production Azure deployment looks like, which means migrating from the OSS stack to Azure requires swapping service endpoints — not redesigning the architecture.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Conceptual Layer                                    │
├──────────────────────┬──────────────────────────┬───────────────────────────┤
│  OSS (local/self-    │  Azure Managed           │  Notes                    │
│  hosted)             │  Equivalent              │                           │
├──────────────────────┼──────────────────────────┼───────────────────────────┤
│ MinIO                │ Azure Data Lake           │ Both expose an S3/ADLS   │
│ (S3-compatible       │ Storage Gen2 (ADLS Gen2) │ API; boto3 works against  │
│  object store)       │                          │ ADLS with the right       │
│                      │                          │ endpoint config           │
├──────────────────────┼──────────────────────────┼───────────────────────────┤
│ Apache Iceberg       │ Delta Lake               │ Delta Lake is the default │
│ + Iceberg REST       │ (on ADLS Gen2)           │ table format in Azure     │
│ Catalog              │                          │ Databricks; Iceberg is    │
│                      │                          │ supported via Unity       │
│                      │                          │ Catalog external tables   │
├──────────────────────┼──────────────────────────┼───────────────────────────┤
│ Apache Spark         │ Azure Databricks         │ Databricks is managed     │
│ (standalone          │ (Spark-as-a-service)     │ Spark; same PySpark API,  │
│  cluster)            │                          │ no cluster management     │
├──────────────────────┼──────────────────────────┼───────────────────────────┤
│ dbt-core             │ dbt on Azure             │ dbt Cloud or dbt-core     │
│                      │ Databricks / Synapse     │ against Databricks SQL    │
│                      │                          │ Warehouse; same models,   │
│                      │                          │ different profile         │
├──────────────────────┼──────────────────────────┼───────────────────────────┤
│ OpenMetadata         │ Microsoft Purview        │ Both expose REST APIs for │
│ (OSS governance      │ (Azure Purview /         │ asset registration, PII   │
│  catalogue)          │  Fabric Data Catalog)    │ classification, and       │
│                      │                          │ lineage; Purview auto-    │
│                      │                          │ scans ADLS natively       │
├──────────────────────┼──────────────────────────┼───────────────────────────┤
│ Great Expectations   │ Azure Data Factory       │ ADF has built-in data     │
│ (column-level        │ Data Flow validation     │ flow validation; GE is    │
│  quality suites)     │ + dbt tests              │ richer for column-level   │
│                      │                          │ expectations at scale     │
├──────────────────────┼──────────────────────────┼───────────────────────────┤
│ Dagster              │ Azure Data Factory       │ ADF pipelines are the     │
│ (asset-centric       │ (pipelines) or           │ Azure-native orchestrator;│
│  orchestrator)       │ Azure Synapse Pipelines  │ Dagster's asset model has │
│                      │                          │ no direct ADF equivalent  │
│                      │                          │ but maps to ADF datasets  │
├──────────────────────┼──────────────────────────┼───────────────────────────┤
│ Iceberg REST         │ Azure Databricks         │ Unity Catalog is          │
│ Catalog              │ Unity Catalog            │ Databricks's managed      │
│                      │                          │ Iceberg/Delta catalogue;  │
│                      │                          │ REST-compatible           │
└──────────────────────┴──────────────────────────┴───────────────────────────┘
```

### Migration Path: OSS → Azure

Because each provisioner is an independent module that wraps a single service, migrating to Azure means replacing service clients — not rewriting business logic:

| Provisioner | Change required for Azure |
|---|---|
| `storage.py` | Update `boto3` endpoint from MinIO to ADLS Gen2 (`account.dfs.core.windows.net`); credentials become a service principal or managed identity |
| `iceberg.py` | Point PyIceberg REST catalog URI at Unity Catalog endpoint; or swap to `delta-rs` for Delta Lake |
| `metadata.py` | Replace OpenMetadata REST calls with Microsoft Purview REST API (`purview.azure.com`); register assets as `DataSet` entities |
| `quality.py` | No change — GE suites run against any datasource including ADLS-backed Databricks tables |
| `dbt.py` | Change dbt profile from `spark` to `databricks`; generated SQL stubs are unchanged |
| `orchestration.py` | Replace Dagster `@asset` templates with Azure Data Factory pipeline JSON templates, or keep Dagster (it runs on Azure as well) |

The YAML config schema, the Pydantic models, the CLI commands, and the provisioner interface are **entirely portable**. The cloud provider is a configuration detail.

---

## OSS Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Object Storage** | [MinIO](https://min.io/) | S3-compatible; identical API to AWS S3 and compatible with ADLS Gen2 via boto3 |
| **Table Format** | [Apache Iceberg](https://iceberg.apache.org/) | Open standard; ACID transactions, schema evolution, time travel; supported by Databricks, Snowflake, BigQuery |
| **Iceberg Catalog** | [Iceberg REST Catalog](https://github.com/tabular-io/iceberg-rest-fixture) | Decouples catalog from compute; PyIceberg and Spark both speak the same REST protocol |
| **Processing** | [Apache Spark 3.5](https://spark.apache.org/) | Included in docker-compose for production architecture parity; not called during `dpa deploy` |
| **Transformation** | [dbt-core](https://docs.getdbt.com/) | SQL-based transformations; model stubs generated from YAML schema, ready to implement |
| **Governance** | [OpenMetadata](https://open-metadata.org/) | Fully OSS metadata catalogue with PII tagging, lineage, and ownership APIs |
| **Quality** | [Great Expectations](https://greatexpectations.io/) | Column-level expectation framework; suites auto-generated from declared YAML rules |
| **Orchestration** | [Dagster](https://dagster.io/) | Asset-centric model maps directly to data products; SLA expressed as `FreshnessPolicy` |
| **CLI** | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) | Type-hint-driven CLI; annotated function signatures _are_ the command interface |
| **Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Declarative schema validation at the config layer; errors surfaced before any API call is made |
| **Catalog** | SQLite via [SQLModel](https://sqlmodel.tiangolo.com/) | Zero-dependency local state; tracks deployed resources and enables `dpa diff` |

---

## Quickstart

### Prerequisites

- Docker + Docker Compose
- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 1. Clone and install

```bash
git clone https://github.com/elam-byte/DataProductAccelerator
cd DataProductAccelerator
uv sync --extra dev
cp .env.example .env
```

### 2. Start the OSS stack

```bash
make up
```

Starts MinIO + Iceberg REST + Dagster. Services are ready when `make up` returns.

```
MinIO console:   http://localhost:9001  (minioadmin / minioadmin)
Iceberg REST:    http://localhost:8181/v1/config
Dagster UI:      http://localhost:3000
```

To also start OpenMetadata and Spark:

```bash
make up-full
# OpenMetadata UI: http://localhost:8585  (takes ~3 minutes to initialise)
# Spark Master UI: http://localhost:8080
```

### 3. Validate a config

```bash
uv run dpa validate examples/customer_360.yml
```

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

### 6. Deploy all examples

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

**Choice:** `IcebergProvisioner` uses PyIceberg REST catalog for table creation. dbt is used only as a transformation layer.

**Why not dbt-spark for DDL?**
- dbt-spark requires a live Spark thrift server to run `CREATE TABLE` — that couples provisioning to compute availability
- PyIceberg talks directly to the REST catalog: `catalog.create_table(identifier, schema, location)` — no Spark JVM needed for schema management
- PyIceberg exposes partition specs, sort orders, and table properties as Python objects, giving programmatic control over the full Iceberg table contract

**Tradeoff:** PyIceberg is less familiar to most dbt-centric data engineers. The trade is familiarity against architectural correctness: the catalog owns the schema contract; compute owns the transformation logic. This separation is the direction the OSS Iceberg ecosystem is heading (Unity Catalog, Nessie, Polaris all speak REST).

---

### 2. OpenMetadata REST API directly — not `metadata-ingestion` SDK

**Choice:** `MetadataProvisioner` uses a thin `httpx`-based client, not the official Python SDK.

**Why not the SDK?**
- `metadata-ingestion` installs 80+ transitive dependencies including Airflow providers — it conflicts with virtually every other Python project's dependency tree
- The SDK version must exactly match the running server version (0.13, 1.x, and 1.3 are all breaking API changes)
- A direct REST client is trivially mockable in tests with `respx`, making the governance provisioner as testable as any other module

**Tradeoff:** More boilerplate (~150 lines for the client class). The REST surface needed here — create table entity, apply PII tag, assign owner — is small and stable across OM versions.

---

### 3. Dagster for orchestration — not Airflow or APScheduler

**Choice:** Generate Dagster `@asset` definitions per table.

**Why Dagster?**
- Asset-centric model maps directly to data products — each table _is_ an asset, and the lineage between bronze → silver → gold is first-class in the Dagster UI
- `FreshnessPolicy` derived from `sla.freshness_hours` means the SLA is enforced in the orchestrator, not just documented in a README
- Dagster's asset graph is queryable via GraphQL, enabling future integrations (e.g. triggering materialisation from `dpa run`)

**Why not Airflow?** Airflow is task-centric — it runs DAGs, not assets. It has no native concept of a materialised dataset with a freshness contract. Expressing the same data product relationship in Airflow requires additional boilerplate (sensors, XComs, custom operators) that Dagster makes first-class.

**Tradeoff:** Dagster adds ~1GB to the docker-compose stack. Mitigated by its placement under `--profile full` and its independence from the core provisioning path.

---

### 4. Generate GE suite JSON directly — not the GE Python API

**Choice:** `QualityProvisioner` writes expectation suite JSON files rather than calling the Great Expectations Python API.

**Why?**
- GE v0.18+ (the "fluent API") is a complete rewrite from v0.15; the two APIs are not compatible and documentation is fragmented across versions
- Writing JSON directly is stable across GE minor versions — the expectation suite format has been consistent since v0.13
- The generated JSON files are human-readable, auditable in Git, and unit-testable without a running GE context

**Tradeoff:** Cannot use advanced GE features like custom expectation classes or multi-batch validation without extending the JSON manually. For auto-generated column rules from a YAML schema, the standard expectation types cover the full surface area.

---

### 5. Spark in docker-compose — not called by `dpa deploy`

**Choice:** `docker-compose.yml` includes a Spark cluster (`--profile full`), but `dpa deploy` never starts or calls Spark. All Iceberg DDL goes through PyIceberg.

**Why separate provisioning from execution?**
- A cold JVM start takes 15–30 seconds inside a CLI command. Provisioning should be fast and idempotent
- PyIceberg handles all schema DDL against the REST catalog without a Spark process
- The Spark cluster is the correct runtime for actual data transformation at scale — that belongs in `dpa run`, not `dpa deploy`

**Tradeoff:** `dpa run` (which materialises data by executing the Dagster assets against Spark) requires the Spark cluster to be healthy. The architectural boundary — provisioning ≠ execution — is the right one, even if it means two separate commands.

---

### 6. SQLite for the local catalog

**Choice:** `DeploymentManifest` is persisted in SQLite at `.dpa/catalog.db`.

**Why?**
- Zero setup — the catalog works in CI, offline, and before docker-compose is started
- Tracks what was deployed, when, and to which bucket and namespace — enabling `dpa diff` to surface schema drift
- SQLModel provides a typed ORM layer with a single import and no migrations config

**Tradeoff:** Not shareable across machines or team members. In a team deployment this would be replaced with a remote store (PostgreSQL, Azure Cosmos DB, etc.). The abstraction in `dpa/catalog/store.py` makes this a one-file change.

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
│   ├── storage.py            MinIO bucket + lifecycle policy (boto3)
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

Test coverage:
- Pydantic model validation edge cases (duplicate names, invalid types, decimal constraints, shorthand quality rule parsing)
- Each provisioner in isolation with mocked service clients
- Full `dpa deploy` round-trip against the docker-compose stack

---

## Scope Boundaries

| Feature | Status | Reason |
|---|---|---|
| Spark data execution | Architecture-only | Provisioning and execution are separate concerns; Spark is the execution runtime, not the provisioning tool |
| OpenMetadata lineage | Not implemented | Lineage registration requires source + sink entities to exist first; complex ordering dependency across provisioners |
| Schema evolution | Drift detection only (`dpa diff`) | Iceberg schema evolution via `update_schema()` against the REST catalog has edge cases; safe migration is a dedicated concern |
| Secret management | `.env.example` + README note | Production deployments should use Azure Key Vault, AWS Secrets Manager, or HashiCorp Vault; `.env` is a local development convenience |
| dbt execution | Stub generation only | Executing dbt-spark against a remote Spark cluster is a runtime concern, not a provisioning concern |
| Multi-user catalog | SQLite only | Single-operator local tool; team deployments swap `store.py` backend to PostgreSQL or a managed database |

---

## Local Services

| Service | URL | Credentials | Purpose |
|---|---|---|---|
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin | Browse buckets and objects |
| Iceberg REST | http://localhost:8181 | — | Iceberg catalog API |
| Dagster UI | http://localhost:3000 | — | Asset graph + materialization runs |
| OpenMetadata | http://localhost:8585 | admin / admin | Governance catalogue (`--profile full`) |
| Spark Master UI | http://localhost:8080 | — | Spark cluster overview (`--profile full`) |

---

## Environment Variables

All settings use the `DPA_` prefix. Copy `.env.example` to `.env` to get started.

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
