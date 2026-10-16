# gymbot-core

Lib Python do GymBot: dominio, acesso ao DynamoDB e calculos de treino. **Sem LLM, sem I/O em `calc.py`.**
Specs de comportamento ficam no harness (`gymbot-harness/specs/`); aqui so o que e deste repo.

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q
```

- Codigo em `src/gymbot_core/`, testes em `tests/` (moto para DynamoDB).
- Funcoes de calculo sao puras e testadas com valores conhecidos.
- Consumidores (`gymbot-agent`, `gymbot-reports`) dependem por tag git: mudanca aqui = tag nova.
