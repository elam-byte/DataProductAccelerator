from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DPA_",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # MinIO / S3
    minio_endpoint: str = Field(default="http://localhost:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    minio_region: str = Field(default="us-east-1")

    # Iceberg REST catalog
    iceberg_catalog_uri: str = Field(default="http://localhost:8181")
    iceberg_warehouse: str = Field(default="s3://iceberg-warehouse/")

    # OpenMetadata
    openmetadata_url: str = Field(default="http://localhost:8585")
    openmetadata_token: str = Field(default="")

    # Dagster
    dagster_home: str = Field(default="./dagster_pipelines")

    # Great Expectations
    ge_project_root: str = Field(default="./ge_project")

    # dbt
    dbt_project_root: str = Field(default="./dbt_project")

    # Local catalog (SQLite)
    catalog_db_path: str = Field(default="./.dpa/catalog.db")

    # Spark (optional — only needed for dpa run)
    spark_master: str = Field(default="local[*]")
    spark_iceberg_packages: str = Field(
        default=(
            "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.0,"
            "org.apache.hadoop:hadoop-aws:3.3.4,"
            "com.amazonaws:aws-java-sdk-bundle:1.12.262"
        )
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
