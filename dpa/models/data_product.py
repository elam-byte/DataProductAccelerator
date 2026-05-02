from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from .enums import ColumnType, DataTier, PartitionTransform, QualityRuleType


class OwnerModel(BaseModel):
    team: str
    email: EmailStr
    slack_channel: str | None = None


class SLAModel(BaseModel):
    freshness_hours: int = Field(gt=0, le=8760)
    availability_pct: float = Field(default=99.9, ge=0.0, le=100.0)
    max_row_count: int | None = None
    min_row_count: int | None = None


class QualityRule(BaseModel):
    rule_type: QualityRuleType
    columns: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def parse_shorthand(cls, data: Any) -> Any:
        """Parses YAML shorthand forms into structured QualityRule.

        Supports two shorthand styles:
          {not_null: [col1, col2]}                         — simple column list
          {accepted_values: {columns: [...], params: {}}}  — columns + params dict
        """
        if isinstance(data, dict) and len(data) == 1:
            key, value = next(iter(data.items()))
            try:
                QualityRuleType(key)
                if isinstance(value, list):
                    return {"rule_type": key, "columns": value}
                if isinstance(value, dict):
                    columns = value.get("columns", [])
                    params = value.get("params", {})
                    return {"rule_type": key, "columns": columns, "params": params}
                return {"rule_type": key, "columns": [value]}
            except ValueError:
                pass
        return data


class PartitionSpec(BaseModel):
    column: str
    transform: PartitionTransform = PartitionTransform.IDENTITY
    num_buckets: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_bucket_params(self) -> PartitionSpec:
        if self.transform == PartitionTransform.BUCKET and self.num_buckets is None:
            raise ValueError("num_buckets is required when transform is 'bucket'")
        return self


class ColumnModel(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    type: ColumnType
    nullable: bool = True
    pii: bool = False
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    decimal_precision: int | None = None
    decimal_scale: int | None = None

    @model_validator(mode="after")
    def validate_decimal_params(self) -> ColumnModel:
        if self.type == ColumnType.DECIMAL:
            if self.decimal_precision is None or self.decimal_scale is None:
                raise ValueError(
                    "decimal_precision and decimal_scale are required for DECIMAL type"
                )
        return self


class TableModel(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    tier: DataTier
    description: str | None = None
    schema_: list[ColumnModel] = Field(alias="schema", min_length=1)
    partition_by: list[PartitionSpec] = Field(default_factory=list)
    quality_rules: list[QualityRule] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @field_validator("schema_")
    @classmethod
    def no_duplicate_column_names(cls, columns: list[ColumnModel]) -> list[ColumnModel]:
        names = [c.name for c in columns]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate column names in schema")
        return columns

    @property
    def pii_columns(self) -> list[ColumnModel]:
        return [c for c in self.schema_ if c.pii]


class DataProductConfig(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    owner: OwnerModel
    sla: SLAModel
    description: str | None = None
    tables: list[TableModel] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("tables")
    @classmethod
    def no_duplicate_table_names(cls, tables: list[TableModel]) -> list[TableModel]:
        names = [t.name for t in tables]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate table names in product config")
        return tables

    @property
    def bucket_name(self) -> str:
        return f"dpa-{self.name.replace('_', '-')}"

    @property
    def namespace(self) -> str:
        return self.name.replace("-", "_")

    @property
    def tables_by_tier(self) -> dict[DataTier, list[TableModel]]:
        result: dict[DataTier, list[TableModel]] = {}
        for table in self.tables:
            result.setdefault(table.tier, []).append(table)
        return result
