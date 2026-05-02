"""MinIO / S3-compatible storage provisioner.

Creates one bucket per data product with bronze/silver/gold prefix markers
and a lifecycle configuration that reflects the SLA freshness policy.
"""
from __future__ import annotations

import json

import boto3
from botocore.exceptions import ClientError

from dpa.config.settings import get_settings
from dpa.models import DataProductConfig
from dpa.utils.errors import ProvisionerError

from .base import Provisioner, ProvisionResult

_NAME = "storage"
_TIERS = ("bronze", "silver", "gold")


class StorageProvisioner(Provisioner):
    name = _NAME

    def __init__(self) -> None:
        settings = get_settings()
        self._s3 = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
        )

    def provision(self, config: DataProductConfig) -> ProvisionResult:
        bucket = config.bucket_name
        try:
            self._create_bucket(bucket)
            self._put_tier_markers(bucket)
            self._put_lifecycle_policy(bucket, config.sla.freshness_hours)
        except ClientError as e:
            raise ProvisionerError(_NAME, str(e)) from e

        resource_ids = [f"s3://{bucket}/{tier}/" for tier in _TIERS]
        return ProvisionResult.ok(_NAME, resource_ids, f"bucket {bucket} ready")

    def teardown(self, config: DataProductConfig) -> ProvisionResult:
        bucket = config.bucket_name
        try:
            self._empty_bucket(bucket)
            self._s3.delete_bucket(Bucket=bucket)
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "NoSuchBucket":
                return ProvisionResult.skip(_NAME, f"bucket {bucket} does not exist")
            raise ProvisionerError(_NAME, str(e)) from e

        return ProvisionResult.ok(_NAME, [bucket], f"bucket {bucket} deleted")

    # ── internal helpers ──────────────────────────────────────────────────────

    def _create_bucket(self, bucket: str) -> None:
        try:
            self._s3.create_bucket(Bucket=bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                return
            raise

    def _put_tier_markers(self, bucket: str) -> None:
        for tier in _TIERS:
            self._s3.put_object(Bucket=bucket, Key=f"{tier}/.keep", Body=b"")

    def _put_lifecycle_policy(self, bucket: str, freshness_hours: int) -> None:
        policy = {
            "Rules": [
                {
                    "ID": "expire-bronze-raw",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "bronze/"},
                    "Expiration": {"Days": max(1, freshness_hours * 7 // 24)},
                }
            ]
        }
        self._s3.put_bucket_lifecycle_configuration(
            Bucket=bucket,
            LifecycleConfiguration=policy,
        )

    def _empty_bucket(self, bucket: str) -> None:
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            objects = page.get("Contents", [])
            if objects:
                self._s3.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": o["Key"]} for o in objects]},
                )
