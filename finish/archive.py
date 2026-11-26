import json
from dataclasses import dataclass
from uuid import uuid4

from workshop import BusinessError, canonical_json


@dataclass(frozen=True)
class AcceptanceReceipt:
    acceptance_id: str
    completed: list[dict]
    unfinished: list[dict]
    unsolvable: list[dict]

    def to_data(self):
        return {
            "acceptance_id": self.acceptance_id,
            "completed_count": len(self.completed),
            "unfinished_count": len(self.unfinished),
            "unsolvable_count": len(self.unsolvable),
            "completed": self.completed,
            "unfinished": self.unfinished,
            "unsolvable": self.unsolvable,
        }


def store_acceptance(db, completed, unfinished, unsolvable):
    receipt = AcceptanceReceipt(uuid4().hex, completed, unfinished, unsolvable)
    db.execute("INSERT INTO acceptances(acceptance_id, receipt) VALUES (?, ?)",
               (receipt.acceptance_id, canonical_json(receipt.to_data())))
    return receipt


def read_receipt(db, acceptance_id):
    row = db.execute("SELECT receipt FROM acceptances WHERE acceptance_id = ?", (acceptance_id,)).fetchone()
    if row is None:
        raise BusinessError("acceptance_not_found", "Acceptance receipt does not exist.", 404)
    data = json.loads(row["receipt"])
    return AcceptanceReceipt(data["acceptance_id"], data["completed"], data["unfinished"],
                             data.get("unsolvable", []))
