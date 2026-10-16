"""Acesso ao DynamoDB para perfil, sessoes, registros, notas e plano (specs/dados.md, A1-A8).

Todo metodo recebe o ``user_id`` explicitamente e monta a chave a partir dele: nao ha como ler
ou gravar o item de outro usuario sem passar o id dele. ``Repository`` e o contrato; ha duas
implementacoes (``TrainingRepository`` no DynamoDB e ``InMemoryRepository`` para evals/testes)
verificadas pelos mesmos testes de contrato.
"""

import json
from decimal import Decimal
from typing import Any, Protocol

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from gymbot_core.models import ExerciseLog, Note, Plan, UserProfile
from gymbot_core.table import GSI1_NAME


class Repository(Protocol):
    def get_profile(self, user_id: int) -> UserProfile | None: ...
    def create_profile(self, profile: UserProfile) -> bool: ...
    def ensure_session(self, user_id: int, date: str) -> None: ...
    def put_log(self, user_id: int, log: ExerciseLog) -> None: ...
    def get_log(self, user_id: int, ref: str) -> ExerciseLog | None: ...
    def last_logs(
        self,
        user_id: int,
        exercise_id: str,
        *,
        limit: int = 5,
        exclude_log_id: str | None = None,
        since: str | None = None,
    ) -> list[ExerciseLog]: ...
    def recent_logs(self, user_id: int, limit: int = 5) -> list[ExerciseLog]: ...
    def logs_between(self, user_id: int, start: str, end: str) -> list[ExerciseLog]: ...
    def add_note(self, user_id: int, note: Note) -> None: ...
    def notes_between(self, user_id: int, start: str, end: str) -> list[Note]: ...
    def get_plan(self, user_id: int) -> Plan | None: ...
    def put_plan(self, user_id: int, plan: Plan) -> None: ...


def _to_ddb(model_dump: dict[str, Any]) -> dict[str, Any]:
    """boto3 nao aceita float: converte via JSON para Decimal e descarta campos None."""
    cleaned = {k: v for k, v in model_dump.items() if v is not None}
    return json.loads(json.dumps(cleaned, default=str), parse_float=Decimal)  # type: ignore[no-any-return]


def _user_pk(user_id: int) -> str:
    return f"USER#{user_id}"


class TrainingRepository:
    def __init__(self, table: Any) -> None:
        self._table = table

    def _paginate(self, **query: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            page = self._table.query(**query)
            items.extend(page["Items"])
            if "LastEvaluatedKey" not in page:
                return items
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    # -- perfil (A1) ---------------------------------------------------------------------
    def get_profile(self, user_id: int) -> UserProfile | None:
        item = self._table.get_item(Key={"PK": _user_pk(user_id), "SK": "PROFILE"}).get("Item")
        return UserProfile.model_validate(item) if item else None

    def create_profile(self, profile: UserProfile) -> bool:
        """True se criou; False se o usuario ja existia (``/start`` repetido nao reseta nada)."""
        item = {
            "PK": _user_pk(profile.user_id),
            "SK": "PROFILE",
            **_to_ddb(profile.model_dump(mode="json")),
        }
        try:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

    # -- sessao do dia -------------------------------------------------------------------
    def ensure_session(self, user_id: int, date: str) -> None:
        try:
            self._table.put_item(
                Item={"PK": _user_pk(user_id), "SK": f"SESSION#{date}", "date": date},
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    # -- registros de exercicio ----------------------------------------------------------
    def put_log(self, user_id: int, log: ExerciseLog) -> None:
        """Idempotente: o mesmo ``log_id`` regrava o mesmo item (retry nao duplica)."""
        item = {
            "PK": _user_pk(user_id),
            "SK": f"LOG#{log.ref}",
            "GSI1PK": f"{_user_pk(user_id)}#EX#{log.exercise_id}",
            "GSI1SK": log.ref,
            **_to_ddb(log.model_dump(mode="json")),
        }
        self._table.put_item(Item=item)

    def get_log(self, user_id: int, ref: str) -> ExerciseLog | None:
        """Busca por ``ref`` ('<data>#<log_id>'); registro apagado (soft delete) e None."""
        item = self._table.get_item(Key={"PK": _user_pk(user_id), "SK": f"LOG#{ref}"}).get("Item")
        if not item:
            return None
        log = ExerciseLog.model_validate(item)
        return None if log.deleted_at else log

    def last_logs(
        self,
        user_id: int,
        exercise_id: str,
        *,
        limit: int = 5,
        exclude_log_id: str | None = None,
        since: str | None = None,
    ) -> list[ExerciseLog]:
        """Ultimos registros do exercicio, do mais novo para o mais antigo (A5)."""
        condition = Key("GSI1PK").eq(f"{_user_pk(user_id)}#EX#{exercise_id}")
        if since:
            condition = condition & Key("GSI1SK").gte(since)
        found: list[ExerciseLog] = []
        kwargs: dict[str, Any] = {
            "IndexName": GSI1_NAME,
            "KeyConditionExpression": condition,
            "FilterExpression": Attr("deleted_at").not_exists(),
            "ScanIndexForward": False,
        }
        while len(found) < limit:
            page = self._table.query(**kwargs)
            for item in page["Items"]:
                log = ExerciseLog.model_validate(item)
                if log.log_id != exclude_log_id:
                    found.append(log)
                    if len(found) == limit:
                        break
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return found

    def recent_logs(self, user_id: int, limit: int = 5) -> list[ExerciseLog]:
        """Registros mais recentes de qualquer exercicio, do mais novo para o mais antigo."""
        found: list[ExerciseLog] = []
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(_user_pk(user_id))
            & Key("SK").begins_with("LOG#"),
            "FilterExpression": Attr("deleted_at").not_exists(),
            "ScanIndexForward": False,
        }
        while len(found) < limit:
            page = self._table.query(**kwargs)
            found.extend(ExerciseLog.model_validate(item) for item in page["Items"])
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return found[:limit]

    def logs_between(self, user_id: int, start: str, end: str) -> list[ExerciseLog]:
        """Registros entre duas datas locais, inclusive, do mais antigo ao mais novo (A4)."""
        items = self._paginate(
            KeyConditionExpression=Key("PK").eq(_user_pk(user_id))
            & Key("SK").between(f"LOG#{start}", f"LOG#{end}~"),
            FilterExpression=Attr("deleted_at").not_exists(),
        )
        return [ExerciseLog.model_validate(item) for item in items]

    # -- notas de contexto ---------------------------------------------------------------
    def add_note(self, user_id: int, note: Note) -> None:
        item = {
            "PK": _user_pk(user_id),
            "SK": f"NOTE#{note.date}#{note.note_id}",
            **_to_ddb(note.model_dump(mode="json")),
        }
        self._table.put_item(Item=item)

    def notes_between(self, user_id: int, start: str, end: str) -> list[Note]:
        """Notas entre duas datas locais, inclusive (A6)."""
        items = self._paginate(
            KeyConditionExpression=Key("PK").eq(_user_pk(user_id))
            & Key("SK").between(f"NOTE#{start}", f"NOTE#{end}~")
        )
        return [Note.model_validate(item) for item in items]

    # -- plano semanal (A2) --------------------------------------------------------------
    def get_plan(self, user_id: int) -> Plan | None:
        item = self._table.get_item(Key={"PK": _user_pk(user_id), "SK": "PLAN#CURRENT"}).get("Item")
        return Plan.model_validate(item) if item else None

    def put_plan(self, user_id: int, plan: Plan) -> None:
        """Grava a versao (historico) e atualiza o ponteiro ``PLAN#CURRENT``. Idempotente."""
        body = _to_ddb(plan.model_dump(mode="json"))
        self._table.put_item(Item={"PK": _user_pk(user_id), "SK": f"PLAN#{plan.version}", **body})
        self._table.put_item(Item={"PK": _user_pk(user_id), "SK": "PLAN#CURRENT", **body})
