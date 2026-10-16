"""Catalogo de exercicios: resolve o texto do usuario ('supino 30kg' -> 'bench_press_barbell')."""

import difflib
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from importlib import resources

import yaml

CUSTOM_PREFIX = "custom:"
FUZZY_CUTOFF = 0.85


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


def resolve(raw: str) -> str:
    """Devolve o exercise_id do catalogo ou ``custom:<slug>`` quando nao reconhece."""
    key = normalize(raw)
    if not key:
        raise ValueError("nome de exercicio vazio")
    lookup = _load()[1]
    if key in lookup:
        return lookup[key]
    close = difflib.get_close_matches(key, lookup, n=1, cutoff=FUZZY_CUTOFF)
    if close:
        return lookup[close[0]]
    return CUSTOM_PREFIX + key.replace(" ", "-")


def all_exercises() -> list[Exercise]:
    return list(_load()[0].values())
