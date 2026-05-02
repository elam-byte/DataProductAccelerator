import json
from typing import Annotated

import typer
from rich.table import Table

from dpa.catalog import store
from dpa.utils import logging as log

app = typer.Typer(help="List and inspect deployed data products.")


@app.command("list")
def catalog_list(
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: table or json"),
    ] = "table",
) -> None:
    """List all deployed data products."""
    products = store.list_products()

    if not products:
        log.info("No data products deployed yet. Run [bold]dpa deploy <config.yml>[/bold] to get started.")
        return

    if format == "json":
        data = [
            {
                "name": p.product_name,
                "version": p.version,
                "deployed_at": p.deployed_at.isoformat(),
                "status": p.status,
                "bucket": p.minio_bucket,
                "namespace": p.iceberg_namespace,
            }
            for p in products
        ]
        log.console.print_json(json.dumps(data))
        return

    t = Table(title="Deployed Data Products", show_lines=False)
    t.add_column("Product", style="bold")
    t.add_column("Version")
    t.add_column("Deployed At")
    t.add_column("Tables", justify="right")
    t.add_column("Status")

    for p in products:
        tables = json.loads(p.tables_json) if isinstance(p.tables_json, str) else p.tables_json
        n_tables = len(tables) if tables else 0
        status_style = "green" if p.status == "success" else "yellow" if p.status == "partial" else "red"
        t.add_row(
            p.product_name,
            p.version,
            p.deployed_at.strftime("%Y-%m-%d %H:%M"),
            str(n_tables),
            f"[{status_style}]{p.status}[/{status_style}]",
        )
    log.console.print(t)


@app.command("show")
def catalog_show(
    product_name: Annotated[str, typer.Argument(help="Name of the data product")],
) -> None:
    """Show full deployment details for a data product."""
    from dpa.commands.status import status as _status

    _status(product_name)
