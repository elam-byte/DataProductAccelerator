from datetime import datetime
from typing import Optional

from sqlmodel import JSON, Column, Field, SQLModel


class DeployedProduct(SQLModel, table=True):
    __tablename__ = "deployed_products"

    id: Optional[int] = Field(default=None, primary_key=True)
    product_name: str = Field(index=True, unique=True)
    version: str
    deployed_at: datetime
    minio_bucket: str
    iceberg_namespace: str
    tables_json: str = Field(sa_column=Column(JSON))
    dagster_job_path: Optional[str] = None
    status: str = "success"
    errors_json: str = Field(default="[]", sa_column=Column(JSON))
