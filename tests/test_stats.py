from datetime import UTC, datetime

import pytest

from gymbot_core.models import ExerciseLog, SetEntry
from gymbot_core.stats import summarize

NOW = datetime(2026, 10, 16, tzinfo=UTC)


def _log(date: str, *sets: tuple[int, float], log_id: str = "a") -> ExerciseLog:
    return ExerciseLog(
        log_id=log_id,
        date=date,
        exercise_id="bench_press_barbell",
        exercise_raw="supino",
        sets=[SetEntry(reps=r, load_kg=w) for r, w in sets],
        created_at=NOW,
    )


def test_no_logs_means_no_stats() -> None:
    assert summarize("bench_press_barbell", []) is None


def test_single_session_has_no_trend() -> None:
    stats = summarize("bench_press_barbell", [_log("2026-10-01", (10, 30), (10, 30))])
    assert stats is not None
    assert stats.sessions == 1 and stats.trend == "insuficiente" and stats.e1rm_change_pct is None
    assert stats.total_volume_kg == 600


def test_records_and_volume_across_sessions_in_any_input_order() -> None:
    logs = [
        _log("2026-10-15", (8, 40), log_id="c"),
        _log("2026-10-01", (10, 30), (10, 30), log_id="a"),
        _log("2026-10-08", (10, 35), log_id="b"),
    ]
    stats = summarize("bench_press_barbell", logs)
    assert stats is not None
    assert (stats.first_date, stats.last_date) == ("2026-10-01", "2026-10-15")
    assert (stats.best_load_kg, stats.best_load_date) == (40, "2026-10-15")
    assert stats.total_volume_kg == 600 + 350 + 320


def test_best_e1rm_uses_epley_and_may_differ_from_best_load() -> None:
    logs = [_log("2026-10-01", (3, 100)), _log("2026-10-08", (12, 90), log_id="b")]
    stats = summarize("bench_press_barbell", logs)
    assert stats is not None
    assert stats.best_load_kg == 100
    # 90 * (1 + 12/30) = 126 > 100 * (1 + 3/30) = 110
    assert (stats.best_e1rm_kg, stats.best_e1rm_date) == (126.0, "2026-10-08")


@pytest.mark.parametrize(
    ("last_load", "trend"),
    [(33, "subindo"), (30.5, "estavel"), (27, "caindo")],
)
def test_trend_compares_first_and_last_session_estimated_1rm(last_load: float, trend: str) -> None:
    logs = [_log("2026-10-01", (10, 30)), _log("2026-10-15", (10, last_load), log_id="b")]
    stats = summarize("bench_press_barbell", logs)
    assert stats is not None and stats.trend == trend


def test_change_percentage_is_computed_in_code() -> None:
    logs = [_log("2026-10-01", (10, 30)), _log("2026-10-15", (10, 33), log_id="b")]
    stats = summarize("bench_press_barbell", logs)
    assert stats is not None and stats.e1rm_change_pct == 10.0
