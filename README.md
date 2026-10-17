# gymbot-core

Biblioteca Python do [GymBot](https://github.com/JoaoGalhard0/gymbot-harness): tudo o que é **domínio e
cálculo**, sem LLM. Consumida por `gymbot-agent` e `gymbot-reports` por tag git.

> O princípio do projeto mora aqui: números (progressão de carga, 1RM, volume, recordes, próxima execução
> de um agendamento) são funções puras e testadas; o LLM só interpreta e narra.

## Módulos

| Módulo | Faz |
|---|---|
| `models` | Pydantic: séries, registros, notas, perfil, plano semanal |
| `catalog` + `exercises.yaml` | 46 exercícios com aliases; resolve "Tríceps  Pulley!" → `triceps_pushdown`; desconhecido vira `custom:<slug>` |
| `calc`, `progression`, `stats` | 1RM (Epley), dupla progressão, estagnação/regressão, evolução e tendência |
| `workout`, `insights`, `reports` | Pré-treino, evolução e os 3 relatórios agendados (dados prontos para narrar) |
| `schedule`, `scheduler` | `Recurrence` → cron do EventBridge, descrição e próxima execução; gateway do Scheduler (AWS e memória) |
| `repository`, `memory`, `table` | Acesso ao DynamoDB single-table, a mesma interface em memória e a definição da tabela |
| `telegram`, `dedup`, `config` | Cliente mínimo da Bot API, dedup por `update_id`, segredos/parâmetros com cache |
| `observability` | Logs JSON, métricas EMF e o catálogo de nomes de métricas |

## Desenvolvimento

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q   # 164 testes
```

O `Repository` tem **testes de contrato**: o mesmo conjunto roda no DynamoDB (`moto`) e no
`InMemoryRepository`, então as duas implementações não divergem.

## Versionamento

Cada mudança publicada ganha uma tag (`v0.6.0`...); os consumidores fixam a tag em
`[tool.uv.sources]`. Mudou o core? Tag nova, depois `uv lock` nos consumidores.
