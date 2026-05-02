import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from dpa.config import load_product_config
from dpa.config.settings import get_settings
from dpa.utils import logging as log
from dpa.utils.errors import ConfigValidationError

app = typer.Typer(help="Validate a data product config and optionally run quality checks.")


@app.callback(invoke_without_command=True)
def validate(
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
    run_quality: Annotated[
        bool,
        typer.Option("--run-quality", help="Execute the Great Expectations checkpoint against live data"),
    ] = False,
) -> None:
    """Validate a data product YAML config without deploying anything."""
    log.section("Validating Data Product Config")

    try:
        config = load_product_config(config_path)
    except ConfigValidationError as e:
        log.error(str(e))
        raise typer.Exit(code=1) from None

    log.success(f"Config is valid: [bold]{config.name}[/bold] v{config.version}")
    log.console.print()
    log.console.print(log.product_summary_table(config))
    log.console.print()

    _print_owner_sla(config)

    if run_quality:
        _run_quality_checks(config.name)


def _print_owner_sla(config: object) -> None:
    from dpa.models import DataProductConfig

    assert isinstance(config, DataProductConfig)
    from rich.table import Table

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column("Key", style="bold dim")
    t.add_column("Value")
    t.add_row("Owner", f"{config.owner.team} <{config.owner.email}>")
    t.add_row("SLA freshness", f"{config.sla.freshness_hours}h")
    t.add_row("SLA availability", f"{config.sla.availability_pct}%")
    if config.description:
        t.add_row("Description", config.description)
    t.add_row("Bucket (planned)", config.bucket_name)
    t.add_row("Namespace (planned)", config.namespace)
    log.console.print(t)


def _run_quality_checks(product_name: str) -> None:
    settings = get_settings()
    log.section("Running Quality Checks")

    checkpoint_name = f"{product_name}_checkpoint"
    result = subprocess.run(
        ["great_expectations", "checkpoint", "run", checkpoint_name],
        cwd=settings.ge_project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        log.success("All quality checks passed")
    else:
        log.error("Quality checks failed")
        log.console.print(result.stdout)
        log.console.print(result.stderr)
        sys.exit(1)
