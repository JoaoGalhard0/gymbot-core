"""Catalogo de exercicios: resolve o texto do usuario ('supino 30kg' -> 'bench_press_barbell')."""

import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from importlib import resources

import yaml

CUSTOM_PREFIX = "custom:"
# So se corrige erro de digitacao, nunca se aproxima por semelhanca: 'supino declinado' NAO e
# 'supino inclinado'. Palavras curtas (<= 4 letras, como 'reto' e 'leg') nao admitem correcao.
MIN_TYPO_WORD_LEN = 5


@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    muscle_group: str
    equipment: str


def normalize(text: str) -> str:
    """minusculas, sem acentos e sem pontuacao: 'Tríceps  (Pulley)!' -> 'triceps pulley'."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


@cache
def _load() -> tuple[dict[str, Exercise], dict[str, str]]:
    raw = yaml.safe_load(
        resources.files("gymbot_core").joinpath("exercises.yaml").read_text("utf-8")
    )
    exercises: dict[str, Exercise] = {}
    lookup: dict[str, str] = {}
    for entry in raw:
        exercise = Exercise(entry["id"], entry["name"], entry["muscle_group"], entry["equipment"])
        exercises[exercise.id] = exercise
        for label in [entry["name"], *entry.get("aliases", [])]:
            key = normalize(label)
            if lookup.setdefault(key, exercise.id) != exercise.id:
                raise ValueError(f"alias ambiguo no catalogo: {label!r}")
    return exercises, lookup


def get_exercise(exercise_id: str) -> Exercise | None:
    return _load()[0].get(exercise_id)


def display_name(exercise_id: str) -> str:
    exercise = get_exercise(exercise_id)
    if exercise:
        return exercise.name
    return exercise_id.removeprefix(CUSTOM_PREFIX).replace("-", " ")


def _one_edit_apart(a: str, b: str) -> bool:
    """Exatamente 1 insercao, remocao, troca de letra ou troca de duas letras adjacentes."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        return (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and a[diffs[0]] == b[diffs[1]]
            and a[diffs[1]] == b[diffs[0]]
        )
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long_[i]:
        i += 1
    return short[i:] == long_[i + 1 :]


def _is_typo_of(key: str, label: str) -> bool:
    """Mesmas palavras, com UM erro de digitacao em UMA palavra de pelo menos 5 letras."""
    words, label_words = key.split(), label.split()
    if len(words) != len(label_words):
        return False
    typos = 0
    for word, label_word in zip(words, label_words, strict=True):
        if word == label_word:
            continue
        if min(len(word), len(label_word)) < MIN_TYPO_WORD_LEN:
            return False
        if not _one_edit_apart(word, label_word):
            return False
        typos += 1
    return typos == 1


def resolve(raw: str) -> str:
    """Devolve o exercise_id do catalogo ou ``custom:<slug>`` quando nao reconhece."""
    key = normalize(raw)
    if not key:
        raise ValueError("nome de exercicio vazio")
    lookup = _load()[1]
    if key in lookup:
        return lookup[key]
    candidates = {exercise_id for label, exercise_id in lookup.items() if _is_typo_of(key, label)}
    if len(candidates) == 1:  # ambiguo (2+ exercicios a um erro de distancia) vira custom
        return candidates.pop()
    return CUSTOM_PREFIX + key.replace(" ", "-")


def all_exercises() -> list[Exercise]:
    return list(_load()[0].values())
