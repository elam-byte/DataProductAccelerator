"""dbt model stub generator.

Generates three files per table (rendered from Jinja2 templates):
  - models/generated/<product>/<tier>_<table>.sql   — transformation stub
  - models/generated/<product>/sources.yml           — Iceberg source definition
  - models/generated/<product>/schema.yml            — column docs + dbt tests
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader

from dpa.config.settings import get_settings
from dpa.models import DataProductConfig
from dpa.utils.errors import ProvisionerError

from .base import Provisioner, ProvisionResult

_NAME = "dbt"

_DBT_TYPE_MAP = {
    "string": "string",
    "integer": "int",
    "long": "bigint",
    "double": "double",
    "float": "float",
    "boolean": "boolean",
    "timestamp": "timestamp",
    "date": "date",
    "decimal": "decimal",
    "binary": "binary",
    "array": "array<string>",
    "map": "map<string,string>",
    "struct": "struct<>",
}

_QUALITY_TO_DBT_TEST = {
    "not_null": "not_null",
    "unique": "unique",
    "accepted_values": "accepted_values",
}


class DbtProvisioner(Provisioner):
    name = _NAME

    def __init__(self, dbt_root: str | None = None) -> None:
        self._dbt_root = Path(dbt_root or get_settings().dbt_project_root)
        self._jinja = Environment(
            loader=PackageLoader("dpa", "templates"),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def provision(self, config: DataProductConfig) -> ProvisionResult:
        out_dir = self._dbt_root / "models" / "generated" / config.name
        out_dir.mkdir(parents=True, exist_ok=True)

        resource_ids: list[str] = []
        try:
            # One SQL stub per table
            for table in config.tables:
                sql_path = out_dir / f"{table.tier.value}_{table.name}.sql"
                self._render(
                    "dbt_model.sql.j2",
                    sql_path,
                    config=config,
                    table=table,
                    dbt_type_map=_DBT_TYPE_MAP,
                )
                resource_ids.append(str(sql_path))

            # Single sources.yml for the whole product
            sources_path = out_dir / "sources.yml"
            self._render("dbt_source.yml.j2", sources_path, config=config)

            # Single schema.yml with column docs + dbt tests
            schema_path = out_dir / "schema.yml"
            self._render(
                "dbt_schema.yml.j2",
                schema_path,
                config=config,
                quality_to_dbt=_QUALITY_TO_DBT_TEST,
            )

        except Exception as e:
            raise ProvisionerError(_NAME, f"Template rendering failed: {e}") from e

        return ProvisionResult.ok(_NAME, resource_ids, f"{len(resource_ids)} dbt model stubs written")

    def teardown(self, config: DataProductConfig) -> ProvisionResult:
        out_dir = self._dbt_root / "models" / "generated" / config.name
        if out_dir.exists():
            import shutil
            shutil.rmtree(out_dir)
        return ProvisionResult.ok(_NAME, [str(out_dir)], "dbt stubs removed")

    def _render(self, template_name: str, output_path: Path, **ctx: object) -> None:
        tmpl = self._jinja.get_template(template_name)
        output_path.write_text(tmpl.render(**ctx))
