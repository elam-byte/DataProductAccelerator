"""SQLite-backed local catalog for tracking deployed data products."""
from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from dpa.config.settings import get_settings
from dpa.models import DeploymentManifest
from dpa.utils.errors import CatalogError

from .models import DeployedProduct


def _get_engine(db_path: str | None = None) -> object:
    path = db_path or get_settings().catalog_db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path}"
    engine = create_engine(url, echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def save_manifest(manifest: DeploymentManifest, db_path: str | None = None) -> None:
    engine = _get_engine(db_path)
    with Session(engine) as session:
        existing = session.exec(
            select(DeployedProduct).where(DeployedProduct.product_name == manifest.product_name)
        ).first()

        tables_json = json.dumps([t.model_dump(mode="json") for t in manifest.tables])
        errors_json = json.dumps(manifest.errors)

        if existing:
            existing.version = manifest.version
            existing.deployed_at = manifest.deployed_at
            existing.minio_bucket = manifest.minio_bucket
            existing.iceberg_namespace = manifest.iceberg_namespace
            existing.tables_json = tables_json
            existing.dagster_job_path = manifest.dagster_job_path
            existing.status = manifest.status
            existing.errors_json = errors_json
            session.add(existing)
        else:
            record = DeployedProduct(
                product_name=manifest.product_name,
                version=manifest.version,
                deployed_at=manifest.deployed_at,
                minio_bucket=manifest.minio_bucket,
                iceberg_namespace=manifest.iceberg_namespace,
                tables_json=tables_json,
                dagster_job_path=manifest.dagster_job_path,
                status=manifest.status,
                errors_json=errors_json,
            )
            session.add(record)
        session.commit()


def get_manifest(product_name: str, db_path: str | None = None) -> DeploymentManifest | None:
    engine = _get_engine(db_path)
    with Session(engine) as session:
        record = session.exec(
            select(DeployedProduct).where(DeployedProduct.product_name == product_name)
        ).first()
        if not record:
            return None
        return _record_to_manifest(record)


def list_products(db_path: str | None = None) -> list[DeployedProduct]:
    engine = _get_engine(db_path)
    with Session(engine) as session:
        return list(session.exec(select(DeployedProduct)).all())


def delete_product(product_name: str, db_path: str | None = None) -> bool:
    engine = _get_engine(db_path)
    with Session(engine) as session:
        record = session.exec(
            select(DeployedProduct).where(DeployedProduct.product_name == product_name)
        ).first()
        if not record:
            return False
        session.delete(record)
        session.commit()
        return True


def _record_to_manifest(record: DeployedProduct) -> DeploymentManifest:
    from dpa.models import ProvisionedTable

    tables = [ProvisionedTable.model_validate(t) for t in json.loads(record.tables_json)]
    return DeploymentManifest(
        product_name=record.product_name,
        version=record.version,
        deployed_at=record.deployed_at,
        minio_bucket=record.minio_bucket,
        iceberg_namespace=record.iceberg_namespace,
        tables=tables,
        dagster_job_path=record.dagster_job_path,
        status=record.status,
        errors=json.loads(record.errors_json),
    )
