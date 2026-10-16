"""Repositorio em memoria com o mesmo contrato do DynamoDB (``Repository``).

Serve aos evals (que chamam o Bedrock de verdade e nao podem usar moto, que interceptaria a AWS
inteira) e a testes rapidos. Ordenacao e filtros imitam as chaves do DynamoDB.
"""

from gymbot_core.models import ExerciseLog, Note, Plan, UserProfile


class InMemoryRepository:
    def __init__(self) -> None:
        self._profiles: dict[int, UserProfile] = {}
        self._logs: dict[tuple[int, str], ExerciseLog] = {}  # (user, ref)
        self._notes: dict[tuple[int, str], Note] = {}  # (user, "<data>#<note_id>")
        self._plans: dict[int, Plan] = {}
        self._plan_versions: dict[tuple[int, str], Plan] = {}
        self.sessions: set[tuple[int, str]] = set()

    def get_profile(self, user_id: int) -> UserProfile | None:
        return self._profiles.get(user_id)

    def create_profile(self, profile: UserProfile) -> bool:
        if profile.user_id in self._profiles:
            return False
        self._profiles[profile.user_id] = profile
        return True

    def ensure_session(self, user_id: int, date: str) -> None:
        self.sessions.add((user_id, date))

    def put_log(self, user_id: int, log: ExerciseLog) -> None:
        self._logs[(user_id, log.ref)] = log.model_copy(deep=True)

    def get_log(self, user_id: int, ref: str) -> ExerciseLog | None:
        log = self._logs.get((user_id, ref))
        return None if log is None or log.deleted_at else log.model_copy(deep=True)

    def _live(self, user_id: int) -> list[ExerciseLog]:
        mine = [(ref, log) for (uid, ref), log in self._logs.items() if uid == user_id]
        return [log for _, log in sorted(mine, key=lambda pair: pair[0]) if not log.deleted_at]

    def last_logs(
        self,
        user_id: int,
        exercise_id: str,
        *,
        limit: int = 5,
        exclude_log_id: str | None = None,
        since: str | None = None,
    ) -> list[ExerciseLog]:
        matches = [
            log
            for log in self._live(user_id)
            if log.exercise_id == exercise_id
            and log.log_id != exclude_log_id
            and (since is None or log.ref >= since)
        ]
        return [log.model_copy(deep=True) for log in reversed(matches)][:limit]

    def recent_logs(self, user_id: int, limit: int = 5) -> list[ExerciseLog]:
        return [log.model_copy(deep=True) for log in reversed(self._live(user_id))][:limit]

    def logs_between(self, user_id: int, start: str, end: str) -> list[ExerciseLog]:
        return [
            log.model_copy(deep=True) for log in self._live(user_id) if start <= log.date <= end
        ]

    def add_note(self, user_id: int, note: Note) -> None:
        self._notes[(user_id, f"{note.date}#{note.note_id}")] = note

    def notes_between(self, user_id: int, start: str, end: str) -> list[Note]:
        mine = sorted((key, n) for (uid, key), n in self._notes.items() if uid == user_id)
        return [n for _, n in mine if start <= n.date <= end]

    def get_plan(self, user_id: int) -> Plan | None:
        plan = self._plans.get(user_id)
        return plan.model_copy(deep=True) if plan else None

    def put_plan(self, user_id: int, plan: Plan) -> None:
        self._plan_versions[(user_id, plan.version)] = plan.model_copy(deep=True)
        self._plans[user_id] = plan.model_copy(deep=True)
