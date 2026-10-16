import json
from typing import Any

import pytest

from gymbot_core.observability import (
    AGENT,
    MILLISECONDS,
    NAMESPACE,
    Metric,
    get_logger,
    record_metric,
    timed,
)


def _emf(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("{")]
    return [json.loads(line) for line in lines]


def test_record_metric_emits_an_emf_line_with_namespace_service_and_dimensions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    record_metric(AGENT, Metric.TOOL_CALLS, 2, Tool="log_sets")
    [line] = _emf(capsys)
    directive = line["_aws"]["CloudWatchMetrics"][0]
    assert directive["Namespace"] == NAMESPACE == "GymBot"
    assert directive["Metrics"] == [{"Name": "ToolCalls", "Unit": "Count"}]
    assert sorted(directive["Dimensions"][0]) == ["Tool", "service"]
    assert line["service"] == "gymbot-agent" and line["Tool"] == "log_sets"
    assert line["ToolCalls"] == [2.0]


def test_counters_default_to_one(capsys: pytest.CaptureFixture[str]) -> None:
    record_metric(AGENT, Metric.MESSAGES_PROCESSED)
    assert _emf(capsys)[0][Metric.MESSAGES_PROCESSED] == [1.0]


def test_timed_emits_the_elapsed_milliseconds(capsys: pytest.CaptureFixture[str]) -> None:
    with timed(AGENT, Metric.LLM_LATENCY_MS):
        sum(range(1000))
    [line] = _emf(capsys)
    assert line["_aws"]["CloudWatchMetrics"][0]["Metrics"][0]["Unit"] == MILLISECONDS
    assert line[Metric.LLM_LATENCY_MS][0] >= 0


def test_timed_still_emits_when_the_block_fails(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(RuntimeError), timed(AGENT, Metric.LLM_LATENCY_MS):
        raise RuntimeError("bedrock fora do ar")
    assert len(_emf(capsys)) == 1


def test_logger_writes_structured_json_with_the_service_and_extra_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    get_logger("gymbot-test").info("processado %s", "ok", extra={"update_id": 7})
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["service"] == "gymbot-test" and line["update_id"] == 7
    assert line["message"] == "processado ok" and line["level"] == "INFO"


def test_metric_names_are_unique_and_pascal_case() -> None:
    names = [v for k, v in vars(Metric).items() if k.isupper()]
    assert len(names) == len(set(names)) >= 15
    assert all(n[0].isupper() and n.isalnum() for n in names)
