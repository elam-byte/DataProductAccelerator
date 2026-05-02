from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from dpa.models import DataProductConfig


@dataclass
class ProvisionResult:
    provisioner: str
    success: bool
    resource_ids: list[str] = field(default_factory=list)
    message: str = ""
    skipped: bool = False

    @classmethod
    def ok(cls, provisioner: str, resource_ids: list[str], message: str = "") -> ProvisionResult:
        return cls(provisioner=provisioner, success=True, resource_ids=resource_ids, message=message)

    @classmethod
    def skip(cls, provisioner: str, reason: str) -> ProvisionResult:
        return cls(provisioner=provisioner, success=True, skipped=True, message=reason)

    @classmethod
    def fail(cls, provisioner: str, message: str) -> ProvisionResult:
        return cls(provisioner=provisioner, success=False, message=message)

    def __str__(self) -> str:
        if self.skipped:
            return f"[{self.provisioner}] SKIPPED — {self.message}"
        status = "OK" if self.success else "FAILED"
        return f"[{self.provisioner}] {status} — {self.message or ', '.join(self.resource_ids)}"


class Provisioner(ABC):
    """Abstract base for all DPA provisioners."""

    name: str = "base"

    @abstractmethod
    def provision(self, config: DataProductConfig) -> ProvisionResult:
        """Create all resources defined by the data product config."""

    @abstractmethod
    def teardown(self, config: DataProductConfig) -> ProvisionResult:
        """Remove all resources that were created during provision."""
