"""Pre-treino (J4): treino do dia + ultima sessao + progressao calculada em codigo.

Usado pelo agente (``prepare_workout``) e pelo relatorio agendado ``pre_workout``. Toda sugestao
numerica vem de ``compute_progression``; quem narra (LLM) so repassa.
"""

from datetime import date, timedelta
from typing import Any

from gymbot_core import catalog
from gymbot_core.models import WEEKDAYS, Plan, PlanDay, PlannedExercise, Weekday
from gymbot_core.progression import Progression, compute_progression
from gymbot_core.repository import Repository

HISTORY_FOR_PROGRESSION = 6  # sessoes lidas por exercicio (estagnacao precisa de >= 3)
NOTES_WINDOW_DAYS = 7


def format_target(item: PlannedExercise) -> str:
    """4 series de 8 a 12 -> '4x8-12'; faixa fixa -> '4x10'."""
    reps = (
        str(item.reps_min) if item.reps_min == item.reps_max else f"{item.reps_min}-{item.reps_max}"
    )
    return f"{item.sets}x{reps}"


def equipment_of(exercise_id: str) -> str | None:
    exercise = catalog.get_exercise(exercise_id)
    return exercise.equipment if exercise else None


def recent_notes(repo: Repository, user_id: int, today: str) -> list[dict[str, str]]:
    start = (date.fromisoformat(today) - timedelta(days=NOTES_WINDOW_DAYS)).isoformat()
    return [
        {"date": n.date, "category": n.category, "text": n.text}
        for n in repo.notes_between(user_id, start, today)
    ]


def progression_for(
    repo: Repository, user_id: int, exercise_id: str, reps_min: int, reps_max: int
) -> tuple[Progression, list[Any]]:
    history = repo.last_logs(user_id, exercise_id, limit=HISTORY_FOR_PROGRESSION)
    progression = compute_progression(
        history, reps_min=reps_min, reps_max=reps_max, equipment=equipment_of(exercise_id)
    )
    return progression, history


def match_day(plan: Plan, focus: str) -> PlanDay | None:
    """Acha o dia do plano pelo rotulo ('costas') ou pelo grupo muscular dos exercicios."""
    wanted = catalog.normalize(focus)
    if not wanted:
        return None
    for day in plan.days:
        if wanted in catalog.normalize(day.label):
            return day
    for day in plan.days:
        groups = {
            exercise.muscle_group
            for item in day.exercises
            if (exercise := catalog.get_exercise(item.exercise_id))
        }
        if any(wanted in catalog.normalize(group) for group in groups):
            return day
    return None


def prepare_workout(
    repo: Repository,
    user_id: int,
    today: str,
    plan: Plan | None,
    weekday: Weekday | None = None,
    focus: str | None = None,
) -> dict[str, Any]:
    if plan is None:
        return {"plan_day": None, "reason": "Usuario sem plano semanal cadastrado."}

    if weekday:
        day = plan.day_for(weekday)
    elif focus:
        day = match_day(plan, focus)
    else:
        day = plan.day_for(WEEKDAYS[date.fromisoformat(today).weekday()])
    if day is None:
        return {
            "plan_day": None,
            "reason": "Nenhum dia do plano corresponde ao pedido.",
            "available_days": [{"weekday": d.weekday, "label": d.label} for d in plan.days],
        }

    exercises: list[dict[str, Any]] = []
    needs_context = False
    for item in day.exercises:
        progression, history = progression_for(
            repo, user_id, item.exercise_id, item.reps_min, item.reps_max
        )
        needs_context = needs_context or progression.stalled or progression.regressed
        exercises.append(
            {
                "exercise": catalog.display_name(item.exercise_id),
                "planned": format_target(item),
                "last_session": {
                    "date": history[0].date,
                    "sets": [{"reps": s.reps, "load_kg": s.load_kg} for s in history[0].sets],
                }
                if history
                else None,
                "progression": progression.model_dump(),
            }
        )
    result: dict[str, Any] = {
        "plan_day": {"weekday": day.weekday, "label": day.label},
        "exercises": exercises,
    }
    if needs_context:
        # Estagnou ou regrediu: notas recentes (sono, alimentacao, dor) podem explicar.
        result["recent_notes"] = recent_notes(repo, user_id, today)
    return result
