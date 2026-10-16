from datetime import UTC, datetime

from gymbot_core import reports
from gymbot_core.memory import InMemoryRepository
from gymbot_core.models import (
    ExerciseLog,
    Note,
    Plan,
    PlanDay,
    PlannedExercise,
    SetEntry,
)
from gymbot_core.schedule import Recurrence, ReportSchedule

NOW = datetime(2026, 10, 16, 21, 0, tzinfo=UTC)
TODAY = "2026-10-16"  # periodo semanal: 2026-10-10 a 2026-10-16
UID = 1
BENCH, SQUAT = "bench_press_barbell", "squat_barbell"


def _log(
    log_id: str, date: str, exercise: str, load: float, reps: int = 10, sets: int = 4
) -> ExerciseLog:
    return ExerciseLog(
        log_id=log_id,
        date=date,
        exercise_id=exercise,
        exercise_raw=exercise,
        sets=[SetEntry(reps=reps, load_kg=load)] * sets,
        created_at=NOW,
    )


def _schedule(report_type: str = "weekly_summary", **kw: object) -> ReportSchedule:
    base: dict[str, object] = {
        "schedule_id": "s",
        "report_type": report_type,
        "recurrence": Recurrence(weekdays=["segunda"], hour=7),
        "timezone": "America/Sao_Paulo",
        "created_at": NOW,
        "status": "active",
    }
    return ReportSchedule.model_validate({**base, **kw})


def test_a_week_without_training_is_not_an_error() -> None:
    result = reports.weekly_summary(InMemoryRepository(), UID, TODAY)
    assert result["sessions"] == 0 and result["exercises"] == []
    assert result["period"] == {"from": "2026-10-10", "to": TODAY}


def test_weekly_summary_counts_distinct_days_and_groups_volume_by_muscle() -> None:
    repo = InMemoryRepository()
    repo.put_log(UID, _log("a", "2026-10-12", BENCH, 30))  # 4x10x30 = 1200 (peito)
    repo.put_log(UID, _log("b", "2026-10-12", SQUAT, 60))  # 2400 (pernas)
    repo.put_log(UID, _log("c", "2026-10-15", BENCH, 32.5))  # 1300 (peito)
    result = reports.weekly_summary(repo, UID, TODAY)
    assert result["sessions"] == 2  # dois dias distintos
    assert result["volume_by_muscle_group"] == {"peito": 2500.0, "pernas": 2400.0}
    assert next(iter(result["volume_by_muscle_group"])) == "peito"  # do maior para o menor
    assert result["total_volume_kg"] == 4900.0


def test_logs_outside_the_window_are_ignored() -> None:
    repo = InMemoryRepository()
    repo.put_log(UID, _log("old", "2026-10-09", BENCH, 99))
    repo.put_log(UID, _log("new", "2026-10-14", BENCH, 30))
    result = reports.weekly_summary(repo, UID, TODAY)
    assert result["exercises"][0]["sessions"] == 1
    assert result["exercises"][0]["best_load_kg"] == 30


def test_new_best_load_and_first_time_flags() -> None:
    repo = InMemoryRepository()
    repo.put_log(UID, _log("prev", "2026-09-20", BENCH, 30))
    repo.put_log(UID, _log("now", "2026-10-14", BENCH, 35))  # supera 30
    repo.put_log(UID, _log("sq", "2026-10-14", SQUAT, 60))  # primeira vez
    by_name = {e["exercise"]: e for e in reports.weekly_summary(repo, UID, TODAY)["exercises"]}
    assert by_name["supino reto"]["new_best_load"] is True
    assert by_name["supino reto"]["first_time"] is False
    assert by_name["agachamento livre"]["first_time"] is True
    assert by_name["agachamento livre"]["new_best_load"] is False


def test_equal_load_is_not_a_new_record() -> None:
    repo = InMemoryRepository()
    repo.put_log(UID, _log("prev", "2026-09-20", BENCH, 30))
    repo.put_log(UID, _log("now", "2026-10-14", BENCH, 30))
    assert reports.weekly_summary(repo, UID, TODAY)["exercises"][0]["new_best_load"] is False


def test_stalled_exercises_are_flagged_for_attention() -> None:
    repo = InMemoryRepository()
    for i, day in enumerate(["2026-09-25", "2026-10-02", "2026-10-14"]):
        repo.put_log(UID, _log(f"s{i}", day, BENCH, 30))
    result = reports.weekly_summary(repo, UID, TODAY)
    assert result["needs_attention"] == [
        {"exercise": "supino reto", "stalled": True, "regressed": False}
    ]


def test_notes_of_the_period_and_plan_size_are_included() -> None:
    repo = InMemoryRepository()
    repo.put_log(UID, _log("a", "2026-10-14", BENCH, 30))
    repo.add_note(
        UID, Note(note_id="n", date="2026-10-13", category="sono", text="dormi mal", created_at=NOW)
    )
    repo.add_note(
        UID, Note(note_id="o", date="2026-09-01", category="dor", text="antiga", created_at=NOW)
    )
    exercise = PlannedExercise(
        exercise_id=BENCH, exercise_raw="supino", sets=4, reps_min=8, reps_max=12
    )
    repo.put_plan(
        UID,
        Plan(
            version="v",
            created_at=NOW,
            days=[
                PlanDay(weekday="segunda", exercises=[exercise]),
                PlanDay(weekday="quarta", exercises=[exercise]),
            ],
        ),
    )
    result = reports.weekly_summary(repo, UID, TODAY)
    assert [n["text"] for n in result["notes"]] == ["dormi mal"]
    assert result["planned_days_per_week"] == 2


def test_summaries_are_isolated_between_users() -> None:
    repo = InMemoryRepository()
    repo.put_log(2, _log("x", "2026-10-14", BENCH, 99))
    assert reports.weekly_summary(repo, UID, TODAY)["sessions"] == 0


def test_build_report_dispatches_by_type() -> None:
    repo = InMemoryRepository()
    repo.put_log(UID, _log("a", "2026-10-14", BENCH, 30))

    weekly = reports.build_report(repo, UID, _schedule("weekly_summary"), TODAY)
    assert weekly["sessions"] == 1

    focus = reports.build_report(
        repo, UID, _schedule("exercise_focus", exercise_ids=[BENCH]), TODAY
    )
    assert focus["exercises"][0]["exercise"] == "supino reto"
    assert focus["period"]["days"] == 30

    pre = reports.build_report(repo, UID, _schedule("pre_workout"), TODAY)
    assert pre["plan_day"] is None  # sem plano: mensagem explicativa, nao erro
