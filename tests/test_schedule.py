from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from gymbot_core.schedule import Recurrence, ReportSchedule, schedule_name

SP = "America/Sao_Paulo"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)  # sexta, 09:00 em Sao Paulo


@pytest.mark.parametrize(
    ("recurrence", "cron"),
    [
        (Recurrence(weekdays=["segunda"], hour=7), "cron(0 7 ? * MON *)"),
        (
            Recurrence(weekdays=["segunda", "quarta", "sexta"], hour=18, minute=30),
            "cron(30 18 ? * MON,WED,FRI *)",
        ),
        (Recurrence(weekdays=[], hour=6), "cron(0 6 * * ? *)"),
        (Recurrence(weekdays=["domingo"], hour=0), "cron(0 0 ? * SUN *)"),
    ],
)
def test_cron_expression_matches_the_eventbridge_format(recurrence: Recurrence, cron: str) -> None:
    assert recurrence.to_cron() == cron


def test_weekdays_are_deduplicated_and_put_in_week_order() -> None:
    recurrence = Recurrence(weekdays=["sexta", "segunda", "segunda"], hour=7)
    assert recurrence.weekdays == ["segunda", "sexta"]


def test_all_seven_days_means_every_day() -> None:
    every = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
    recurrence = Recurrence(weekdays=every, hour=7)  # type: ignore[arg-type]
    assert recurrence.weekdays == [] and recurrence.to_cron() == "cron(0 7 * * ? *)"


@pytest.mark.parametrize(("hour", "minute"), [(24, 0), (-1, 0), (7, 60), (7, -1)])
def test_invalid_time_is_rejected(hour: int, minute: int) -> None:
    with pytest.raises(ValidationError):
        Recurrence(weekdays=["segunda"], hour=hour, minute=minute)


def test_unknown_weekday_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Recurrence(weekdays=["lunes"], hour=7)  # type: ignore[list-item]


@pytest.mark.parametrize(
    ("recurrence", "text"),
    [
        (Recurrence(weekdays=["segunda"], hour=7), "toda segunda às 07:00"),
        (
            Recurrence(weekdays=["terca", "quinta"], hour=18, minute=5),
            "toda terça e quinta às 18:05",
        ),
        (
            Recurrence(weekdays=["segunda", "quarta", "sabado"], hour=7),
            "toda segunda, quarta e sábado às 07:00",
        ),
        (Recurrence(weekdays=[], hour=7), "todos os dias às 07:00"),
    ],
)
def test_description_is_readable_portuguese(recurrence: Recurrence, text: str) -> None:
    assert recurrence.describe() == text


def test_next_run_is_the_coming_monday_at_the_local_time() -> None:
    result = Recurrence(weekdays=["segunda"], hour=7).next_run(NOW, SP)
    assert (result.year, result.month, result.day, result.hour) == (2026, 10, 19, 7)
    assert result.tzinfo is not None and result.utcoffset() is not None


def test_next_run_later_today_when_the_time_has_not_passed() -> None:
    result = Recurrence(weekdays=["sexta"], hour=18).next_run(NOW, SP)  # hoje, 18:00 local
    assert (result.day, result.hour) == (16, 18)


def test_next_run_skips_today_when_the_time_already_passed() -> None:
    result = Recurrence(weekdays=["sexta"], hour=8).next_run(NOW, SP)  # 08:00 < 09:00 local
    assert result.day == 23  # a proxima sexta


def test_next_run_is_strictly_after_the_reference_instant() -> None:
    exactly = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)  # 07:00 local
    assert Recurrence(weekdays=["sexta"], hour=7).next_run(exactly, SP).day == 23


def test_daily_next_run_is_today_or_tomorrow() -> None:
    assert Recurrence(weekdays=[], hour=18).next_run(NOW, SP).day == 16
    assert Recurrence(weekdays=[], hour=8).next_run(NOW, SP).day == 17


def test_next_run_uses_the_users_timezone_not_utc() -> None:
    # 02:00 UTC de sabado ainda e sexta a noite em Sao Paulo (23:00).
    late = datetime(2026, 10, 17, 2, 0, tzinfo=UTC)
    assert Recurrence(weekdays=["sexta"], hour=23, minute=30).next_run(late, SP).day == 16


def test_schedule_name_fits_the_eventbridge_limit() -> None:
    assert schedule_name(5511999999999, "0" * 12) == "u5511999999999-000000000000"
    assert len(schedule_name(5511999999999, "0" * 12)) <= 64


def _schedule(**kw: object) -> ReportSchedule:
    base: dict[str, object] = {
        "schedule_id": "s",
        "report_type": "weekly_summary",
        "recurrence": Recurrence(weekdays=["segunda"], hour=7),
        "timezone": SP,
        "created_at": NOW,
    }
    return ReportSchedule.model_validate({**base, **kw})


def test_schedule_rejects_an_unknown_timezone() -> None:
    with pytest.raises(ValidationError):
        _schedule(timezone="Marte/Olympus")


def test_exercise_focus_needs_exercises() -> None:
    with pytest.raises(ValidationError):
        _schedule(report_type="exercise_focus")
    assert _schedule(report_type="exercise_focus", exercise_ids=["bench_press_barbell"])


def test_schedule_describe_includes_the_timezone() -> None:
    assert _schedule().describe() == "toda segunda às 07:00 (America/Sao_Paulo)"
