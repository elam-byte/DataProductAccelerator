"""Iceberg provisioner using PyIceberg REST catalog.

Creates an Iceberg namespace (mapped to the data product name) and one table
per TableModel entry in the config. PyIceberg handles DDL directly against the
REST catalog without requiring a running Spark cluster.
"""
from __future__ import annotations

import pyarrow as pa
from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError, NoSuchNamespaceError, TableAlreadyExistsError
from pyiceberg.schema import Schema
from pyiceberg.types import (
    BinaryType,
    BooleanType,
    DateType,
    DecimalType,
    DoubleType,
    FloatType,
    IntegerType,
    ListType,
    LongType,
    MapType,
    NestedField,
    StringType,
    TimestampType,
)

from dpa.config.settings import get_settings
from dpa.models import ColumnModel, ColumnType, DataProductConfig, TableModel
from dpa.models.enums import PartitionTransform
from dpa.utils.errors import ProvisionerError

from .base import Provisioner, ProvisionResult

_NAME = "iceberg"


def _column_type_to_iceberg(col: ColumnModel) -> object:
    mapping = {
        ColumnType.STRING: StringType(),
        ColumnType.INTEGER: IntegerType(),
        ColumnType.LONG: LongType(),
        ColumnType.DOUBLE: DoubleType(),
        ColumnType.FLOAT: FloatType(),
        ColumnType.BOOLEAN: BooleanType(),
        ColumnType.TIMESTAMP: TimestampType(),
        ColumnType.DATE: DateType(),
        ColumnType.BINARY: BinaryType(),
    }
    if col.type == ColumnType.DECIMAL:
        return DecimalType(col.decimal_precision or 18, col.decimal_scale or 4)
    result = mapping.get(col.type)
    if result is None:
        # ARRAY, MAP, STRUCT — use StringType as a placeholder for generated stubs
        return StringType()
    return result


def _build_iceberg_schema(columns: list[ColumnModel]) -> Schema:
    fields = []
    for idx, col in enumerate(columns, start=1):
        iceberg_type = _column_type_to_iceberg(col)
        field = NestedField(
            field_id=idx,
            name=col.name,
            field_type=iceberg_type,
            required=not col.nullable,
            doc=col.description,
        )
        fields.append(field)
    return Schema(*fields)


class IcebergProvisioner(Provisioner):
    name = _NAME

    def __init__(self) -> None:
        settings = get_settings()
        self._catalog = load_catalog(
            "rest",
            **{
                "type": "rest",
                "uri": settings.iceberg_catalog_uri,
                "s3.endpoint": settings.minio_endpoint,
                "s3.access-key-id": settings.minio_access_key,
                "s3.secret-access-key": settings.minio_secret_key,
                "s3.path-style-access": "true",
            },
        )
        self._settings = settings

    def provision(self, config: DataProductConfig) -> ProvisionResult:
        namespace = config.namespace
        try:
            self._ensure_namespace(namespace, config)
        except Exception as e:
            raise ProvisionerError(_NAME, f"Failed to create namespace '{namespace}': {e}") from e

        resource_ids: list[str] = []
        for table in config.tables:
            try:
                fqn = self._create_table(namespace, table, config)
                resource_ids.append(fqn)
            except Exception as e:
                raise ProvisionerError(_NAME, f"Failed to create table '{table.name}': {e}") from e

        return ProvisionResult.ok(_NAME, resource_ids, f"{len(resource_ids)} Iceberg tables created")

    def teardown(self, config: DataProductConfig) -> ProvisionResult:
        namespace = config.namespace
        dropped: list[str] = []

        for table in config.tables:
            identifier = (namespace, table.name)
            try:
                self._catalog.drop_table(identifier)
                dropped.append(f"{namespace}.{table.name}")
            except Exception:
                pass

        try:
            self._catalog.drop_namespace(namespace)
        except (NoSuchNamespaceError, Exception):
            pass

        return ProvisionResult.ok(_NAME, dropped, f"{len(dropped)} tables dropped")

    # ── internal helpers ──────────────────────────────────────────────────────

    def _ensure_namespace(self, namespace: str, config: DataProductConfig) -> None:
        properties = {
            "owner": config.owner.team,
            "owner_email": config.owner.email,
            "product_version": config.version,
        }
        try:
            self._catalog.create_namespace(namespace, properties=properties)
        except NamespaceAlreadyExistsError:
            pass

    def _create_table(
        self, namespace: str, table: TableModel, config: DataProductConfig
    ) -> str:
        identifier = (namespace, table.name)
        schema = _build_iceberg_schema(table.schema_)

        location = (
            f"{self._settings.iceberg_warehouse.rstrip('/')}"
            f"/{config.bucket_name}/{table.tier.value}/{table.name}"
        )

        properties: dict[str, str] = {
            "owner": config.owner.team,
            "tier": table.tier.value,
            "product": config.name,
            "product_version": config.version,
            "write.format.default": "parquet",
            "write.parquet.compression-codec": "snappy",
        }
        if table.description:
            properties["comment"] = table.description

        try:
            self._catalog.create_table(
                identifier=identifier,
                schema=schema,
                location=location,
                properties=properties,
            )
        except TableAlreadyExistsError:
            pass

        return f"{namespace}.{table.name}"
