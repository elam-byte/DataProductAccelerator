from typing import Annotated

import typer

from dpa.catalog import store as catalog
from dpa.config import load_product_config
from dpa.models import DataProductConfig
from dpa.provisioners.iceberg import IcebergProvisioner
from dpa.provisioners.storage import StorageProvisioner
from dpa.utils import logging as log
from dpa.utils.errors import ConfigValidationError

app = typer.Typer(help="Remove all provisioned resources for a data product.")


@app.callback(invoke_without_command=True)
def teardown(
    product_name: Annotated[str, typer.Argument(help="Name of the data product to remove")],
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to the config YAML (used if product is not in catalog)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Tear down all resources created by dpa deploy for a product."""
    if not force:
        confirmed = typer.confirm(
            f"This will delete all resources for '[bold]{product_name}[/bold]'. Continue?"
        )
        if not confirmed:
            raise typer.Abort()

    log.section(f"Tearing Down: {product_name}")

    # Resolve config: prefer catalog manifest, fall back to --config
    config = _resolve_config(product_name, config_path)
    if config is None:
        log.error(
            f"Product '{product_name}' not found in catalog and no --config provided."
        )
        raise typer.Exit(code=1)

    errors: list[str] = []

    # Tear down in reverse provisioner order
    for P in [IcebergProvisioner, StorageProvisioner]:
        p = P()
        try:
            result = p.teardown(config)
            if result.skipped:
                log.warning(f"{p.name}: {result.message}")
            elif result.success:
                log.success(f"{p.name}: {result.message}")
            else:
                log.error(f"{p.name}: {result.message}")
                errors.append(result.message)
        except Exception as e:
            log.error(f"{p.name} teardown failed: {e}")
            errors.append(str(e))

    catalog.delete_product(product_name)

    if errors:
        log.warning("Teardown completed with errors (see above)")
        raise typer.Exit(code=1)
    else:
        log.success(f"Product '{product_name}' fully removed")


def _resolve_config(product_name: str, config_path: str | None) -> DataProductConfig | None:
    if config_path:
        from pathlib import Path

        try:
            return load_product_config(Path(config_path))
        except ConfigValidationError as e:
            log.error(str(e))
            return None

    manifest = catalog.get_manifest(product_name)
    if manifest:
        # Reconstruct a minimal config from the manifest for teardown purposes
        from dpa.models import DataProductConfig, OwnerModel, SLAModel, TableModel
        from dpa.models.enums import ColumnType

        tables = [
            TableModel.model_validate(
                {
                    "name": t.name,
                    "tier": t.tier,
                    "schema": [{"name": "id", "type": "string"}],
                }
            )
            for t in manifest.tables
        ]
        return DataProductConfig(
            name=manifest.product_name,
            version=manifest.version,
            owner=OwnerModel(team="unknown", email="unknown@unknown.com"),
            sla=SLAModel(freshness_hours=24),
            tables=tables,
        )
    return None
