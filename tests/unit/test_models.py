import pytest
from pydantic import ValidationError

from dpa.models import DataProductConfig, QualityRule
from dpa.models.enums import ColumnType, DataTier, QualityRuleType


class TestDataProductConfig:
    def test_valid_minimal_config(self, minimal_config_dict):
        config = DataProductConfig.model_validate(minimal_config_dict)
        assert config.name == "test_product"
        assert config.version == "1.0.0"
        assert len(config.tables) == 1

    def test_bucket_name_uses_hyphens(self, minimal_config_dict):
        minimal_config_dict["name"] = "my_product"
        config = DataProductConfig.model_validate(minimal_config_dict)
        assert config.bucket_name == "dpa-my-product"

    def test_namespace_uses_underscores(self, minimal_config_dict):
        config = DataProductConfig.model_validate(minimal_config_dict)
        assert config.namespace == "test_product"

    def test_name_must_be_lowercase(self, minimal_config_dict):
        minimal_config_dict["name"] = "MyProduct"
        with pytest.raises(ValidationError):
            DataProductConfig.model_validate(minimal_config_dict)

    def test_name_cannot_start_with_digit(self, minimal_config_dict):
        minimal_config_dict["name"] = "1product"
        with pytest.raises(ValidationError):
            DataProductConfig.model_validate(minimal_config_dict)

    def test_version_must_be_semver(self, minimal_config_dict):
        minimal_config_dict["version"] = "1.0"
        with pytest.raises(ValidationError):
            DataProductConfig.model_validate(minimal_config_dict)

    def test_duplicate_table_names_rejected(self, minimal_config_dict):
        table = minimal_config_dict["tables"][0].copy()
        minimal_config_dict["tables"].append(table)
        with pytest.raises(ValidationError, match="Duplicate table names"):
            DataProductConfig.model_validate(minimal_config_dict)

    def test_tables_by_tier(self, customer_360_config):
        by_tier = customer_360_config.tables_by_tier
        assert DataTier.BRONZE in by_tier
        assert DataTier.SILVER in by_tier
        assert DataTier.GOLD in by_tier

    def test_pii_columns_property(self, customer_360_config):
        # customer_summary gold table has email as PII
        gold_tables = customer_360_config.tables_by_tier[DataTier.GOLD]
        summary = gold_tables[0]
        pii = summary.pii_columns
        assert any(c.name == "email" for c in pii)


class TestQualityRule:
    def test_shorthand_not_null(self):
        rule = QualityRule.model_validate({"not_null": ["col1", "col2"]})
        assert rule.rule_type == QualityRuleType.NOT_NULL
        assert rule.columns == ["col1", "col2"]

    def test_shorthand_unique(self):
        rule = QualityRule.model_validate({"unique": ["id"]})
        assert rule.rule_type == QualityRuleType.UNIQUE
        assert rule.columns == ["id"]

    def test_structured_form(self):
        rule = QualityRule.model_validate({
            "rule_type": "not_null",
            "columns": ["id"],
        })
        assert rule.rule_type == QualityRuleType.NOT_NULL

    def test_unknown_rule_type_rejected(self):
        with pytest.raises(Exception):
            QualityRule.model_validate({"nonexistent_rule": ["col"]})


class TestColumnModel:
    def test_decimal_requires_precision_and_scale(self, minimal_config_dict):
        minimal_config_dict["tables"][0]["schema"].append({
            "name": "amount",
            "type": "decimal",
        })
        with pytest.raises(ValidationError, match="decimal_precision"):
            DataProductConfig.model_validate(minimal_config_dict)

    def test_decimal_with_precision_and_scale_valid(self, minimal_config_dict):
        minimal_config_dict["tables"][0]["schema"].append({
            "name": "amount",
            "type": "decimal",
            "decimal_precision": 18,
            "decimal_scale": 4,
        })
        config = DataProductConfig.model_validate(minimal_config_dict)
        amount_col = next(c for c in config.tables[0].schema_ if c.name == "amount")
        assert amount_col.decimal_precision == 18

    def test_column_name_must_be_valid_identifier(self, minimal_config_dict):
        minimal_config_dict["tables"][0]["schema"].append({
            "name": "bad-name",
            "type": "string",
        })
        with pytest.raises(ValidationError):
            DataProductConfig.model_validate(minimal_config_dict)

    def test_duplicate_column_names_rejected(self, minimal_config_dict):
        minimal_config_dict["tables"][0]["schema"].append({
            "name": "id",
            "type": "string",
        })
        with pytest.raises(ValidationError, match="Duplicate column names"):
            DataProductConfig.model_validate(minimal_config_dict)


class TestExampleConfigs:
    def test_customer_360_loads(self, customer_360_config):
        assert customer_360_config.name == "customer_360"
        assert len(customer_360_config.tables) == 3

    def test_order_events_loads(self, order_events_config):
        assert order_events_config.name == "order_events"
        assert len(order_events_config.tables) == 2

    def test_customer_360_has_pii_fields(self, customer_360_config):
        all_pii = [
            c.name
            for t in customer_360_config.tables
            for c in t.schema_
            if c.pii
        ]
        assert "email" in all_pii
