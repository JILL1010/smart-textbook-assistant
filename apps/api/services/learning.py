import hashlib
import json


def quiz_token(raw: str | None) -> str | None:
    if not raw:
        return None
    normalized = json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode()).hexdigest()


def serialize_attempt(attempt) -> dict:
    return {
        "id": attempt.id, "generation_revision": attempt.generation_revision,
        "quiz_token": attempt.quiz_token, "answers": json.loads(attempt.answers),
        "correct": attempt.correct, "total": attempt.total,
        "created_at": attempt.created_at.isoformat(),
    }
