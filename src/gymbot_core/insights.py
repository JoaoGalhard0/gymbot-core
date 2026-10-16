"""Evolucao no periodo (J5): estatisticas calculadas em codigo; o LLM so resume."""

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from gymbot_core import catalog
from gymbot_core.models import ExerciseLog
from gymbot_core.repository import Repository
from gymbot_core.stats import summarize

MAX_EXERCISES = 10
MAX_DAYS = 366
HISTORY_LIMIT = 500  # teto de registros lidos por exercicio no periodo


def progress(
    repo: Repository, user_id: int, today: str, exercise_id: str | None, days: int
) -> dict[str, Any]:
    """Evolucao de um exercicio, ou de todos os treinados no periodo se ``exercise_id`` for None."""
    days = max(1, min(days, MAX_DAYS))
    since = (date.fromisoformat(today) - timedelta(days=days)).isoformat()

    if exercise_id:
        logs = repo.last_logs(user_id, exercise_id, limit=HISTORY_LIMIT, since=since)
    else:
        logs = repo.logs_between(user_id, since, today)

    grouped: dict[str, list[ExerciseLog]] = defaultdict(list)
    for log in logs:
        grouped[log.exercise_id].append(log)

    stats = [s for ex_id, items in grouped.items() if (s := summarize(ex_id, items))]
    stats.sort(key=lambda s: s.sessions, reverse=True)
    return {
        "period": {"from": since, "to": today, "days": days},
        "exercises": [
            {
                "exercise": catalog.display_name(s.exercise_id),
                **s.model_dump(exclude={"exercise_id"}),
            }
            for s in stats[:MAX_EXERCISES]
        ],
        "total_exercises": len(stats),
    }
