import typer

from dpa.commands import catalog, deploy, status, teardown, validate

app = typer.Typer(
    name="dpa",
    help="Data Product Accelerator — self-service CLI for governed data products on an OSS lakehouse.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

app.add_typer(deploy.app, name="deploy")
app.add_typer(validate.app, name="validate")
app.add_typer(status.app, name="status")
app.add_typer(teardown.app, name="teardown")
app.add_typer(catalog.app, name="catalog")


@app.callback()
def main(version: bool = typer.Option(False, "--version", "-v", help="Show version and exit")) -> None:
    if version:
        from dpa import __version__
        typer.echo(f"dpa {__version__}")
        raise typer.Exit()
