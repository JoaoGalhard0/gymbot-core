"""H4: so se corrige erro de digitacao; nunca se funde um exercicio diferente em outro."""

import pytest

from gymbot_core import catalog


@pytest.mark.parametrize(
    "different",
    [
        "supino declinado",  # NAO e supino inclinado
        "crucifixo declinado",  # NAO e crucifixo inclinado
        "puxada atras",  # NAO e puxada frontal
        "agachamento sumo",
        "remada alta",
        "rosca concentrada",
        "rosca inversa",
        "triceps coice",
        "stiff unilateral",
        "leg press horizontal",
        "desenvolvimento arnold",
        "abdominal infra",
    ],
)
def test_a_different_exercise_is_never_merged_into_a_catalog_one(different: str) -> None:
    assert catalog.resolve(different).startswith(catalog.CUSTOM_PREFIX)


@pytest.mark.parametrize(
    ("typo", "expected"),
    [
        ("agachamentoo livre", "squat_barbell"),  # letra a mais
        ("agachmento livre", "squat_barbell"),  # letra a menos
        ("agacahmento livre", "squat_barbell"),  # duas letras adjacentes trocadas
        ("desenvolvimeto com halteres", "overhead_press_dumbbell"),
        ("supino inclinado com halteres", "incline_bench_press_dumbbell"),  # exato
    ],
)
def test_a_single_typo_in_a_long_word_is_still_recognized(typo: str, expected: str) -> None:
    assert catalog.resolve(typo) == expected


@pytest.mark.parametrize(
    "not_corrected",
    [
        "agachmeto livre",  # dois erros na mesma palavra
        "supino retto",  # 'reto' tem 4 letras: palavra curta nao se corrige
        "legg press 45",  # 'leg' e curta
        "agachamentoo livree",  # um erro em cada uma de duas palavras
    ],
)
def test_two_typos_or_short_words_are_not_corrected(not_corrected: str) -> None:
    assert catalog.resolve(not_corrected).startswith(catalog.CUSTOM_PREFIX)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("supino", "supinoo", True),  # insercao
        ("supino", "supno", True),  # remocao
        ("supino", "supimo", True),  # substituicao
        ("supino", "suipno", True),  # troca de adjacentes
        ("supino", "supino", False),  # igual nao e "erro"
        ("declinado", "inclinado", False),  # duas edicoes
        ("supino", "agacho", False),
    ],
)
def test_one_edit_apart_helper(a: str, b: str, expected: bool) -> None:
    assert catalog._one_edit_apart(a, b) is expected
