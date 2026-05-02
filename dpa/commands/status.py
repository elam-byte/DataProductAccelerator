from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from dpa.catalog import store as catalog
from dpa.utils import logging as log

app = typer.Typer(help="Show the deployment status of a data product.")


@app.callback(invoke_without_command=True)
def status(
    product_name: Annotated[str, typer.Argument(help="Name of the deployed data product")],
) -> None:
    """Show deployment status, resources, and quality summary for a data product."""
    manifest = catalog.get_manifest(product_name)
    if not manifest:
        log.error(f"No deployment found for product '[bold]{product_name}[/bold]'")
        log.info("Run [bold]dpa catalog list[/bold] to see all deployed products.")
        raise typer.Exit(code=1)

    log.section(f"Status: {product_name}")

    # Overview panel
    lines = [
        f"[bold]Name:[/bold]      {manifest.product_name}",
        f"[bold]Version:[/bold]   {manifest.version}",
        f"[bold]Deployed:[/bold]  {manifest.deployed_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"[bold]Status:[/bold]    [{'green' if not manifest.failed else 'red'}]{manifest.status}[/]",
        f"[bold]Bucket:[/bold]    s3://{manifest.minio_bucket}",
        f"[bold]Namespace:[/bold] {manifest.iceberg_namespace}",
    ]
    if manifest.dagster_job_path:
        lines.append(f"[bold]Dagster job:[/bold] {manifest.dagster_job_path}")
    log.console.print(Panel("\n".join(lines), title="Overview", border_style="cyan"))

    # Tables table
    if manifest.tables:
        t = Table(title="Provisioned Tables", show_lines=True)
        t.add_column("Table")
        t.add_column("Tier")
        t.add_column("Iceberg Location")
        t.add_column("OM Registered")
        t.add_column("GE Suite")
        t.add_column("dbt Stub")

        tier_styles = {"bronze": "bronze", "silver": "silver", "gold": "gold"}
        for table in manifest.tables:
            style = tier_styles.get(table.tier.value, "")
            t.add_row(
                table.name,
                f"[{style}]{table.tier.value.upper()}[/{style}]",
                table.iceberg_location,
                "[green]✓[/green]" if table.openmetadata_fqn else "[dim]—[/dim]",
                "[green]✓[/green]" if table.ge_suite_path else "[dim]—[/dim]",
                "[green]✓[/green]" if table.dbt_model_path else "[dim]—[/dim]",
            )
        log.console.print(t)

    if manifest.errors:
        log.console.print("\n[bold red]Errors:[/bold red]")
        for e in manifest.errors:
            log.console.print(f"  • {e}")
