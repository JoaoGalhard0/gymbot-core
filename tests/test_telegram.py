from typing import Any

import pytest

from gymbot_core.telegram import TelegramClient, TelegramError, Update

SAMPLE_UPDATE = {
    "update_id": 987654,
    "message": {
        "message_id": 10,
        "from": {"id": 123, "is_bot": False, "first_name": "Joao", "language_code": "pt-br"},
        "chat": {"id": 123, "type": "private", "first_name": "Joao"},
        "date": 1760000000,
        "text": "supino reto 30kg 4x10",
    },
}


def test_update_parses_real_payload_and_ignores_extra_fields() -> None:
    update = Update.model_validate(SAMPLE_UPDATE)
    assert update.update_id == 987654
    assert update.message is not None
    assert update.message.text == "supino reto 30kg 4x10"
    assert update.message.chat.id == 123
    assert update.message.from_user is not None
    assert update.message.from_user.id == 123


def test_update_without_message_is_valid() -> None:
    update = Update.model_validate({"update_id": 1, "edited_message": {"message_id": 1}})
    assert update.message is None


class FakePost:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((url, payload))
        return self.response


def test_send_message_calls_bot_api() -> None:
    post = FakePost({"ok": True})
    TelegramClient("TOKEN", post).send_message(123, "oi")
    assert post.calls == [
        ("https://api.telegram.org/botTOKEN/sendMessage", {"chat_id": 123, "text": "oi"})
    ]


def test_set_webhook_sends_secret_and_only_messages() -> None:
    post = FakePost({"ok": True})
    TelegramClient("TOKEN", post).set_webhook("https://x.example/hook", "s3cret")
    url, payload = post.calls[0]
    assert url.endswith("/setWebhook")
    assert payload["secret_token"] == "s3cret"
    assert payload["allowed_updates"] == ["message"]


def test_error_does_not_leak_token() -> None:
    post = FakePost({"ok": False, "description": "Unauthorized"})
    with pytest.raises(TelegramError) as error:
        TelegramClient("TOKEN-SECRETO", post).send_message(1, "x")
    assert "TOKEN-SECRETO" not in str(error.value)
    assert "Unauthorized" in str(error.value)
