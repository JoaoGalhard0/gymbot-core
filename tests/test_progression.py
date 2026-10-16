from datetime import UTC, datetime

import pytest

from gymbot_core.models import ExerciseLog, SetEntry
from gymbot_core.progression import compute_progression, is_regressed, is_stalled

NOW = datetime(2026, 10, 16, tzinfo=UTC)


def _log(day: int, *sets: tuple[int, float]) -> ExerciseLog:
    """Sessao em 2026-09-<day>; sets = (reps, carga)."""
    return ExerciseLog(
        log_id=f"l{day:02d}",
        date=f"2026-09-{day:02d}",
        exercise_id="bench_press_barbell",
        exercise_raw="supino",
        sets=[SetEntry(reps=r, load_kg=w) for r, w in sets],
        created_at=NOW,
    )


def test_no_history_has_no_numbers() -> None:
    result = compute_progression([])
    assert result.action == "no_history"
    assert result.suggested_load_kg is None and result.target_reps is None


def test_all_sets_at_top_of_range_increases_load_and_restarts_at_the_floor() -> None:
    history = [_log(20, (12, 30), (12, 30), (12, 30), (12, 30))]
    result = compute_progression(history, reps_min=8, reps_max=12, equipment="barra")
    assert result.action == "increase_load"
    assert result.suggested_load_kg == 32.5  # +2.5 kg de barra
    assert result.target_reps == 8
    assert result.last_date == "2026-09-20"


@pytest.mark.parametrize(
    ("equipment", "increment"),
    [
        ("barra", 2.5),
        ("halter", 2.0),
        ("maquina", 5.0),
        ("cabo", 2.5),
        ("desconhecido", 2.5),
        (None, 2.5),
    ],
)
def test_increment_depends_on_the_equipment(equipment: str | None, increment: float) -> None:
    history = [_log(20, (12, 20), (12, 20))]
    result = compute_progression(history, reps_min=8, reps_max=12, equipment=equipment)
    assert result.suggested_load_kg == 20 + increment


def test_one_weak_set_keeps_the_load_and_asks_for_one_more_rep() -> None:
    history = [_log(20, (12, 30), (12, 30), (10, 30), (9, 30))]
    result = compute_progression(history, reps_min=8, reps_max=12)
    assert result.action == "hold"
    assert result.suggested_load_kg == 30
    assert result.target_reps == 10  # serie mais fraca fez 9 -> alvo 10


def test_target_never_exceeds_the_top_of_the_range() -> None:
    history = [_log(20, (12, 30), (11, 30))]
    assert compute_progression(history, reps_min=8, reps_max=12).target_reps == 12


def test_below_the_floor_suggests_reducing_the_load() -> None:
    history = [_log(20, (6, 40), (5, 40))]
    result = compute_progression(history, reps_min=8, reps_max=12)
    assert result.action == "hold"
    assert "reduzir a carga" in result.reason


def test_top_load_is_used_when_the_load_varies_between_sets() -> None:
    history = [_log(20, (12, 60), (12, 70), (12, 80))]
    assert compute_progression(history, equipment="barra").suggested_load_kg == 82.5


def test_default_range_is_8_to_12() -> None:
    history = [_log(20, (12, 30))]
    assert compute_progression(history).action == "increase_load"
    assert compute_progression([_log(20, (11, 30))]).action == "hold"


def test_stalled_after_three_sessions_without_improvement() -> None:
    history = [_log(20, (10, 30)), _log(13, (10, 30)), _log(6, (10, 30))]
    assert is_stalled(history) is True
    assert compute_progression(history).stalled is True


def test_not_stalled_when_the_latest_session_improved() -> None:
    assert is_stalled([_log(20, (10, 32.5)), _log(13, (10, 30)), _log(6, (10, 30))]) is False
    assert is_stalled([_log(20, (11, 30)), _log(13, (10, 30)), _log(6, (10, 30))]) is False


def test_not_stalled_with_fewer_than_three_sessions() -> None:
    assert is_stalled([_log(20, (10, 30)), _log(13, (10, 30))]) is False


def test_regressed_when_volume_drops_more_than_ten_percent_vs_prior_average() -> None:
    prior = [_log(13, (10, 30), (10, 30)), _log(6, (10, 30), (10, 30))]  # 600 cada
    assert is_regressed([_log(20, (10, 30), (7, 30)), *prior]) is True  # 510 < 540
    assert is_regressed([_log(20, (10, 30), (9, 30)), *prior]) is False  # 570 >= 540


def test_regression_needs_at_least_two_prior_sessions() -> None:
    assert is_regressed([_log(20, (1, 10)), _log(13, (10, 30))]) is False
