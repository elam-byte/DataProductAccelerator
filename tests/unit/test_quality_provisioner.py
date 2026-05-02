"""Tests for the GE suite JSON generator — no services required."""
import json
from pathlib import Path

import pytest

from dpa.models import DataProductConfig
from dpa.models.enums import QualityRuleType


class TestQualityProvisioner:
    """Validates that QualityProvisioner generates correct GE expectation JSON."""

    def test_not_null_rule_maps_to_ge_expectation(self, minimal_config_dict, tmp_path):
        minimal_config_dict["tables"][0]["quality_rules"] = [
            {"not_null": ["id"]}
        ]
        config = DataProductConfig.model_validate(minimal_config_dict)

        from dpa.provisioners.quality import QualityProvisioner

        p = QualityProvisioner(ge_root=str(tmp_path))
        result = p.provision(config)

        assert result.success
        suite_path = Path(result.resource_ids[0])
        suite = json.loads(suite_path.read_text())
        expectation_types = [e["expectation_type"] for e in suite["expectations"]]
        assert "expect_column_values_to_not_be_null" in expectation_types

    def test_unique_rule_maps_to_ge_expectation(self, minimal_config_dict, tmp_path):
        minimal_config_dict["tables"][0]["quality_rules"] = [
            {"unique": ["id"]}
        ]
        config = DataProductConfig.model_validate(minimal_config_dict)

        from dpa.provisioners.quality import QualityProvisioner

        p = QualityProvisioner(ge_root=str(tmp_path))
        result = p.provision(config)

        suite = json.loads(Path(result.resource_ids[0]).read_text())
        types = [e["expectation_type"] for e in suite["expectations"]]
        assert "expect_column_values_to_be_unique" in types

    def test_email_format_rule_uses_regex(self, minimal_config_dict, tmp_path):
        minimal_config_dict["tables"][0]["quality_rules"] = [
            {"email_format": ["email_col"]}
        ]
        config = DataProductConfig.model_validate(minimal_config_dict)

        from dpa.provisioners.quality import QualityProvisioner

        p = QualityProvisioner(ge_root=str(tmp_path))
        result = p.provision(config)

        suite = json.loads(Path(result.resource_ids[0]).read_text())
        types = [e["expectation_type"] for e in suite["expectations"]]
        assert "expect_column_values_to_match_regex" in types

    def test_suite_file_is_valid_json(self, customer_360_config, tmp_path):
        from dpa.provisioners.quality import QualityProvisioner

        p = QualityProvisioner(ge_root=str(tmp_path))
        result = p.provision(customer_360_config)

        for suite_path in result.resource_ids:
            content = Path(suite_path).read_text()
            parsed = json.loads(content)
            assert "expectations" in parsed
            assert "expectation_suite_name" in parsed
