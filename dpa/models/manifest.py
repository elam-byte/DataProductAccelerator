from datetime import datetime

from pydantic import BaseModel, Field

from .enums import DataTier


class ProvisionedTable(BaseModel):
    name: str
    tier: DataTier
    iceberg_location: str
    iceberg_fqn: str
    ge_suite_path: str | None = None
    dbt_model_path: str | None = None
    openmetadata_fqn: str | None = None
    dagster_asset_key: str | None = None


class DeploymentManifest(BaseModel):
    product_name: str
    version: str
    deployed_at: datetime = Field(default_factory=datetime.utcnow)
    minio_bucket: str
    iceberg_namespace: str
    tables: list[ProvisionedTable] = Field(default_factory=list)
    dagster_job_path: str | None = None
    status: str = "success"
    errors: list[str] = Field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.status != "success" or bool(self.errors)
