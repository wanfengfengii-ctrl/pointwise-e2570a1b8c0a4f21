from dataclasses import dataclass

from proof.loading import read_loaded_proof
from workshop import BusinessError, transaction


@dataclass(frozen=True)
class RegisteredSheet:
    sheet_id: str
    proof_id: str

    def to_data(self):
        return {"sheet_id": self.sheet_id, "proof_id": self.proof_id}


def register_sheet(db, sheet_id, proof_id):
    with transaction(db, write=True):
        read_loaded_proof(db, proof_id)
        cursor = db.execute(
            """INSERT INTO sheets(sheet_id, proof_id) VALUES (?, ?)
               ON CONFLICT(sheet_id) DO NOTHING""",
            (sheet_id, proof_id),
        )
        if cursor.rowcount != 1:
            raise BusinessError("sheet_exists", "This paper number is already registered.", 409)
    return RegisteredSheet(sheet_id, proof_id)


def read_sheet(db, sheet_id):
    row = db.execute("SELECT proof_id FROM sheets WHERE sheet_id = ?", (sheet_id,)).fetchone()
    if row is None:
        raise BusinessError("sheet_not_found", "Paper is not registered.", 404)
    return RegisteredSheet(sheet_id, row["proof_id"])
