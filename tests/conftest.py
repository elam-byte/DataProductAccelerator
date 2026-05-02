from pathlib import Path

import pytest
import yaml


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


@pytest.fixture
def customer_360_config():
    from dpa.config import load_product_config
    return load_product_config(EXAMPLES_DIR / "customer_360.yml")


@pytest.fixture
def order_events_config():
    from dpa.config import load_product_config
    return load_product_config(EXAMPLES_DIR / "order_events.yml")


@pytest.fixture
def minimal_config_dict():
    return {
        "name": "test_product",
        "version": "1.0.0",
        "owner": {"team": "eng", "email": "eng@example.com"},
        "sla": {"freshness_hours": 24},
        "tables": [
            {
                "name": "test_table",
                "tier": "gold",
                "schema": [
                    {"name": "id", "type": "string", "nullable": False},
                    {"name": "value", "type": "double"},
                ],
            }
        ],
    }
