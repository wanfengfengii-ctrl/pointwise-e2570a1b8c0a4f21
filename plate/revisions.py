import json
from dataclasses import dataclass
from uuid import uuid4

from plate.drafts import read_draft
from plate.geometry import FaceMap, SheetSize, plate_spec_data, read_plate_spec
from workshop import BusinessError, canonical_json, identifier, transaction


@dataclass(frozen=True)
class FrozenEdition:
    edition_id: str
    draft_id: str | None
    size: SheetSize
    sides: str
    faces: dict[str, FaceMap]

    def to_data(self):
        return {
            "edition_id": self.edition_id,
            "draft_id": self.draft_id,
            "spec": plate_spec_data(self.size, self.sides, self.faces),
        }


def freeze_edition(db, *, draft_id=None, spec=None):
    if (draft_id is None) == (spec is None):
        raise BusinessError("invalid_request", "Supply a draft_id or a direct spec.")
    with transaction(db, write=True):
        if draft_id is not None:
            spec = read_draft(db, identifier(draft_id, "draft_id")).spec
        size, sides, faces = read_plate_spec(spec)
        edition = FrozenEdition(uuid4().hex, draft_id, size, sides, faces)
        db.execute(
            "INSERT INTO editions(edition_id, draft_id, spec) VALUES (?, ?, ?)",
            (edition.edition_id, draft_id, canonical_json(edition.to_data()["spec"])),
        )
    return edition


def read_frozen_edition(db, edition_id):
    row = db.execute(
        "SELECT draft_id, spec FROM editions WHERE edition_id = ?", (edition_id,)
    ).fetchone()
    if row is None:
        raise BusinessError("edition_not_found", "Frozen edition does not exist.", 404)
    size, sides, faces = read_plate_spec(json.loads(row["spec"]))
    return FrozenEdition(edition_id, row["draft_id"], size, sides, faces)
