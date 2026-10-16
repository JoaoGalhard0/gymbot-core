"""Logs JSON e metricas EMF (CloudWatch) das Lambdas do GymBot. Ver specs/arquitetura.md.

Metricas usam o namespace ``GymBot`` e a dimensao ``service`` (gymbot-ingress, gymbot-agent,
gymbot-reports). Saem como linhas EMF no stdout, sem chamada de API nem permissao extra de IAM.
Nomes ficam em ``Metric`` e sao os mesmos usados pelo dashboard e pelos alarmes no gymbot-infra.

Privacidade: nunca registre o texto das mensagens do usuario; use ids (user_id, update_id).
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager

from aws_lambda_powertools import Logger
from aws_lambda_powertools.metrics import MetricUnit, single_metric

NAMESPACE = "GymBot"

INGRESS = "gymbot-ingress"
AGENT = "gymbot-agent"
REPORTS = "gymbot-reports"

COUNT = "Count"
MILLISECONDS = "Milliseconds"


class Metric:
    """Catalogo de metricas (nome -> significado). Mudou um nome? Ajuste o dashboard/alarmes."""

    # ingress
    UPDATES_ACCEPTED = "UpdatesAccepted"  # enfileirado para o agente
    UPDATES_DENIED = "UpdatesDenied"  # usuario fora da allowlist
    UPDATES_DUPLICATE = "UpdatesDuplicate"  # reentrega do Telegram descartada
    UPDATES_REJECTED = "UpdatesRejected"  # secret do webhook invalido (sinal de abuso)
    ENQUEUE_FAILED = "EnqueueFailed"
    # agent
    MESSAGES_PROCESSED = "MessagesProcessed"
    MESSAGES_FAILED = "MessagesFailed"
    TOOL_CALLS = "ToolCalls"  # dimensao Tool
    LLM_LATENCY_MS = "LLMLatencyMs"  # tempo de agent.invoke (LLM + tools) por mensagem
    INPUT_TOKENS = "InputTokens"
    OUTPUT_TOKENS = "OutputTokens"
    AGENT_FALLBACKS = "AgentFallbacks"  # limite de iteracoes estourado
    SCHEDULES_CHANGED = "SchedulesChanged"  # dimensao Action: created|updated|deleted
    SCHEDULER_ERRORS = "SchedulerErrors"
    # reports
    REPORTS_SENT = "ReportsSent"
    REPORTS_FAILED = "ReportsFailed"
    REPORTS_FALLBACK = "ReportsFallback"  # narracao do LLM falhou; texto deterministico enviado
    REPORTS_ORPHANED = "ReportsOrphaned"
    REPORTS_SKIPPED = "ReportsSkipped"  # usuario sem perfil


def get_logger(service: str) -> Logger:
    """Logger JSON estruturado (campos extras viram chaves do JSON)."""
    return Logger(service=service)


def record_metric(
    service: str, name: str, value: float = 1, unit: str = COUNT, **dimensions: str
) -> None:
    """Emite uma metrica EMF imediatamente (uma linha no stdout)."""
    with single_metric(
        name=name, unit=MetricUnit(unit), value=value, namespace=NAMESPACE
    ) as metric:
        metric.add_dimension(name="service", value=service)
        for key, val in dimensions.items():
            metric.add_dimension(name=key, value=val)


@contextmanager
def timed(service: str, name: str, **dimensions: str) -> Iterator[None]:
    """Mede o bloco em ms e emite a metrica mesmo se ele levantar excecao."""
    start = time.perf_counter()
    try:
        yield
    finally:
        record_metric(
            service,
            name,
            (time.perf_counter() - start) * 1000,
            MILLISECONDS,
            **dimensions,
        )
