"""Agendamento de relatorios: recorrencia semanal -> cron do EventBridge, proxima execucao, modelo.

O LLM nunca escreve cron: ele informa dias da semana e horario (``Recurrence``) e o codigo monta
a expressao, entao nao ha cron invalido para validar e a proxima execucao mostrada ao usuario e
calculada aqui (specs/agendamento.md, ADR 010).
"""

from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

from gymbot_core.models import WEEKDAYS, Weekday

ReportType = Literal["weekly_summary", "pre_workout", "exercise_focus"]
MAX_SCHEDULES_PER_USER = 5

_CRON_DAY: dict[str, str] = dict(
    zip(WEEKDAYS, ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], strict=True)
)
_DISPLAY_DAY = {"terca": "terça", "sabado": "sábado"}


def schedule_name(user_id: int, schedule_id: str) -> str:
    """Nome do schedule no EventBridge (limite de 64 caracteres)."""
    return f"u{user_id}-{schedule_id}"


class Recurrence(BaseModel):
    weekdays: list[Weekday] = []  # vazio = todos os dias
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)

    @model_validator(mode="after")
    def _normalize_days(self) -> "Recurrence":
        self.weekdays = sorted(set(self.weekdays), key=WEEKDAYS.index)
        if len(self.weekdays) == len(WEEKDAYS):
            self.weekdays = []  # os sete dias = todo dia
        return self

    def to_cron(self) -> str:
        """``cron(min hora dia-do-mes mes dia-da-semana ano)`` do EventBridge Scheduler."""
        if not self.weekdays:
            return f"cron({self.minute} {self.hour} * * ? *)"
        days = ",".join(_CRON_DAY[d] for d in self.weekdays)
        return f"cron({self.minute} {self.hour} ? * {days} *)"

    def describe(self) -> str:
        at = f"{self.hour:02d}:{self.minute:02d}"
        if not self.weekdays:
            return f"todos os dias às {at}"
        names = [_DISPLAY_DAY.get(d, d) for d in self.weekdays]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" e {names[-1]}"
        return f"toda {joined} às {at}"

    def next_run(self, after: datetime, timezone: str) -> datetime:
        """Proxima execucao estritamente depois de ``after``, no fuso informado."""
        tz = ZoneInfo(timezone)
        start = after.astimezone(tz)
        for offset in range(8):  # 7 dias cobrem qualquer recorrencia semanal
            day = start.date() + timedelta(days=offset)
            candidate = datetime.combine(day, time(self.hour, self.minute), tzinfo=tz)
            allowed = not self.weekdays or WEEKDAYS[day.weekday()] in self.weekdays
            if allowed and candidate > start:
                return candidate
        raise AssertionError("recorrencia sem proxima execucao")  # inalcancavel


class ReportSchedule(BaseModel):
    schedule_id: str
    report_type: ReportType
    recurrence: Recurrence
    timezone: str
    exercise_ids: list[str] = []  # so para exercise_focus
    status: Literal["pending", "active"] = "pending"
    created_at: datetime

    @model_validator(mode="after")
    def _consistent(self) -> "ReportSchedule":
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"fuso horario invalido: {self.timezone}") from error
        if self.report_type == "exercise_focus" and not self.exercise_ids:
            raise ValueError("exercise_focus precisa de ao menos um exercicio")
        return self

    def describe(self) -> str:
        return f"{self.recurrence.describe()} ({self.timezone})"
