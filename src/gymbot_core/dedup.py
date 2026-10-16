"""Dedup de updates do Telegram: PutItem condicional com TTL (ver specs/dados.md, A8)."""

import time
from typing import Any

from botocore.exceptions import ClientError

DEDUP_TTL_SECONDS = 24 * 3600


def _key(update_id: int) -> dict[str, str]:
    return {"PK": f"UPDATE#{update_id}", "SK": "UPDATE"}


def claim_update(table: Any, update_id: int, *, now: float | None = None) -> bool:
    """True se este update ainda nao foi visto (e o reserva); False se for reentrega."""
    ts = int(now if now is not None else time.time())
    try:
        table.put_item(
            Item={**_key(update_id), "ttl": ts + DEDUP_TTL_SECONDS},
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return True


def release_update(table: Any, update_id: int) -> None:
    """Desfaz a reserva, para o Telegram poder reentregar se o enfileiramento falhou."""
    table.delete_item(Key=_key(update_id))
