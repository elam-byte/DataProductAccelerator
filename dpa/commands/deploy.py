"""dpa deploy — provisions all resources for a data product from a YAML config."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from dpa.catalog import store as catalog
from dpa.config import load_product_config
from dpa.models import DataProductConfig, DeploymentManifest, ProvisionedTable
from dpa.provisioners.base import Provisioner, ProvisionResult
from dpa.provisioners.iceberg import IcebergProvisioner
from dpa.provisioners.storage import StorageProvisioner
from dpa.utils import logging as log
from dpa.utils.errors import ConfigValidationError, ProvisionerError

app = typer.Typer(help="Deploy a data product from a YAML config file.")


@app.callback(invoke_without_command=True)
def deploy(
    config_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Path to the data product YAML config",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print what would be created without making any API calls"),
    ] = False,
    skip_metadata: Annotated[
        bool,
        typer.Option("--skip-metadata", help="Skip OpenMetadata registration"),
    ] = False,
    skip_quality: Annotated[
        bool,
        typer.Option("--skip-quality", help="Skip Great Expectations suite generation"),
    ] = False,
    skip_dbt: Annotated[
        bool,
        typer.Option("--skip-dbt", help="Skip dbt model stub generation"),
    ] = False,
    skip_orchestration: Annotated[
        bool,
        typer.Option("--skip-orchestration", help="Skip Dagster asset generation"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-deploy even if this product version is already deployed"),
    ] = False,
) -> None:
    """
    Deploy a data product: provisions MinIO storage, Iceberg tables,
    OpenMetadata registration, Great Expectations suites, dbt stubs, and Dagster assets.
    """
    log.section(f"Deploying Data Product from {config_path.name}")

    try:
        config = load_product_config(config_path)
    except ConfigValidationError as e:
        log.error(str(e))
        raise typer.Exit(code=1) from None

    log.info(f"Product: [bold]{config.name}[/bold] v{config.version}  ({len(config.tables)} tables)")

    if dry_run:
        _print_dry_run(config)
        return

    existing = catalog.get_manifest(config.name)
    if existing and existing.version == config.version and not force:
        log.warning(
            f"Product [bold]{config.name}[/bold] v{config.version} is already deployed. "
            "Use --force to re-deploy."
        )
        raise typer.Exit(code=0)

    errors: list[str] = []
    provisioned_tables: list[ProvisionedTable] = []

    # ── Phase 1: Storage + Iceberg (always run) ────────────────────────────
    results = _run_provisioners(
        config,
        [StorageProvisioner(), IcebergProvisioner()],
        errors,
    )

    # Build ProvisionedTable entries from Iceberg results
    iceberg_result = next((r for r in results if r.provisioner == "iceberg"), None)
    if iceberg_result and iceberg_result.success:
        for table in config.tables:
            fqn = f"{config.namespace}.{table.name}"
            location = (
                f"s3://{config.bucket_name}/{table.tier.value}/{table.name}"
            )
            pt = ProvisionedTable(
                name=table.name,
                tier=table.tier,
                iceberg_location=location,
                iceberg_fqn=fqn,
            )
            provisioned_tables.append(pt)

    # ── Phase 2: Governance (optional) ────────────────────────────────────
    if not skip_metadata:
        _run_metadata_provisioner(config, provisioned_tables, errors)

    # ── Phase 3: Quality (optional) ───────────────────────────────────────
    if not skip_quality:
        _run_quality_provisioner(config, provisioned_tables, errors)

    # ── Phase 4: dbt stubs (optional) ─────────────────────────────────────
    if not skip_dbt:
        _run_dbt_provisioner(config, provisioned_tables, errors)

    # ── Phase 5: Dagster assets (optional) ────────────────────────────────
    dagster_job_path: str | None = None
    if not skip_orchestration:
        dagster_job_path = _run_orchestration_provisioner(config, provisioned_tables, errors)

    # ── Persist manifest ───────────────────────────────────────────────────
    status = "partial" if errors else "success"
    manifest = DeploymentManifest(
        product_name=config.name,
        version=config.version,
        deployed_at=datetime.utcnow(),
        minio_bucket=config.bucket_name,
        iceberg_namespace=config.namespace,
        tables=provisioned_tables,
        dagster_job_path=dagster_job_path,
        status=status,
        errors=errors,
    )
    catalog.save_manifest(manifest)

    log.console.print()
    log.console.print(log.manifest_panel(manifest))

    if errors:
        raise typer.Exit(code=1)


# ── helper runners ─────────────────────────────────────────────────────────────


def _run_provisioners(
    config: DataProductConfig,
    provisioners: list[Provisioner],
    errors: list[str],
) -> list[ProvisionResult]:
    results: list[ProvisionResult] = []
    with log.make_progress() as progress:
        for p in provisioners:
            task = progress.add_task(f"[cyan]{p.name}[/cyan] provisioner…", total=None)
            try:
                result = p.provision(config)
                results.append(result)
                if result.skipped:
                    progress.update(task, description=f"[yellow]↷ {p.name}[/yellow] skipped")
                elif result.success:
                    progress.update(task, description=f"[green]✓ {p.name}[/green]")
                else:
                    progress.update(task, description=f"[red]✗ {p.name}[/red]")
                    errors.append(result.message)
            except ProvisionerError as e:
                progress.update(task, description=f"[red]✗ {p.name}[/red]")
                errors.append(str(e))
                results.append(ProvisionResult.fail(p.name, str(e)))
    return results


def _run_metadata_provisioner(
    config: DataProductConfig,
    provisioned_tables: list[ProvisionedTable],
    errors: list[str],
) -> None:
    try:
        from dpa.provisioners.metadata import MetadataProvisioner

        p = MetadataProvisioner()
        results = _run_provisioners(config, [p], errors)
        result = results[0] if results else None
        if result and result.success and result.resource_ids:
            for pt, fqn in zip(provisioned_tables, result.resource_ids):
                pt.openmetadata_fqn = fqn
    except ImportError:
        log.warning("OpenMetadata provisioner not available — skipping")


def _run_quality_provisioner(
    config: DataProductConfig,
    provisioned_tables: list[ProvisionedTable],
    errors: list[str],
) -> None:
    try:
        from dpa.provisioners.quality import QualityProvisioner

        p = QualityProvisioner()
        results = _run_provisioners(config, [p], errors)
        result = results[0] if results else None
        if result and result.success:
            for pt, path in zip(provisioned_tables, result.resource_ids):
                pt.ge_suite_path = path
    except ImportError:
        log.warning("Quality provisioner not available — skipping")


def _run_dbt_provisioner(
    config: DataProductConfig,
    provisioned_tables: list[ProvisionedTable],
    errors: list[str],
) -> None:
    try:
        from dpa.provisioners.dbt import DbtProvisioner

        p = DbtProvisioner()
        results = _run_provisioners(config, [p], errors)
        result = results[0] if results else None
        if result and result.success:
            for pt, path in zip(provisioned_tables, result.resource_ids):
                pt.dbt_model_path = path
    except ImportError:
        log.warning("dbt provisioner not available — skipping")


def _run_orchestration_provisioner(
    config: DataProductConfig,
    provisioned_tables: list[ProvisionedTable],
    errors: list[str],
) -> str | None:
    try:
        from dpa.provisioners.orchestration import OrchestrationProvisioner

        p = OrchestrationProvisioner()
        results = _run_provisioners(config, [p], errors)
        result = results[0] if results else None
        if result and result.success and result.resource_ids:
            for pt, key in zip(provisioned_tables, result.resource_ids):
                pt.dagster_asset_key = key
            return result.message  # job file path stored in message
    except ImportError:
        log.warning("Orchestration provisioner not available — skipping")
    return None


def _print_dry_run(config: DataProductConfig) -> None:
    log.section("Dry Run — Resources that would be created")
    log.console.print(f"\n[bold]MinIO bucket:[/bold] {config.bucket_name}")
    log.console.print(f"[bold]Iceberg namespace:[/bold] {config.namespace}")
    log.console.print("\n[bold]Tables:[/bold]")
    for t in config.tables:
        loc = f"s3://{config.bucket_name}/{t.tier.value}/{t.name}"
        log.console.print(f"  • [bold]{t.name}[/bold] → {loc}  ({len(t.schema_)} columns)")
    log.console.print()
    log.info("No resources created (--dry-run)")
