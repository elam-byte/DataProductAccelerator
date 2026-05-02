from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from dpa.models import DataProductConfig
from dpa.provisioners.storage import StorageProvisioner
from dpa.utils.errors import ProvisionerError


@pytest.fixture
def mock_s3():
    with patch("dpa.provisioners.storage.boto3.client") as mock_client:
        s3 = MagicMock()
        mock_client.return_value = s3
        yield s3


class TestStorageProvisioner:
    def test_provision_creates_bucket(self, mock_s3, minimal_config_dict):
        config = DataProductConfig.model_validate(minimal_config_dict)
        p = StorageProvisioner()
        result = p.provision(config)

        assert result.success
        mock_s3.create_bucket.assert_called_once_with(Bucket=config.bucket_name)

    def test_provision_puts_tier_markers(self, mock_s3, minimal_config_dict):
        config = DataProductConfig.model_validate(minimal_config_dict)
        StorageProvisioner().provision(config)

        put_keys = {call.kwargs["Key"] for call in mock_s3.put_object.call_args_list}
        assert "bronze/.keep" in put_keys
        assert "silver/.keep" in put_keys
        assert "gold/.keep" in put_keys

    def test_provision_sets_lifecycle_policy(self, mock_s3, minimal_config_dict):
        config = DataProductConfig.model_validate(minimal_config_dict)
        StorageProvisioner().provision(config)
        mock_s3.put_bucket_lifecycle_configuration.assert_called_once()

    def test_bucket_already_exists_is_idempotent(self, mock_s3, minimal_config_dict):
        mock_s3.create_bucket.side_effect = ClientError(
            {"Error": {"Code": "BucketAlreadyOwnedByYou"}}, "CreateBucket"
        )
        config = DataProductConfig.model_validate(minimal_config_dict)
        result = StorageProvisioner().provision(config)
        assert result.success

    def test_unexpected_client_error_raises(self, mock_s3, minimal_config_dict):
        mock_s3.create_bucket.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "CreateBucket"
        )
        config = DataProductConfig.model_validate(minimal_config_dict)
        with pytest.raises(ProvisionerError):
            StorageProvisioner().provision(config)

    def test_teardown_returns_skip_when_bucket_missing(self, mock_s3, minimal_config_dict):
        mock_s3.get_paginator.return_value.paginate.return_value = iter([{"Contents": []}])
        mock_s3.delete_bucket.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket"}}, "DeleteBucket"
        )
        config = DataProductConfig.model_validate(minimal_config_dict)
        result = StorageProvisioner().teardown(config)
        assert result.skipped
