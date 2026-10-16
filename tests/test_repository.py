from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from moto import mock_aws

from gymbot_core.models import ExerciseLog, Note, SetEntry, UserProfile
from gymbot_core.repository import TrainingRepository
from gymbot_core.table import table_definition

NOW = datetime(2026, 10, 16, 21, 0, tzinfo=UTC)


@pytest.fixture
def repo() -> Iterator[TrainingRepository]:
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        yield TrainingRepository(dynamodb.create_table(**table_definition("gymbot-test")))


def _log(
    log_id: str, date: str, load: float, reps: int = 10, exercise: str = "bench_press_barbell"
):
    return ExerciseLog(
        log_id=log_id,
        date=date,
        exercise_id=exercise,
        exercise_raw="supino",
        sets=[SetEntry(reps=reps, load_kg=load)] * 4,
        created_at=NOW,
    )


def test_profile_is_created_once_and_never_reset(repo: TrainingRepository) -> None:
    profile = UserProfile(user_id=1, chat_id=1, name="Joao", created_at=NOW)
    assert repo.create_profile(profile) is True
    changed = profile.model_copy(update={"name": "Outro", "timezone": "UTC"})
    assert repo.create_profile(changed) is False
    stored = repo.get_profile(1)
    assert stored is not None
    assert (stored.name, stored.timezone) == ("Joao", "America/Sao_Paulo")


def test_missing_profile_is_none(repo: TrainingRepository) -> None:
    assert repo.get_profile(404) is None


def test_logs_come_back_newest_first_with_float_loads(repo: TrainingRepository) -> None:
    repo.put_log(1, _log("a", "2026-10-02", 27.5))
    repo.put_log(1, _log("b", "2026-10-09", 30.0))
    repo.put_log(1, _log("c", "2026-10-16", 32.5))
    logs = repo.last_logs(1, "bench_press_barbell", limit=2)
    assert [log.log_id for log in logs] == ["c", "b"]
    assert logs[0].sets[0].load_kg == 32.5
    assert logs[0].sets[0].reps == 10


def test_put_log_is_idempotent(repo: TrainingRepository) -> None:
    for _ in range(3):
        repo.put_log(1, _log("same", "2026-10-16", 30.0))
    assert len(repo.last_logs(1, "bench_press_barbell")) == 1


def test_exclude_log_id_skips_the_log_being_compared(repo: TrainingRepository) -> None:
    repo.put_log(1, _log("old", "2026-10-09", 30.0))
    repo.put_log(1, _log("new", "2026-10-16", 32.5))
    previous = repo.last_logs(1, "bench_press_barbell", limit=1, exclude_log_id="new")
    assert [log.log_id for log in previous] == ["old"]


def test_history_is_per_exercise_and_per_user(repo: TrainingRepository) -> None:
    repo.put_log(1, _log("mine", "2026-10-16", 30.0))
    repo.put_log(2, _log("theirs", "2026-10-16", 99.0))
    repo.put_log(1, _log("other", "2026-10-16", 50.0, exercise="squat_barbell"))
    assert [log.log_id for log in repo.last_logs(1, "bench_press_barbell")] == ["mine"]
    assert [log.log_id for log in repo.last_logs(2, "bench_press_barbell")] == ["theirs"]
    assert repo.last_logs(3, "bench_press_barbell") == []


def test_soft_deleted_logs_are_hidden_and_do_not_shrink_the_page(repo: TrainingRepository) -> None:
    for i in range(4):
        repo.put_log(1, _log(f"ok{i}", f"2026-10-0{i + 1}", 20.0 + i))
    deleted = _log("gone", "2026-10-20", 90.0).model_copy(update={"deleted_at": NOW})
    repo.put_log(1, deleted)
    logs = repo.last_logs(1, "bench_press_barbell", limit=3)
    assert [log.log_id for log in logs] == ["ok3", "ok2", "ok1"]


def test_ensure_session_is_idempotent(repo: TrainingRepository) -> None:
    repo.ensure_session(1, "2026-10-16")
    repo.ensure_session(1, "2026-10-16")


def test_notes_are_returned_for_the_requested_period_only(repo: TrainingRepository) -> None:
    def note(note_id: str, date: str) -> Note:
        return Note(note_id=note_id, date=date, category="sono", text="dormi 4h", created_at=NOW)

    repo.add_note(1, note("n1", "2026-10-10"))
    repo.add_note(1, note("n2", "2026-10-16"))
    repo.add_note(1, note("n3", "2026-10-25"))
    found: list[Any] = repo.notes_between(1, "2026-10-15", "2026-10-16")
    assert [n.note_id for n in found] == ["n2"]
