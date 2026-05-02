"""OpenMetadata governance provisioner.

Uses the OpenMetadata REST API directly via httpx (not metadata-ingestion SDK,
which requires exact version pinning and installs 80+ transitive dependencies).

Creates:
  - A Custom DatabaseService representing the MinIO/Iceberg lakehouse
  - A Database entity for the data product namespace
  - A Table entity per TableModel, with column descriptions and PII tags
  - Ownership assignment from config.owner
"""
from __future__ import annotations

import httpx

from dpa.config.settings import get_settings
from dpa.models import DataProductConfig, TableModel
from dpa.utils.errors import ProvisionerError, ServiceUnavailableError
from dpa.utils.retry import http_retry

from .base import Provisioner, ProvisionResult

_NAME = "metadata"
_OM_DATABASE_SERVICE = "dpa-lakehouse"


class OpenMetadataClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(headers=headers, timeout=30.0)

    @http_retry()
    def get(self, path: str) -> httpx.Response:
        return self._client.get(f"{self._base}/api/v1{path}")

    @http_retry()
    def post(self, path: str, json: dict) -> httpx.Response:
        return self._client.post(f"{self._base}/api/v1{path}", json=json)

    @http_retry()
    def put(self, path: str, json: dict) -> httpx.Response:
        return self._client.put(f"{self._base}/api/v1{path}", json=json)

    def is_healthy(self) -> bool:
        try:
            r = self._client.get(f"{self._base}/api/v1/system/status", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    def get_or_create_service(self) -> str:
        """Create a Custom DatabaseService for the DPA lakehouse, return its id."""
        payload = {
            "name": _OM_DATABASE_SERVICE,
            "displayName": "DPA Iceberg Lakehouse",
            "description": "Apache Iceberg tables on MinIO — managed by the Data Product Accelerator.",
            "serviceType": "CustomDatabase",
            "connection": {"config": {"type": "CustomDatabase", "sourcePythonClass": "pyiceberg"}},
        }
        r = self.put("/services/databaseServices", json=payload)
        r.raise_for_status()
        return r.json()["id"]

    def get_or_create_database(self, service_id: str, product_name: str) -> str:
        """Create a Database entity for the product namespace, return its fqn."""
        payload = {
            "name": product_name,
            "displayName": product_name.replace("_", " ").title(),
            "service": service_id,
        }
        r = self.put("/databases", json=payload)
        r.raise_for_status()
        return r.json()["fullyQualifiedName"]

    def get_or_create_schema(self, database_fqn: str, tier: str) -> str:
        payload = {
            "name": tier,
            "database": database_fqn,
        }
        r = self.put("/databaseSchemas", json=payload)
        r.raise_for_status()
        return r.json()["fullyQualifiedName"]

    def create_table(
        self,
        schema_fqn: str,
        table: TableModel,
        product_name: str,
        owner_team: str,
    ) -> str:
        columns = []
        for col in table.schema_:
            c: dict = {
                "name": col.name,
                "dataType": col.type.value.upper(),
                "constraint": "NOT_NULL" if not col.nullable else "NONE",
            }
            if col.description:
                c["description"] = col.description
            if col.pii:
                c["tags"] = [{"tagFQN": "PII.Sensitive", "labelType": "Automated", "state": "Suggested"}]
            columns.append(c)

        payload = {
            "name": table.name,
            "displayName": table.name.replace("_", " ").title(),
            "description": table.description or f"{table.tier.value.title()} tier table for {product_name}",
            "tableType": "Regular",
            "databaseSchema": schema_fqn,
            "columns": columns,
        }
        r = self.put("/tables", json=payload)
        r.raise_for_status()
        fqn = r.json()["fullyQualifiedName"]

        # Assign owner
        self._add_owner(fqn, owner_team)
        return fqn

    def _add_owner(self, table_fqn: str, team_name: str) -> None:
        r = self.get(f"/teams/name/{team_name}")
        if r.status_code != 200:
            return
        team_id = r.json()["id"]
        patch = [{"op": "add", "path": "/owner", "value": {"id": team_id, "type": "team"}}]
        encoded = table_fqn.replace(".", "%2E")
        self._client.patch(
            f"{self._base}/api/v1/tables/{encoded}",
            json=patch,
            headers={"Content-Type": "application/json-patch+json"},
        )


class MetadataProvisioner(Provisioner):
    name = _NAME

    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenMetadataClient(settings.openmetadata_url, settings.openmetadata_token)
        self._settings = settings

    def provision(self, config: DataProductConfig) -> ProvisionResult:
        if not self._client.is_healthy():
            raise ServiceUnavailableError("OpenMetadata", self._settings.openmetadata_url)

        try:
            service_id = self._client.get_or_create_service()
            db_fqn = self._client.get_or_create_database(service_id, config.namespace)
        except Exception as e:
            raise ProvisionerError(_NAME, f"Failed to create database service/entity: {e}") from e

        resource_ids: list[str] = []
        for table in config.tables:
            try:
                schema_fqn = self._client.get_or_create_schema(db_fqn, table.tier.value)
                table_fqn = self._client.create_table(
                    schema_fqn, table, config.name, config.owner.team
                )
                resource_ids.append(table_fqn)
            except Exception as e:
                raise ProvisionerError(_NAME, f"Failed to register table '{table.name}': {e}") from e

        return ProvisionResult.ok(
            _NAME,
            resource_ids,
            f"{len(resource_ids)} tables registered in OpenMetadata",
        )

    def teardown(self, config: DataProductConfig) -> ProvisionResult:
        return ProvisionResult.skip(_NAME, "OpenMetadata entity removal not implemented — delete via UI")
