import pytest
from pydantic import ValidationError

from gymbot_core.models import Note, SetEntry


@pytest.mark.parametrize(("reps", "load"), [(0, 30), (-1, 30), (101, 30), (10, -5), (10, 1001)])
def test_set_bounds_are_enforced(reps: int, load: float) -> None:
    with pytest.raises(ValidationError):
        SetEntry(reps=reps, load_kg=load)


def test_note_rejects_unknown_category_and_bad_date() -> None:
    with pytest.raises(ValidationError):
        Note.model_validate(
            {
                "note_id": "1",
                "date": "2026-10-16",
                "category": "humor",
                "text": "x",
                "created_at": "2026-10-16T00:00:00Z",
            }
        )
    with pytest.raises(ValidationError):
        Note.model_validate(
            {
                "note_id": "1",
                "date": "16/10/2026",
                "text": "x",
                "created_at": "2026-10-16T00:00:00Z",
            }
        )
