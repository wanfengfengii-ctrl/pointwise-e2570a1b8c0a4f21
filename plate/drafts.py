import json
from dataclasses import dataclass

from workshop import BusinessError, canonical_json, identifier, transaction


@dataclass(frozen=True)
class Draft:
    draft_id: str
    spec: dict

    def to_data(self):
        return {"draft_id": self.draft_id, "spec": self.spec}


def _draft_payload(draft_id, spec):
    identifier(draft_id, "draft_id")
    if not isinstance(spec, dict):
        raise BusinessError("invalid_request", "Draft spec must be an object.")
    return canonical_json(spec)


def save_draft(db, draft_id, spec):
    payload = _draft_payload(draft_id, spec)
    with transaction(db, write=True):
        db.execute(
            """INSERT INTO drafts(draft_id, spec) VALUES (?, ?)
               ON CONFLICT(draft_id) DO UPDATE SET spec = excluded.spec""",
            (draft_id, payload),
        )
    return Draft(draft_id, spec)


def read_draft(db, draft_id):
    row = db.execute("SELECT spec FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
    if row is None:
        raise BusinessError("draft_not_found", "Draft does not exist.", 404)
    return Draft(draft_id, json.loads(row["spec"]))


def insert_missing_draft(db, draft_id, spec):
    cursor = db.execute(
        "INSERT INTO drafts(draft_id, spec) VALUES (?, ?) ON CONFLICT(draft_id) DO NOTHING",
        (draft_id, _draft_payload(draft_id, spec)),
    )
    return cursor.rowcount == 1
