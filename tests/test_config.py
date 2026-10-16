import boto3
import pytest
from moto import mock_aws

from gymbot_core import config


def test_parse_allowlist() -> None:
    assert config.parse_allowlist("123, 456,,") == frozenset({123, 456})
    assert config.parse_allowlist("") == frozenset()


def test_parse_allowlist_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        config.parse_allowlist("123,abc")


@mock_aws
def test_secret_and_parameter_are_read_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    config.get_secret.cache_clear()
    config.get_parameter.cache_clear()
    boto3.client("secretsmanager", region_name="us-east-1").create_secret(
        Name="gymbot/test/token", SecretString="abc"
    )
    boto3.client("ssm", region_name="us-east-1").put_parameter(
        Name="/gymbot/test/allowlist", Value="1,2", Type="String"
    )
    assert config.get_secret("gymbot/test/token") == "abc"
    assert config.get_parameter("/gymbot/test/allowlist") == "1,2"
    assert config.get_secret.cache_info().hits == 0
    config.get_secret("gymbot/test/token")
    assert config.get_secret.cache_info().hits == 1
