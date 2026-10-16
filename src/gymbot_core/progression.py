"""Sugestao de progressao de carga (dupla progressao). Puro: nenhum numero vem do LLM (J4).

Regras (specs/agente.md):
- Todas as series da ultima sessao no topo da faixa de reps -> sobe a carga em um incremento e
  recomeca no piso da faixa.
- Senao, mantem a carga e busca +1 repeticao na serie mais fraca.
- Estagnado: ultimas 3 sessoes sem melhora (nem carga nem repeticoes).
- Regrediu: volume da ultima sessao mais de 10% abaixo da media das ate 3 anteriores.
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from gymbot_core.calc import top_load, total_volume
from gymbot_core.models import ExerciseLog

DEFAULT_REPS_MIN = 8
DEFAULT_REPS_MAX = 12
STALL_SESSIONS = 3
REGRESSION_DROP = 0.10  # queda de volume que conta como regressao
MIN_PRIOR_SESSIONS_FOR_REGRESSION = 2

# Incremento tipico por equipamento (kg): barra e cabo em "anilhas" pequenas, halter de 2 em 2,
# maquina em uma placa. Peso corporal: primeira carga extra.
INCREMENT_KG: dict[str, float] = {
    "barra": 2.5,
    "halter": 2.0,
    "cabo": 2.5,
    "maquina": 5.0,
    "peso corporal": 2.5,
}
DEFAULT_INCREMENT_KG = 2.5

Action = Literal["no_history", "increase_load", "hold"]


class Progression(BaseModel):
    action: Action
    suggested_load_kg: float | None = None
    target_reps: int | None = None
    last_date: str | None = None
    last_top_load_kg: float | None = None
    stalled: bool = False
    regressed: bool = False
    reason: str


def _score(log: ExerciseLog) -> tuple[float, int]:
    """Ordena sessoes: mais carga vence; com a mesma carga, mais repeticoes totais."""
    return top_load(log.sets), sum(s.reps for s in log.sets)


def is_stalled(history: Sequence[ExerciseLog]) -> bool:
    """``history`` do mais novo para o mais antigo. Estagnado = nenhuma das ultimas 3 melhorou."""
    if len(history) < STALL_SESSIONS:
        return False
    newest, middle, oldest = (_score(log) for log in history[:STALL_SESSIONS])
    return newest <= middle and middle <= oldest


def is_regressed(history: Sequence[ExerciseLog]) -> bool:
    prior = history[1 : 1 + STALL_SESSIONS]
    if len(prior) < MIN_PRIOR_SESSIONS_FOR_REGRESSION:
        return False
    average = sum(total_volume(log.sets) for log in prior) / len(prior)
    return average > 0 and total_volume(history[0].sets) < average * (1 - REGRESSION_DROP)


def compute_progression(
    history: Sequence[ExerciseLog],
    *,
    reps_min: int = DEFAULT_REPS_MIN,
    reps_max: int = DEFAULT_REPS_MAX,
    equipment: str | None = None,
) -> Progression:
    if not history:
        return Progression(action="no_history", reason="Sem registros anteriores deste exercicio.")

    last = history[0]
    last_top = top_load(last.sets)
    weakest = min(s.reps for s in last.sets)
    stalled, regressed = is_stalled(history), is_regressed(history)

    if weakest >= reps_max:
        increment = INCREMENT_KG.get(equipment or "", DEFAULT_INCREMENT_KG)
        return Progression(
            action="increase_load",
            suggested_load_kg=round(last_top + increment, 2),
            target_reps=reps_min,
            reason=f"Todas as series bateram o topo da faixa ({reps_max} reps): subir a carga.",
            last_date=last.date,
            last_top_load_kg=last_top,
            stalled=stalled,
            regressed=regressed,
        )

    target = min(weakest + 1, reps_max)
    note = " Abaixo do piso da faixa: considere reduzir a carga." if weakest < reps_min else ""
    return Progression(
        action="hold",
        suggested_load_kg=last_top,
        target_reps=target,
        reason=f"Manter a carga e buscar {target} reps na serie mais fraca.{note}",
        last_date=last.date,
        last_top_load_kg=last_top,
        stalled=stalled,
        regressed=regressed,
    )
