import json
from pathlib import Path

from plate.drafts import insert_missing_draft
from plate.geometry import read_plate_spec
from workshop import transaction


_SEEDS = Path(__file__).resolve().parents[1] / "examples" / "drafts.json"


def seed_missing_drafts(db):
    seeds = json.loads(_SEEDS.read_text(encoding="utf-8"))
    inserted = []
    with transaction(db, write=True):
        for draft_id, spec in sorted(seeds.items()):
            read_plate_spec(spec)
            if insert_missing_draft(db, draft_id, spec):
                inserted.append(draft_id)
    return inserted
