"""Contrato das propostas de confirmacao (ADR 009) nas duas implementacoes do repositorio."""

from collections.abc import Iterator
from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws

from gymbot_core.memory import InMemoryRepository
from gymbot_core.models import ExerciseLog, Proposal, SetEntry
from gymbot_core.repository import Repository, TrainingRepository
from gymbot_core.table import table_definition

NOW = datetime(2026, 10, 16, 21, 0, tzinfo=UTC)


@pytest.fixture(params=["dynamodb", "memory"])
def repo(request: pytest.FixtureRequest) -> Iterator[Repository]:
    if request.param == "memory":
        yield InMemoryRepository()
        return
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        yield TrainingRepository(dynamodb.create_table(**table_definition("gymbot-test")))


def _proposal(proposal_id: str = "p1", **kw: object) -> Proposal:
    base: dict[str, object] = {
        "proposal_id": proposal_id,
        "action": "upsert_plan",
        "fingerprint": "f" * 16,
        "update_id": 100,
        "created_at": NOW,
    }
    return Proposal.model_validate({**base, **kw})


def test_proposal_round_trips_and_missing_is_none(repo: Repository) -> None:
    assert repo.get_proposal(1, "p1") is None
    repo.put_proposal(1, _proposal())
    stored = repo.get_proposal(1, "p1")
    assert stored is not None
    assert (stored.action, stored.update_id, stored.consumed_by) == ("upsert_plan", 100, None)


def test_proposals_are_per_user(repo: Repository) -> None:
    repo.put_proposal(1, _proposal())
    assert repo.get_proposal(2, "p1") is None


def test_marking_a_proposal_consumed_is_persisted(repo: Repository) -> None:
    repo.put_proposal(1, _proposal())
    repo.put_proposal(1, _proposal(consumed_by=101))
    stored = repo.get_proposal(1, "p1")
    assert stored is not None and stored.consumed_by == 101


def test_proposals_do_not_leak_into_other_queries(repo: Repository) -> None:
    repo.put_proposal(1, _proposal())
    log = ExerciseLog(
        log_id="a",
        date="2026-10-16",
        exercise_id="bench_press_barbell",
        exercise_raw="supino",
        sets=[SetEntry(reps=10, load_kg=30)],
        created_at=NOW,
    )
    repo.put_log(1, log)
    assert [entry.log_id for entry in repo.recent_logs(1, 10)] == ["a"]
    assert repo.list_schedules(1) == []


def test_dynamodb_proposals_expire_by_ttl_one_hour_after_creation() -> None:
    with mock_aws():
        table = boto3.resource("dynamodb", region_name="us-east-1").create_table(
            **table_definition("gymbot-test")
        )
        TrainingRepository(table).put_proposal(1, _proposal())
        item = table.get_item(Key={"PK": "USER#1", "SK": "PROPOSAL#p1"})["Item"]
        assert int(item["ttl"]) == int(NOW.timestamp()) + 3600
