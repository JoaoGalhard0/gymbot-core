import pytest

from gymbot_core.calc import compare, estimate_1rm, top_load, total_volume
from gymbot_core.models import SetEntry


def _sets(*pairs: tuple[int, float]) -> list[SetEntry]:
    return [SetEntry(reps=r, load_kg=w) for r, w in pairs]


def test_one_rep_is_the_load_itself() -> None:
    assert estimate_1rm(100.0, 1) == 100.0


def test_epley_known_value() -> None:
    # 80 kg x 10 reps -> 80 * (1 + 10/30) = 106.666...
    assert estimate_1rm(80.0, 10) == pytest.approx(106.6667, abs=1e-3)


@pytest.mark.parametrize(("load", "reps"), [(50.0, 0), (50.0, -3), (-1.0, 5)])
def test_invalid_input_is_rejected(load: float, reps: int) -> None:
    with pytest.raises(ValueError):
        estimate_1rm(load, reps)


def test_volume_and_top_load() -> None:
    sets = _sets((10, 30), (10, 30), (8, 32.5))
    assert total_volume(sets) == 10 * 30 + 10 * 30 + 8 * 32.5
    assert top_load(sets) == 32.5


def test_compare_reports_load_and_volume_deltas() -> None:
    previous = _sets((10, 30), (10, 30), (10, 30), (10, 30))  # 1200
    current = _sets((10, 32.5), (10, 32.5), (10, 32.5), (8, 32.5))  # 1235
    result = compare(previous, current)
    assert result.top_load_delta_kg == 2.5
    assert result.volume_delta_kg == pytest.approx(total_volume(current) - 1200)
    assert result.volume_delta_pct == pytest.approx(
        (total_volume(current) - 1200) / 1200 * 100, abs=0.1
    )


def test_compare_with_zero_previous_volume_has_no_percentage() -> None:
    result = compare(_sets((10, 0)), _sets((10, 20)))
    assert result.volume_delta_pct is None
