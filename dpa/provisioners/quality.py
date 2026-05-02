"""Great Expectations suite generator.

Writes expectation suite JSON directly (not via the GE Python API) for
version stability. GE's fluent API changes significantly across minor versions;
JSON output is stable and readable.
"""
from __future__ import annotations

import json
from pathlib import Path

from dpa.config.settings import get_settings
from dpa.models import DataProductConfig, TableModel
from dpa.models.enums import QualityRuleType
from dpa.utils.errors import ProvisionerError

from .base import Provisioner, ProvisionResult

_NAME = "quality"

# Maps QualityRuleType → GE expectation type
_EXPECTATION_MAP = {
    QualityRuleType.NOT_NULL: "expect_column_values_to_not_be_null",
    QualityRuleType.UNIQUE: "expect_column_values_to_be_unique",
    QualityRuleType.EMAIL_FORMAT: "expect_column_values_to_match_regex",
    QualityRuleType.REGEX: "expect_column_values_to_match_regex",
    QualityRuleType.ACCEPTED_VALUES: "expect_column_values_to_be_in_set",
    QualityRuleType.MIN_VALUE: "expect_column_values_to_be_between",
    QualityRuleType.MAX_VALUE: "expect_column_values_to_be_between",
}

_EMAIL_REGEX = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"


def _rule_to_expectations(rule: object) -> list[dict]:
    from dpa.models import QualityRule

    assert isinstance(rule, QualityRule)

    expectation_type = _EXPECTATION_MAP.get(rule.rule_type)
    if not expectation_type:
        return []

    expectations = []
    for col in rule.columns:
        kwargs: dict = {"column": col}

        if rule.rule_type == QualityRuleType.EMAIL_FORMAT:
            kwargs["regex"] = _EMAIL_REGEX
        elif rule.rule_type == QualityRuleType.REGEX:
            kwargs["regex"] = rule.params.get("pattern", ".*")
        elif rule.rule_type == QualityRuleType.ACCEPTED_VALUES:
            kwargs["value_set"] = rule.params.get("values", [])
        elif rule.rule_type == QualityRuleType.MIN_VALUE:
            kwargs["min_value"] = rule.params.get("min")
        elif rule.rule_type == QualityRuleType.MAX_VALUE:
            kwargs["max_value"] = rule.params.get("max")

        expectations.append({
            "expectation_type": expectation_type,
            "kwargs": kwargs,
            "meta": {"rule_source": "dpa", "rule_type": rule.rule_type.value},
        })

    return expectations


class QualityProvisioner(Provisioner):
    name = _NAME

    def __init__(self, ge_root: str | None = None) -> None:
        self._ge_root = Path(ge_root or get_settings().ge_project_root)

    def provision(self, config: DataProductConfig) -> ProvisionResult:
        expectations_dir = self._ge_root / "expectations"
        expectations_dir.mkdir(parents=True, exist_ok=True)

        resource_ids: list[str] = []
        for table in config.tables:
            try:
                path = self._write_suite(config.name, table, expectations_dir)
                resource_ids.append(str(path))
            except Exception as e:
                raise ProvisionerError(_NAME, f"Failed to generate suite for '{table.name}': {e}") from e

        return ProvisionResult.ok(
            _NAME,
            resource_ids,
            f"{len(resource_ids)} expectation suites generated",
        )

    def teardown(self, config: DataProductConfig) -> ProvisionResult:
        expectations_dir = self._ge_root / "expectations"
        removed: list[str] = []
        for table in config.tables:
            path = expectations_dir / f"{config.name}__{table.name}.json"
            if path.exists():
                path.unlink()
                removed.append(str(path))
        return ProvisionResult.ok(_NAME, removed, f"{len(removed)} suites removed")

    def _write_suite(self, product_name: str, table: TableModel, outdir: Path) -> Path:
        suite_name = f"{product_name}__{table.name}"
        expectations: list[dict] = []

        for rule in table.quality_rules:
            expectations.extend(_rule_to_expectations(rule))

        suite = {
            "expectation_suite_name": suite_name,
            "data_asset_type": None,
            "expectations": expectations,
            "meta": {
                "great_expectations_version": "0.18.x",
                "product": product_name,
                "table": table.name,
                "tier": table.tier.value,
                "generated_by": "dpa",
            },
        }

        path = outdir / f"{suite_name}.json"
        path.write_text(json.dumps(suite, indent=2))
        return path
