"""Calculos puros de treino. Nada aqui faz I/O nem chama LLM (ver specs/agente.md)."""

from collections.abc import Sequence

from pydantic import BaseModel

from gymbot_core.models import SetEntry


class Comparison(BaseModel):
    """Diferenca entre duas sessoes do mesmo exercicio (atual - anterior)."""

    top_load_delta_kg: float
    volume_delta_kg: float
    volume_delta_pct: float | None  # None quando o volume anterior era zero


def total_volume(sets: Sequence[SetEntry]) -> float:
    """Volume = soma de carga x repeticoes (kg)."""
    return sum(s.load_kg * s.reps for s in sets)


def top_load(sets: Sequence[SetEntry]) -> float:
    return max(s.load_kg for s in sets)


def compare(previous: Sequence[SetEntry], current: Sequence[SetEntry]) -> Comparison:
    prev_volume, curr_volume = total_volume(previous), total_volume(current)
    return Comparison(
        top_load_delta_kg=round(top_load(current) - top_load(previous), 2),
        volume_delta_kg=round(curr_volume - prev_volume, 2),
        volume_delta_pct=round((curr_volume - prev_volume) / prev_volume * 100, 1)
        if prev_volume
        else None,
    )


def estimate_1rm(load_kg: float, reps: int) -> float:
    """1RM estimado pela formula de Epley: ``carga * (1 + reps / 30)``.

    Com ``reps == 1`` devolve a propria carga; reps <= 0 ou carga negativa sao invalidos.
    """
    if reps <= 0:
        raise ValueError("reps deve ser >= 1")
    if load_kg < 0:
        raise ValueError("load_kg nao pode ser negativo")
    if reps == 1:
        return load_kg
    return load_kg * (1 + reps / 30)
