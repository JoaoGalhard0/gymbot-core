"""Dados dos relatorios agendados (J7). Tudo calculado em codigo; o LLM so narra.

Tres tipos (specs/agendamento.md): ``weekly_summary``, ``pre_workout`` e ``exercise_focus``.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from gymbot_core import catalog, insights, workout
from gymbot_core.calc import top_load, total_volume
from gymbot_core.models import ExerciseLog
from gymbot_core.progression import compute_progression
from gymbot_core.repository import Repository
from gymbot_core.schedule import ReportSchedule
from gymbot_core.stats import summarize

WEEK_DAYS = 7
FOCUS_DAYS = 30
OTHER_GROUP = "outros"


def weekly_summary(
    repo: Repository, user_id: int, today: str, days: int = WEEK_DAYS
) -> dict[str, Any]:
    """Sessoes, volume por grupo muscular, recordes e estagnacoes dos ultimos ``days`` dias."""
    start = (date.fromisoformat(today) - timedelta(days=days - 1)).isoformat()
    logs = repo.logs_between(user_id, start, today)
    notes = repo.notes_between(user_id, start, today)
    plan = repo.get_plan(user_id)
    base: dict[str, Any] = {
        "period": {"from": start, "to": today},
        "planned_days_per_week": len(plan.days) if plan else None,
        "notes": [{"date": n.date, "category": n.category, "text": n.text} for n in notes],
    }
    if not logs:
        return {**base, "sessions": 0, "exercises": [], "volume_by_muscle_group": {}}

    grouped: dict[str, list[ExerciseLog]] = defaultdict(list)
    for log in logs:
        grouped[log.exercise_id].append(log)

    by_group: dict[str, float] = defaultdict(float)
    exercises: list[dict[str, Any]] = []
    attention: list[dict[str, Any]] = []
    for exercise_id, items in grouped.items():
        stats = summarize(exercise_id, items)
        assert stats is not None
        history = repo.last_logs(user_id, exercise_id, limit=200)
        earlier = [log for log in history if log.date < start]
        best_before = max((top_load(log.sets) for log in earlier), default=None)
        exercises.append(
            {
                "exercise": catalog.display_name(exercise_id),
                "sessions": stats.sessions,
                "best_load_kg": stats.best_load_kg,
                "volume_kg": stats.total_volume_kg,
                "first_time": best_before is None,
                "new_best_load": best_before is not None and stats.best_load_kg > best_before,
            }
        )
        group = catalog.get_exercise(exercise_id)
        by_group[group.muscle_group if group else OTHER_GROUP] += sum(
            total_volume(log.sets) for log in items
        )
        progression = compute_progression(history[: workout.HISTORY_FOR_PROGRESSION])
        if progression.stalled or progression.regressed:
            attention.append(
                {
                    "exercise": catalog.display_name(exercise_id),
                    "stalled": progression.stalled,
                    "regressed": progression.regressed,
                }
            )

    exercises.sort(key=lambda e: e["volume_kg"], reverse=True)
    return {
        **base,
        "sessions": len({log.date for log in logs}),
        "exercises": exercises,
        "volume_by_muscle_group": {
            g: round(v, 1) for g, v in sorted(by_group.items(), key=lambda kv: -kv[1])
        },
        "total_volume_kg": round(sum(by_group.values()), 1),
        "needs_attention": attention,
    }


def exercise_focus(
    repo: Repository, user_id: int, today: str, exercise_ids: list[str], days: int = FOCUS_DAYS
) -> dict[str, Any]:
    """Evolucao dos exercicios escolhidos (``scope.exercise_ids``) no periodo."""
    merged: list[dict[str, Any]] = []
    period: dict[str, Any] = {}
    for exercise_id in exercise_ids:
        result = insights.progress(repo, user_id, today, exercise_id, days)
        period = result["period"]
        merged.extend(result["exercises"])
    return {"period": period, "exercises": merged, "total_exercises": len(merged)}


def build_report(
    repo: Repository, user_id: int, schedule: ReportSchedule, today: str
) -> dict[str, Any]:
    """Dados do relatorio conforme o tipo do agendamento."""
    if schedule.report_type == "weekly_summary":
        return weekly_summary(repo, user_id, today)
    if schedule.report_type == "exercise_focus":
        return exercise_focus(repo, user_id, today, schedule.exercise_ids)
    return workout.prepare_workout(repo, user_id, today, repo.get_plan(user_id))
