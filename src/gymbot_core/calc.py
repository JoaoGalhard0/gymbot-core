"""Calculos puros de treino. Nada aqui faz I/O nem chama LLM (ver specs/agente.md)."""


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
