"""Modelos do update do Telegram e cliente minimo da Bot API (so stdlib + pydantic)."""

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

API_BASE = "https://api.telegram.org"

# post(url, payload) -> resposta JSON decodificada. Injetavel para testes.
PostFn = Callable[[str, dict[str, Any]], dict[str, Any]]


class TelegramUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    first_name: str | None = None
    language_code: str | None = None


class TelegramChat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int


class TelegramMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message_id: int
    chat: TelegramChat
    from_user: TelegramUser | None = Field(default=None, alias="from")
    text: str | None = None


class Update(BaseModel):
    """Update do webhook. Campos nao usados (editadas, callbacks, ...) sao ignorados."""

    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessage | None = None


def _urllib_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result: dict[str, Any] = json.loads(response.read())
        return result
    except urllib.error.HTTPError as error:
        # Erros 4xx/5xx do Telegram trazem JSON com a descricao ({"ok": false, ...}), mas o
        # urlopen levanta antes de lermos o corpo. Devolvemos esse JSON para `_call` explicar.
        try:
            body = json.loads(error.read())
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        body.setdefault("description", str(error.reason))
        return {**body, "ok": False, "error_code": error.code}


class TelegramError(RuntimeError):
    """Resposta de erro da Bot API. A mensagem nunca contem a URL (que leva o token)."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code

    @property
    def transient(self) -> bool:
        """429 (rate limit) e 5xx valem uma nova tentativa; o resto (400, 401, 403) nao."""
        return self.error_code == 429 or (self.error_code or 0) >= 500


class TelegramClient:
    def __init__(self, token: str, post: PostFn = _urllib_post) -> None:
        self._token = token
        self._post = post

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._post(f"{API_BASE}/bot{self._token}/{method}", payload)
        if not result.get("ok"):
            # Nunca inclui a URL (contem o token) na mensagem de erro.
            raise TelegramError(
                f"{method} falhou: {result.get('description', 'sem descricao')}",
                error_code=result.get("error_code"),
            )
        return result

    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text})

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        self._call("sendChatAction", {"chat_id": chat_id, "action": action})

    def set_webhook(self, url: str, secret_token: str) -> None:
        self._call(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": ["message"],
                "drop_pending_updates": True,
            },
        )
