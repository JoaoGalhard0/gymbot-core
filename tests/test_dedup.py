from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws

from gymbot_core.dedup import DEDUP_TTL_SECONDS, claim_update, release_update


@pytest.fixture
def table() -> Iterator[Any]:
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        yield dynamodb.create_table(
            TableName="gymbot-test",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )


def test_first_claim_wins_and_redelivery_is_rejected(table: Any) -> None:
    assert claim_update(table, 42) is True
    assert claim_update(table, 42) is False


def test_different_updates_are_independent(table: Any) -> None:
    assert claim_update(table, 1) is True
    assert claim_update(table, 2) is True


def test_claim_sets_ttl_24h_ahead(table: Any) -> None:
    claim_update(table, 7, now=1_000_000)
    item = table.get_item(Key={"PK": "UPDATE#7", "SK": "UPDATE"})["Item"]
    assert item["ttl"] == 1_000_000 + DEDUP_TTL_SECONDS


def test_release_allows_a_new_claim(table: Any) -> None:
    claim_update(table, 9)
    release_update(table, 9)
    assert claim_update(table, 9) is True
