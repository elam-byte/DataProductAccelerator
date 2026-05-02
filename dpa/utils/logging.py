from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table
from rich.theme import Theme

_theme = Theme(
    {
        "info": "bold cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "dim": "dim white",
        "bronze": "bold #cd7f32",
        "silver": "bold #c0c0c0",
        "gold": "bold #ffd700",
    }
)

console = Console(theme=_theme)


def info(msg: str) -> None:
    console.print(f"[info]ℹ[/info]  {msg}")


def success(msg: str) -> None:
    console.print(f"[success]✓[/success]  {msg}")


def warning(msg: str) -> None:
    console.print(f"[warning]⚠[/warning]  {msg}")


def error(msg: str) -> None:
    console.print(f"[error]✗[/error]  {msg}")


def section(title: str) -> None:
    console.rule(f"[bold]{title}[/bold]")


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=False,
    )


def product_summary_table(config: object) -> Table:
    """Build a Rich table summarising a DataProductConfig for dpa validate output."""
    from dpa.models import DataProductConfig

    assert isinstance(config, DataProductConfig)

    table = Table(title=f"Data Product: [bold]{config.name}[/bold] v{config.version}", show_lines=True)
    table.add_column("Table", style="bold")
    table.add_column("Tier")
    table.add_column("Columns", justify="right")
    table.add_column("PII Fields")
    table.add_column("Quality Rules", justify="right")
    table.add_column("Partitioned By")

    tier_styles = {"bronze": "bronze", "silver": "silver", "gold": "gold"}

    for t in config.tables:
        pii_cols = ", ".join(c.name for c in t.schema_ if c.pii) or "—"
        partition = ", ".join(
            f"{p.column}({p.transform.value})" for p in t.partition_by
        ) or "—"
        style = tier_styles.get(t.tier.value, "")
        table.add_row(
            t.name,
            f"[{style}]{t.tier.value.upper()}[/{style}]",
            str(len(t.schema_)),
            pii_cols,
            str(len(t.quality_rules)),
            partition,
        )

    return table


def manifest_panel(manifest: object) -> Panel:
    """Build a Rich panel summarising a DeploymentManifest for dpa deploy output."""
    from dpa.models import DeploymentManifest

    assert isinstance(manifest, DeploymentManifest)

    lines = [
        f"[bold]Product:[/bold]  {manifest.product_name} v{manifest.version}",
        f"[bold]Bucket:[/bold]   {manifest.minio_bucket}",
        f"[bold]Namespace:[/bold] {manifest.iceberg_namespace}",
        f"[bold]Tables:[/bold]   {len(manifest.tables)} provisioned",
        f"[bold]Status:[/bold]   [{'success' if not manifest.failed else 'error'}]{manifest.status}[/]",
    ]
    if manifest.errors:
        lines.append("[error]Errors:[/error]")
        for e in manifest.errors:
            lines.append(f"  • {e}")

    color = "green" if not manifest.failed else "red"
    return Panel("\n".join(lines), title="[bold]Deployment Summary[/bold]", border_style=color)
