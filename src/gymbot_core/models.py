"""Modelos de dominio. Datas de treino ('YYYY-MM-DD') sao no fuso do usuario; timestamps em UTC."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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


class Note(BaseModel):
    note_id: str
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    category: NoteCategory = "outro"
    text: str = Field(min_length=1, max_length=1000)
    created_at: datetime


class UserProfile(BaseModel):
    user_id: int
    chat_id: int
    name: str | None = None
    timezone: str = DEFAULT_TIMEZONE
    created_at: datetime
