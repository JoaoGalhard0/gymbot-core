"""Gateway do EventBridge Scheduler: um schedule por pedido do usuario (specs/agendamento.md).

``EventBridgeScheduler`` fala com a AWS; ``InMemoryScheduler`` tem o mesmo contrato para testes e
evals. O ``Input`` do alvo leva so ``user_id`` e ``schedule_id``: tipo de relatorio e escopo sao
lidos do item no DynamoDB quando a Lambda dispara (uma unica fonte da verdade).
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from botocore.exceptions import ClientError

from gymbot_core.schedule import ReportSchedule, schedule_name

RETRY_ATTEMPTS = 3
MAX_EVENT_AGE_SECONDS = 3600


class SchedulerGateway(Protocol):
    def upsert(self, user_id: int, schedule: ReportSchedule) -> None: ...
    def delete(self, user_id: int, schedule_id: str) -> None: ...


@dataclass(frozen=True)
class SchedulerTarget:
    lambda_arn: str
    role_arn: str  # role que o Scheduler assume para invocar a Lambda
    dlq_arn: str


def _code(error: ClientError) -> str:
    return str(error.response["Error"]["Code"])


class EventBridgeScheduler:
    def __init__(self, client: Any, group: str, target: SchedulerTarget | None = None) -> None:
        self._client = client
        self._group = group
        self._target = target  # so quem cria/altera precisa; quem so apaga (reports) nao

    def _params(self, user_id: int, schedule: ReportSchedule) -> dict[str, Any]:
        if self._target is None:
            raise RuntimeError("SchedulerTarget nao configurado: este cliente so pode apagar")
        return {
            "Name": schedule_name(user_id, schedule.schedule_id),
            "GroupName": self._group,
            "ScheduleExpression": schedule.recurrence.to_cron(),
            "ScheduleExpressionTimezone": schedule.timezone,
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {
                "Arn": self._target.lambda_arn,
                "RoleArn": self._target.role_arn,
                "Input": json.dumps({"user_id": user_id, "schedule_id": schedule.schedule_id}),
                "RetryPolicy": {
                    "MaximumRetryAttempts": RETRY_ATTEMPTS,
                    "MaximumEventAgeInSeconds": MAX_EVENT_AGE_SECONDS,
                },
                "DeadLetterConfig": {"Arn": self._target.dlq_arn},
            },
            "State": "ENABLED",
        }

    def upsert(self, user_id: int, schedule: ReportSchedule) -> None:
        """Cria; se ja existir (retry da mesma mensagem ou edicao), atualiza."""
        params = self._params(user_id, schedule)
        try:
            self._client.create_schedule(**params)
        except ClientError as error:
            if _code(error) != "ConflictException":
                raise
            self._client.update_schedule(**params)

    def delete(self, user_id: int, schedule_id: str) -> None:
        """Idempotente: apagar o que nao existe mais nao e erro."""
        try:
            self._client.delete_schedule(
                Name=schedule_name(user_id, schedule_id), GroupName=self._group
            )
        except ClientError as error:
            if _code(error) != "ResourceNotFoundException":
                raise


@dataclass
class InMemoryScheduler:
    schedules: dict[str, dict[str, Any]] = field(default_factory=dict)
    fail_with: Exception | None = None  # simula a AWS fora do ar na proxima chamada

    def _maybe_fail(self) -> None:
        if self.fail_with is not None:
            error, self.fail_with = self.fail_with, None
            raise error

    def upsert(self, user_id: int, schedule: ReportSchedule) -> None:
        self._maybe_fail()
        self.schedules[schedule_name(user_id, schedule.schedule_id)] = {
            "cron": schedule.recurrence.to_cron(),
            "timezone": schedule.timezone,
            "user_id": user_id,
            "schedule_id": schedule.schedule_id,
        }

    def delete(self, user_id: int, schedule_id: str) -> None:
        self._maybe_fail()
        self.schedules.pop(schedule_name(user_id, schedule_id), None)
