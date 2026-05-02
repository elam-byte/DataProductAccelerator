class DPAError(Exception):
    """Base exception for all DPA errors."""


class ConfigValidationError(DPAError):
    """Raised when a data product YAML config fails validation."""


class ProvisionerError(DPAError):
    """Raised when a provisioner fails to create or remove a resource."""

    def __init__(self, provisioner: str, message: str) -> None:
        super().__init__(f"[{provisioner}] {message}")
        self.provisioner = provisioner


class CatalogError(DPAError):
    """Raised on local catalog read/write failures."""


class ServiceUnavailableError(DPAError):
    """Raised when a required backing service (MinIO, OM, Dagster) is unreachable."""

    def __init__(self, service: str, endpoint: str) -> None:
        super().__init__(f"{service} is not reachable at {endpoint}")
        self.service = service
        self.endpoint = endpoint
