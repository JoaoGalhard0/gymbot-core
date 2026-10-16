"""Modelos do update do Telegram e cliente minimo da Bot API (so stdlib + pydantic)."""

import json
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
    with urllib.request.urlopen(request, timeout=10) as response:
        result: dict[str, Any] = json.loads(response.read())
    return result


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, post: PostFn = _urllib_post) -> None:
        self._token = token
        self._post = post

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._post(f"{API_BASE}/bot{self._token}/{method}", payload)
        if not result.get("ok"):
            # Nunca inclui a URL (contem o token) na mensagem de erro.
            raise TelegramError(f"{method} falhou: {result.get('description', 'sem descricao')}")
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
