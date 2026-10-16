import pytest

from gymbot_core import catalog


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("supino reto", "bench_press_barbell"),
        ("Supino", "bench_press_barbell"),
        ("SUPINO RETO COM BARRA", "bench_press_barbell"),
        ("supino inclinado com halteres", "incline_bench_press_dumbbell"),
        ("Tríceps  Pulley!", "triceps_pushdown"),
        ("triceps corda", "triceps_pushdown"),
        ("serrote", "dumbbell_row"),
        ("agachamento", "squat_barbell"),
        ("elevação lateral", "lateral_raise"),
        ("rosca martelo", "hammer_curl"),
    ],
)
def test_resolves_names_and_aliases_ignoring_accents_and_case(raw: str, expected: str) -> None:
    assert catalog.resolve(raw) == expected


def test_small_typo_is_resolved_by_fuzzy_match() -> None:
    assert catalog.resolve("agachamento livre") == catalog.resolve("agachamentoo livre")


def test_unknown_exercise_becomes_a_custom_slug() -> None:
    assert catalog.resolve("Remada Cavalinho Maluca") == "custom:remada-cavalinho-maluca"


def test_similar_but_different_exercises_are_not_merged() -> None:
    assert catalog.resolve("supino reto") != catalog.resolve("supino inclinado")
    assert catalog.resolve("rosca direta") != catalog.resolve("rosca martelo")
    assert catalog.resolve("crucifixo") != catalog.resolve("crucifixo inverso")


def test_empty_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        catalog.resolve("  !! ")


def test_display_name_for_catalog_and_custom() -> None:
    assert catalog.display_name("bench_press_barbell") == "supino reto"
    assert catalog.display_name("custom:remada-cavalinho") == "remada cavalinho"


def test_catalog_ids_are_unique_and_every_alias_is_unambiguous() -> None:
    # _load levanta ValueError se dois exercicios compartilharem um alias.
    exercises = catalog.all_exercises()
    assert len(exercises) == len({e.id for e in exercises})
    assert len(exercises) >= 40
