"""Estatisticas de evolucao de um exercicio (J5): volume, 1RM estimado, recordes e tendencia."""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from gymbot_core.calc import estimate_1rm, top_load, total_volume
from gymbot_core.models import ExerciseLog

TREND_THRESHOLD_PCT = 2.5  # variacao do 1RM estimado abaixo disso conta como estavel

Trend = Literal["subindo", "estavel", "caindo", "insuficiente"]


class ExerciseStats(BaseModel):
    exercise_id: str
    sessions: int
    first_date: str
    last_date: str
    best_load_kg: float
    best_load_date: str
    best_e1rm_kg: float
    best_e1rm_date: str
    total_volume_kg: float
    e1rm_change_pct: float | None  # primeira -> ultima sessao; None com < 2 sessoes
    trend: Trend


def _session_e1rm(log: ExerciseLog) -> float:
    return max(estimate_1rm(s.load_kg, s.reps) for s in log.sets)


def summarize(exercise_id: str, logs: Sequence[ExerciseLog]) -> ExerciseStats | None:
    """``logs`` em qualquer ordem. Devolve None quando nao ha registros."""
    if not logs:
        return None
    ordered = sorted(logs, key=lambda log: (log.date, log.log_id))
    best_load = max(ordered, key=lambda log: top_load(log.sets))
    best_e1rm = max(ordered, key=_session_e1rm)
    first, last = _session_e1rm(ordered[0]), _session_e1rm(ordered[-1])

    change: float | None = None
    trend: Trend = "insuficiente"
    if len(ordered) >= 2 and first > 0:
        change = round((last - first) / first * 100, 1)
        trend = (
            "subindo"
            if change > TREND_THRESHOLD_PCT
            else "caindo"
            if change < -TREND_THRESHOLD_PCT
            else "estavel"
        )

    return ExerciseStats(
        exercise_id=exercise_id,
        sessions=len(ordered),
        first_date=ordered[0].date,
        last_date=ordered[-1].date,
        best_load_kg=top_load(best_load.sets),
        best_load_date=best_load.date,
        best_e1rm_kg=round(_session_e1rm(best_e1rm), 1),
        best_e1rm_date=best_e1rm.date,
        total_volume_kg=round(sum(total_volume(log.sets) for log in ordered), 1),
        e1rm_change_pct=change,
        trend=trend,
    )
