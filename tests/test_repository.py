"""Contrato do ``Repository``: o mesmo conjunto de testes roda no DynamoDB (moto) e em memoria."""

from collections.abc import Iterator
from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws

from gymbot_core.memory import InMemoryRepository
from gymbot_core.models import (
    ExerciseLog,
    Note,
    Plan,
    PlanDay,
    PlannedExercise,
    SetEntry,
    UserProfile,
)
from gymbot_core.repository import Repository, TrainingRepository
from gymbot_core.schedule import Recurrence, ReportSchedule
from gymbot_core.table import table_definition

NOW = datetime(2026, 10, 16, 21, 0, tzinfo=UTC)
BENCH = "bench_press_barbell"


@pytest.fixture(params=["dynamodb", "memory"])
def repo(request: pytest.FixtureRequest) -> Iterator[Repository]:
    if request.param == "memory":
        yield InMemoryRepository()
        return
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        yield TrainingRepository(dynamodb.create_table(**table_definition("gymbot-test")))


def _log(log_id: str, date: str, load: float, reps: int = 10, exercise: str = BENCH) -> ExerciseLog:
    return ExerciseLog(
        log_id=log_id,
        date=date,
        exercise_id=exercise,
        exercise_raw="supino",
        sets=[SetEntry(reps=reps, load_kg=load)] * 4,
        created_at=NOW,
    )


def _plan(version: str = "v1", *days: PlanDay) -> Plan:
    default = PlanDay(
        weekday="segunda",
        label="peito",
        exercises=[
            PlannedExercise(
                exercise_id=BENCH, exercise_raw="supino", sets=4, reps_min=8, reps_max=12
            )
        ],
    )
    return Plan(version=version, days=list(days) or [default], created_at=NOW)


# ---- perfil e sessao ----------------------------------------------------------------------
def test_profile_is_created_once_and_never_reset(repo: Repository) -> None:
    profile = UserProfile(user_id=1, chat_id=1, name="Joao", created_at=NOW)
    assert repo.create_profile(profile) is True
    changed = profile.model_copy(update={"name": "Outro", "timezone": "UTC"})
    assert repo.create_profile(changed) is False
    stored = repo.get_profile(1)
    assert stored is not None
    assert (stored.name, stored.timezone) == ("Joao", "America/Sao_Paulo")


def test_missing_profile_is_none(repo: Repository) -> None:
    assert repo.get_profile(404) is None


def test_ensure_session_is_idempotent(repo: Repository) -> None:
    repo.ensure_session(1, "2026-10-16")
    repo.ensure_session(1, "2026-10-16")


# ---- registros -----------------------------------------------------------------------------
def test_logs_come_back_newest_first_with_float_loads(repo: Repository) -> None:
    repo.put_log(1, _log("a", "2026-10-02", 27.5))
    repo.put_log(1, _log("b", "2026-10-09", 30.0))
    repo.put_log(1, _log("c", "2026-10-16", 32.5))
    logs = repo.last_logs(1, BENCH, limit=2)
    assert [log.log_id for log in logs] == ["c", "b"]
    assert logs[0].sets[0].load_kg == 32.5
    assert logs[0].sets[0].reps == 10


def test_put_log_is_idempotent(repo: Repository) -> None:
    for _ in range(3):
        repo.put_log(1, _log("same", "2026-10-16", 30.0))
    assert len(repo.last_logs(1, BENCH)) == 1


def test_exclude_log_id_skips_the_log_being_compared(repo: Repository) -> None:
    repo.put_log(1, _log("old", "2026-10-09", 30.0))
    repo.put_log(1, _log("new", "2026-10-16", 32.5))
    previous = repo.last_logs(1, BENCH, limit=1, exclude_log_id="new")
    assert [log.log_id for log in previous] == ["old"]


def test_since_limits_the_history_by_date(repo: Repository) -> None:
    repo.put_log(1, _log("a", "2026-09-01", 25.0))
    repo.put_log(1, _log("b", "2026-10-01", 30.0))
    repo.put_log(1, _log("c", "2026-10-15", 32.5))
    logs = repo.last_logs(1, BENCH, limit=10, since="2026-10-01")
    assert [log.log_id for log in logs] == ["c", "b"]


def test_history_is_per_exercise_and_per_user(repo: Repository) -> None:
    repo.put_log(1, _log("mine", "2026-10-16", 30.0))
    repo.put_log(2, _log("theirs", "2026-10-16", 99.0))
    repo.put_log(1, _log("other", "2026-10-16", 50.0, exercise="squat_barbell"))
    assert [log.log_id for log in repo.last_logs(1, BENCH)] == ["mine"]
    assert [log.log_id for log in repo.last_logs(2, BENCH)] == ["theirs"]
    assert repo.last_logs(3, BENCH) == []


def test_soft_deleted_logs_are_hidden_everywhere(repo: Repository) -> None:
    for i in range(4):
        repo.put_log(1, _log(f"ok{i}", f"2026-10-0{i + 1}", 20.0 + i))
    gone = _log("gone", "2026-10-20", 90.0).model_copy(update={"deleted_at": NOW})
    repo.put_log(1, gone)
    assert [log.log_id for log in repo.last_logs(1, BENCH, limit=3)] == ["ok3", "ok2", "ok1"]
    assert "gone" not in [log.log_id for log in repo.recent_logs(1, limit=10)]
    assert "gone" not in [log.log_id for log in repo.logs_between(1, "2026-10-01", "2026-10-31")]
    assert repo.get_log(1, gone.ref) is None


def test_get_log_by_ref_is_scoped_to_the_user(repo: Repository) -> None:
    log = _log("a", "2026-10-16", 30.0)
    repo.put_log(1, log)
    assert repo.get_log(1, log.ref) is not None
    assert repo.get_log(2, log.ref) is None
    assert repo.get_log(1, "2026-10-16#nao-existe") is None


def test_updating_a_log_replaces_it_without_duplicating(repo: Repository) -> None:
    original = _log("a", "2026-10-16", 30.0)
    repo.put_log(1, original)
    repo.put_log(1, original.model_copy(update={"sets": [SetEntry(reps=10, load_kg=32.0)] * 4}))
    logs = repo.last_logs(1, BENCH)
    assert len(logs) == 1 and logs[0].sets[0].load_kg == 32.0


def test_recent_logs_span_exercises_newest_first(repo: Repository) -> None:
    repo.put_log(1, _log("a", "2026-10-14", 30.0))
    repo.put_log(1, _log("b", "2026-10-15", 50.0, exercise="squat_barbell"))
    repo.put_log(1, _log("c", "2026-10-16", 20.0, exercise="lateral_raise"))
    repo.put_log(2, _log("x", "2026-10-16", 99.0))
    assert [log.log_id for log in repo.recent_logs(1, limit=2)] == ["c", "b"]
    assert [log.log_id for log in repo.recent_logs(1, limit=10)] == ["c", "b", "a"]


def test_logs_between_is_inclusive_and_oldest_first(repo: Repository) -> None:
    for log_id, date in [
        ("a", "2026-09-30"),
        ("b", "2026-10-01"),
        ("c", "2026-10-31"),
        ("d", "2026-11-01"),
    ]:
        repo.put_log(1, _log(log_id, date, 30.0))
    found = repo.logs_between(1, "2026-10-01", "2026-10-31")
    assert [log.log_id for log in found] == ["b", "c"]


# ---- notas ---------------------------------------------------------------------------------
def test_notes_are_returned_for_the_requested_period_only(repo: Repository) -> None:
    def note(note_id: str, date: str) -> Note:
        return Note(note_id=note_id, date=date, category="sono", text="dormi 4h", created_at=NOW)

    repo.add_note(1, note("n1", "2026-10-10"))
    repo.add_note(1, note("n2", "2026-10-16"))
    repo.add_note(1, note("n3", "2026-10-25"))
    assert [n.note_id for n in repo.notes_between(1, "2026-10-15", "2026-10-16")] == ["n2"]


# ---- plano ---------------------------------------------------------------------------------
def test_no_plan_means_none(repo: Repository) -> None:
    assert repo.get_plan(1) is None


def test_plan_round_trips_and_current_points_to_the_latest_version(repo: Repository) -> None:
    repo.put_plan(1, _plan("v1"))
    wednesday = PlanDay(
        weekday="quarta",
        label="costas",
        exercises=[
            PlannedExercise(
                exercise_id="lat_pulldown",
                exercise_raw="puxada",
                sets=3,
                reps_min=10,
                reps_max=12,
                note="controlar a descida",
            )
        ],
    )
    repo.put_plan(1, _plan("v2", wednesday))
    current = repo.get_plan(1)
    assert current is not None and current.version == "v2"
    assert [d.weekday for d in current.days] == ["quarta"]
    assert current.days[0].exercises[0].note == "controlar a descida"
    assert current.days[0].exercises[0].reps_max == 12


def test_put_plan_is_idempotent(repo: Repository) -> None:
    for _ in range(2):
        repo.put_plan(1, _plan("v1"))
    plan = repo.get_plan(1)
    assert plan is not None and len(plan.days) == 1


def test_plans_are_per_user(repo: Repository) -> None:
    repo.put_plan(1, _plan("v1"))
    assert repo.get_plan(2) is None


# ---- agendamentos -------------------------------------------------------------------------
def _schedule(schedule_id: str = "s1", **kw: object) -> ReportSchedule:
    base: dict[str, object] = {
        "schedule_id": schedule_id,
        "report_type": "weekly_summary",
        "recurrence": Recurrence(weekdays=["segunda"], hour=7),
        "timezone": "America/Sao_Paulo",
        "created_at": NOW,
    }
    return ReportSchedule.model_validate({**base, **kw})


def test_schedule_round_trips_and_is_listed_in_id_order(repo: Repository) -> None:
    repo.put_schedule(1, _schedule("b", status="active"))
    repo.put_schedule(
        1,
        _schedule(
            "a",
            report_type="exercise_focus",
            exercise_ids=[BENCH],
            recurrence=Recurrence(weekdays=["terca", "quinta"], hour=18, minute=30),
        ),
    )
    listed = repo.list_schedules(1)
    assert [s.schedule_id for s in listed] == ["a", "b"]
    assert listed[0].recurrence.weekdays == ["terca", "quinta"]
    assert (listed[0].recurrence.hour, listed[0].recurrence.minute) == (18, 30)
    assert listed[0].exercise_ids == [BENCH]
    assert listed[1].status == "active"


def test_get_and_delete_schedule_are_scoped_to_the_user(repo: Repository) -> None:
    repo.put_schedule(1, _schedule("s1"))
    assert repo.get_schedule(1, "s1") is not None
    assert repo.get_schedule(2, "s1") is None
    repo.delete_schedule(2, "s1")  # outro usuario: nao apaga
    assert repo.get_schedule(1, "s1") is not None
    repo.delete_schedule(1, "s1")
    repo.delete_schedule(1, "s1")  # idempotente
    assert repo.get_schedule(1, "s1") is None


def test_put_schedule_overwrites_for_status_changes(repo: Repository) -> None:
    repo.put_schedule(1, _schedule("s1", status="pending"))
    repo.put_schedule(1, _schedule("s1", status="active"))
    schedules = repo.list_schedules(1)
    assert len(schedules) == 1 and schedules[0].status == "active"


def test_schedules_do_not_leak_into_other_queries(repo: Repository) -> None:
    repo.put_schedule(1, _schedule("s1"))
    repo.put_log(1, _log("a", "2026-10-16", 30.0))
    assert [log.log_id for log in repo.recent_logs(1, 10)] == ["a"]
    assert [s.schedule_id for s in repo.list_schedules(1)] == ["s1"]
