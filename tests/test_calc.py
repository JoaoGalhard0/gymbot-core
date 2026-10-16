import pytest

from gymbot_core.calc import estimate_1rm


def test_one_rep_is_the_load_itself() -> None:
    assert estimate_1rm(100.0, 1) == 100.0


def test_epley_known_value() -> None:
    # 80 kg x 10 reps -> 80 * (1 + 10/30) = 106.666...
    assert estimate_1rm(80.0, 10) == pytest.approx(106.6667, abs=1e-3)


@pytest.mark.parametrize(("load", "reps"), [(50.0, 0), (50.0, -3), (-1.0, 5)])
def test_invalid_input_is_rejected(load: float, reps: int) -> None:
    with pytest.raises(ValueError):
        estimate_1rm(load, reps)
