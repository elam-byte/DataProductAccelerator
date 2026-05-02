"""Dagster asset file generator.

Renders a Python file per data product containing @asset definitions for each
table. The rendered file is validated with ast.parse() before writing to prevent
a syntax error from crashing the entire Dagster repository load.
"""
from __future__ import annotations

import ast
from pathlib import Path

from jinja2 import Environment, PackageLoader

from dpa.config.settings import get_settings
from dpa.models import DataProductConfig
from dpa.utils.errors import ProvisionerError

from .base import Provisioner, ProvisionResult

_NAME = "orchestration"


class OrchestrationProvisioner(Provisioner):
    name = _NAME

    def __init__(self, dagster_home: str | None = None) -> None:
        self._dagster_home = Path(dagster_home or get_settings().dagster_home)
        self._jinja = Environment(
            loader=PackageLoader("dpa", "templates"),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def provision(self, config: DataProductConfig) -> ProvisionResult:
        out_dir = self._dagster_home / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)

        job_path = out_dir / f"{config.name}_assets.py"

        try:
            tmpl = self._jinja.get_template("dagster_asset.py.j2")
            rendered = tmpl.render(config=config)
        except Exception as e:
            raise ProvisionerError(_NAME, f"Template rendering failed: {e}") from e

        # Validate generated Python before writing — a syntax error here would
        # crash the Dagster repository loader for ALL products, not just this one.
        try:
            ast.parse(rendered)
        except SyntaxError as e:
            raise ProvisionerError(_NAME, f"Generated Python has syntax error: {e}") from e

        job_path.write_text(rendered)

        asset_keys = [f"{config.name}/{t.name}" for t in config.tables]
        return ProvisionResult.ok(
            _NAME,
            asset_keys,
            str(job_path),
        )

    def teardown(self, config: DataProductConfig) -> ProvisionResult:
        job_path = self._dagster_home / "generated" / f"{config.name}_assets.py"
        if job_path.exists():
            job_path.unlink()
        return ProvisionResult.ok(_NAME, [str(job_path)], "Dagster assets removed")
