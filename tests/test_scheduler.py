"""EventBridgeScheduler contra o moto (que replica Conflict/NotFound do Scheduler real)."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from gymbot_core.schedule import Recurrence, ReportSchedule
from gymbot_core.scheduler import EventBridgeScheduler, InMemoryScheduler, SchedulerTarget

GROUP = "gymbot-reports-test"
TARGET = SchedulerTarget(
    lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:reports",
    role_arn="arn:aws:iam::123456789012:role/gymbot-scheduler-invoke-test",
    dlq_arn="arn:aws:sqs:us-east-1:123456789012:gymbot-reports-dlq-test",
)


def _schedule(schedule_id: str = "s1", hour: int = 7) -> ReportSchedule:
    return ReportSchedule(
        schedule_id=schedule_id,
        report_type="weekly_summary",
        recurrence=Recurrence(weekdays=["segunda"], hour=hour),
        timezone="America/Sao_Paulo",
        created_at=datetime(2026, 10, 16, tzinfo=UTC),
    )


@pytest.fixture
def client() -> Iterator[Any]:
    with mock_aws():
        scheduler = boto3.client("scheduler", region_name="us-east-1")
        scheduler.create_schedule_group(Name=GROUP)
        yield scheduler


def test_upsert_creates_a_schedule_with_cron_timezone_retry_and_dlq(client: Any) -> None:
    EventBridgeScheduler(client, GROUP, TARGET).upsert(42, _schedule())
    created = client.get_schedule(Name="u42-s1", GroupName=GROUP)
    assert created["ScheduleExpression"] == "cron(0 7 ? * MON *)"
    assert created["ScheduleExpressionTimezone"] == "America/Sao_Paulo"
    assert created["FlexibleTimeWindow"] == {"Mode": "OFF"}
    target = created["Target"]
    assert target["Arn"] == TARGET.lambda_arn and target["RoleArn"] == TARGET.role_arn
    assert target["RetryPolicy"]["MaximumRetryAttempts"] == 3
    assert target["DeadLetterConfig"]["Arn"] == TARGET.dlq_arn
    assert json.loads(target["Input"]) == {"user_id": 42, "schedule_id": "s1"}


def test_upsert_twice_updates_instead_of_failing(client: Any) -> None:
    gateway = EventBridgeScheduler(client, GROUP, TARGET)
    gateway.upsert(42, _schedule(hour=7))
    gateway.upsert(42, _schedule(hour=9))  # retry ou edicao: Conflict vira update
    assert (
        client.get_schedule(Name="u42-s1", GroupName=GROUP)["ScheduleExpression"]
        == "cron(0 9 ? * MON *)"
    )
    assert len(client.list_schedules(GroupName=GROUP)["Schedules"]) == 1


def test_delete_removes_and_is_idempotent(client: Any) -> None:
    gateway = EventBridgeScheduler(client, GROUP, TARGET)
    gateway.upsert(42, _schedule())
    gateway.delete(42, "s1")
    gateway.delete(42, "s1")  # ja nao existe: sem erro
    assert client.list_schedules(GroupName=GROUP)["Schedules"] == []


def test_delete_only_client_works_without_a_target_but_cannot_create(client: Any) -> None:
    EventBridgeScheduler(client, GROUP, TARGET).upsert(42, _schedule())
    deleter = EventBridgeScheduler(client, GROUP)  # como a Lambda de relatorios
    deleter.delete(42, "s1")
    assert client.list_schedules(GroupName=GROUP)["Schedules"] == []
    with pytest.raises(RuntimeError):
        deleter.upsert(42, _schedule())


class DeniedClient:
    """Cliente cujo Scheduler responde AccessDenied (ex.: falta iam:PassRole)."""

    def _denied(self, operation: str) -> ClientError:
        return ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, operation)

    def create_schedule(self, **_: Any) -> None:
        raise self._denied("CreateSchedule")

    def update_schedule(self, **_: Any) -> None:
        raise self._denied("UpdateSchedule")

    def delete_schedule(self, **_: Any) -> None:
        raise self._denied("DeleteSchedule")


def test_errors_other_than_conflict_or_not_found_are_not_swallowed() -> None:
    gateway = EventBridgeScheduler(DeniedClient(), GROUP, TARGET)
    with pytest.raises(ClientError):
        gateway.upsert(42, _schedule())
    with pytest.raises(ClientError):
        gateway.delete(42, "s1")


def test_schedules_of_different_users_do_not_collide(client: Any) -> None:
    gateway = EventBridgeScheduler(client, GROUP, TARGET)
    gateway.upsert(1, _schedule("same"))
    gateway.upsert(2, _schedule("same"))
    names = {s["Name"] for s in client.list_schedules(GroupName=GROUP)["Schedules"]}
    assert names == {"u1-same", "u2-same"}


# ---- versao em memoria: mesmo contrato ---------------------------------------------------------
def test_in_memory_scheduler_has_the_same_contract() -> None:
    gateway = InMemoryScheduler()
    gateway.upsert(42, _schedule(hour=7))
    gateway.upsert(42, _schedule(hour=9))
    assert gateway.schedules["u42-s1"]["cron"] == "cron(0 9 ? * MON *)"
    gateway.delete(42, "s1")
    gateway.delete(42, "s1")
    assert gateway.schedules == {}


def test_in_memory_scheduler_can_simulate_an_outage_once() -> None:
    gateway = InMemoryScheduler(fail_with=RuntimeError("aws fora do ar"))
    with pytest.raises(RuntimeError):
        gateway.upsert(42, _schedule())
    gateway.upsert(42, _schedule())  # a falha e de uma chamada so
    assert "u42-s1" in gateway.schedules
