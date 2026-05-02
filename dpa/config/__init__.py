from pathlib import Path

import yaml
from pydantic import ValidationError

from dpa.models import DataProductConfig
from dpa.utils.errors import ConfigValidationError


def load_product_config(path: Path) -> DataProductConfig:
    """Load and validate a data product YAML config file."""
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ConfigValidationError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigValidationError(f"{path} must contain a YAML mapping at the top level")

    try:
        return DataProductConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigValidationError(f"Config validation failed for {path}:\n{e}") from e
