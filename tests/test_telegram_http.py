"""M3: erros 4xx/5xx da Bot API (servidor HTTP local): mantem a descricao e nao vaza o token."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from gymbot_core.telegram import TelegramClient, TelegramError, _urllib_post


@pytest.fixture
def telegram_server() -> Iterator[tuple[str, dict[str, Any]]]:
    """Servidor que responde o que o teste mandar em ``reply`` (status, corpo, content-type)."""
    reply: dict[str, Any] = {"status": 200, "body": b'{"ok": true}', "type": "application/json"}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(
                int(self.headers.get("Content-Length", 0))
            )  # consome o corpo da requisicao
            self.send_response(reply["status"])
            self.send_header("Content-Type", reply["type"])
            self.send_header("Content-Length", str(len(reply["body"])))
            self.end_headers()
            self.wfile.write(reply["body"])

        def log_message(self, *args: Any) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/botSEGREDO/sendMessage", reply
    server.shutdown()


def _client(url: str) -> TelegramClient:
    return TelegramClient("SEGREDO", lambda _url, payload: _urllib_post(url, payload))


def test_a_400_keeps_the_telegram_description_instead_of_a_bare_http_error(
    telegram_server: tuple[str, dict[str, Any]],
) -> None:
    url, reply = telegram_server
    body = {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
    reply.update(status=400, body=json.dumps(body).encode())
    result = _urllib_post(url, {"chat_id": 1})
    assert result["ok"] is False and result["error_code"] == 400
    assert result["description"] == "Bad Request: chat not found"


def test_client_raises_a_telegram_error_with_description_code_and_no_token(
    telegram_server: tuple[str, dict[str, Any]],
) -> None:
    url, reply = telegram_server
    reply.update(
        status=401, body=b'{"ok": false, "error_code": 401, "description": "Unauthorized"}'
    )
    with pytest.raises(TelegramError) as error:
        _client(url).send_message(1, "oi")
    assert "Unauthorized" in str(error.value) and error.value.error_code == 401
    assert "SEGREDO" not in str(error.value)
    assert error.value.transient is False


def test_a_non_json_gateway_error_still_becomes_a_telegram_error(
    telegram_server: tuple[str, dict[str, Any]],
) -> None:
    url, reply = telegram_server
    reply.update(status=502, body=b"<html>Bad Gateway</html>", type="text/html")
    with pytest.raises(TelegramError) as error:
        _client(url).send_message(1, "oi")
    assert error.value.error_code == 502 and error.value.transient is True
    assert "SEGREDO" not in str(error.value)


def test_rate_limit_is_transient(telegram_server: tuple[str, dict[str, Any]]) -> None:
    url, reply = telegram_server
    body = {
        "ok": False,
        "error_code": 429,
        "description": "Too Many Requests: retry after 3",
        "parameters": {"retry_after": 3},
    }
    reply.update(status=429, body=json.dumps(body).encode())
    with pytest.raises(TelegramError) as error:
        _client(url).send_message(1, "oi")
    assert error.value.transient is True and "retry after 3" in str(error.value)


@pytest.mark.parametrize(
    ("code", "transient"),
    [
        (429, True),
        (500, True),
        (503, True),
        (400, False),
        (401, False),
        (403, False),
        (None, False),
    ],
)
def test_only_rate_limit_and_server_errors_are_transient(code: int | None, transient: bool) -> None:
    assert TelegramError("x", error_code=code).transient is transient


def test_a_successful_response_is_returned_untouched(
    telegram_server: tuple[str, dict[str, Any]],
) -> None:
    url, _ = telegram_server
    assert _urllib_post(url, {"chat_id": 1}) == {"ok": True}
