"""Modelos de dominio. Datas de treino ('YYYY-MM-DD') sao no fuso do usuario; timestamps em UTC."""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DEFAULT_TIMEZONE = "America/Sao_Paulo"
NoteCategory = Literal["sono", "alimentacao", "dor", "outro"]


class SetEntry(BaseModel):
    reps: int = Field(ge=1, le=100)
    load_kg: float = Field(ge=0, le=1000)


class ExerciseLog(BaseModel):
    log_id: str
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    exercise_id: str
    exercise_raw: str
    sets: list[SetEntry] = Field(min_length=1)
    unit_original: Literal["kg", "lb"] = "kg"
    rpe: float | None = Field(default=None, ge=1, le=10)
    note: str | None = None
    source_update_id: int | None = None
    created_at: datetime
    deleted_at: datetime | None = None

    @property
    def ref(self) -> str:
        """Referencia opaca para corrigir/apagar o registro: '<data>#<log_id>'."""
        return f"{self.date}#{self.log_id}"


class Note(BaseModel):
    note_id: str
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    category: NoteCategory = "outro"
    text: str = Field(min_length=1, max_length=1000)
    created_at: datetime


PROPOSAL_TTL = timedelta(hours=1)


class Proposal(BaseModel):
    """Pre-visualizacao de uma acao sensivel, guardada no servidor (ADR 009).

    Confirmar exige o ``proposal_id`` devolvido na pre-visualizacao, feita em uma mensagem
    ANTERIOR do usuario (``update_id`` menor), com exatamente os mesmos dados (``fingerprint``).
    """

    proposal_id: str
    action: str
    fingerprint: str
    update_id: int  # mensagem do usuario em que a pre-visualizacao foi feita
    created_at: datetime
    consumed_by: int | None = None  # update_id que a confirmou (retry da mesma mensagem e ok)


class UserProfile(BaseModel):
    user_id: int
    chat_id: int
    name: str | None = None
    timezone: str = DEFAULT_TIMEZONE
    created_at: datetime


# ---- plano semanal (J2) ---------------------------------------------------------------------
Weekday = Literal["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
WEEKDAYS: tuple[Weekday, ...] = (
    "segunda",
    "terca",
    "quarta",
    "quinta",
    "sexta",
    "sabado",
    "domingo",
)  # a posicao e o ``date.weekday()``


class PlannedExercise(BaseModel):
    exercise_id: str
    exercise_raw: str
    sets: int = Field(ge=1, le=20)
    reps_min: int = Field(ge=1, le=100)
    reps_max: int = Field(ge=1, le=100)
    note: str | None = None

    @model_validator(mode="after")
    def _range_is_ordered(self) -> "PlannedExercise":
        if self.reps_min > self.reps_max:
            raise ValueError("reps_min nao pode ser maior que reps_max")
        return self


class PlanDay(BaseModel):
    weekday: Weekday
    label: str = ""  # ex.: "peito e triceps"
    exercises: list[PlannedExercise] = Field(min_length=1)


class Plan(BaseModel):
    version: str
    days: list[PlanDay]
    created_at: datetime

    @model_validator(mode="after")
    def _one_day_per_weekday_in_week_order(self) -> "Plan":
        weekdays = [d.weekday for d in self.days]
        if len(set(weekdays)) != len(weekdays):
            raise ValueError("um mesmo dia da semana aparece duas vezes no plano")
        self.days.sort(key=lambda d: WEEKDAYS.index(d.weekday))
        return self

    def day_for(self, weekday: Weekday) -> PlanDay | None:
        return next((d for d in self.days if d.weekday == weekday), None)
