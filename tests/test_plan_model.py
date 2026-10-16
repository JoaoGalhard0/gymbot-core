from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from gymbot_core.models import Plan, PlanDay, PlannedExercise

NOW = datetime(2026, 10, 16, tzinfo=UTC)


def _ex(reps_min: int = 8, reps_max: int = 12) -> PlannedExercise:
    return PlannedExercise(
        exercise_id="bench_press_barbell",
        exercise_raw="supino",
        sets=4,
        reps_min=reps_min,
        reps_max=reps_max,
    )


def test_rep_range_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        _ex(reps_min=12, reps_max=8)


def test_a_weekday_cannot_appear_twice() -> None:
    day = PlanDay(weekday="segunda", exercises=[_ex()])
    with pytest.raises(ValidationError):
        Plan(version="v", days=[day, day], created_at=NOW)


def test_days_are_sorted_in_week_order_and_found_by_weekday() -> None:
    plan = Plan(
        version="v",
        days=[
            PlanDay(weekday="sexta", exercises=[_ex()]),
            PlanDay(weekday="segunda", exercises=[_ex()]),
        ],
        created_at=NOW,
    )
    assert [d.weekday for d in plan.days] == ["segunda", "sexta"]
    assert plan.day_for("sexta") is not None
    assert plan.day_for("quarta") is None


def test_a_day_needs_at_least_one_exercise() -> None:
    with pytest.raises(ValidationError):
        PlanDay(weekday="segunda", exercises=[])
