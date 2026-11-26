import json
from dataclasses import dataclass

from paper.intake import RegisteredSheet, read_sheet
from press.positions import PressPosition
from proof.loading import LoadedProof, read_loaded_proof
from workshop import canonical_json


@dataclass(frozen=True)
class Impression:
    impression_id: int
    sheet_id: str
    proof_id: str
    face: str
    command: str
    position: PressPosition
    front_impression_id: int | None

    def to_data(self):
        return {
            "impression_id": self.impression_id,
            "sheet_id": self.sheet_id,
            "proof_id": self.proof_id,
            "face": self.face,
            "command": self.command,
            "position": [list(point) for point in self.position],
            "front_impression_id": self.front_impression_id,
        }


@dataclass(frozen=True)
class PrintFacts:
    sheet: RegisteredSheet
    proof: LoadedProof
    impressions: tuple[Impression, ...]


def append_impression(db, sheet, face, command, position, front_impression_id=None):
    cursor = db.execute(
        """INSERT INTO impressions(sheet_id, proof_id, face, command, position, front_impression_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sheet.sheet_id, sheet.proof_id, face, command, canonical_json(position), front_impression_id),
    )
    return Impression(cursor.lastrowid, sheet.sheet_id, sheet.proof_id, face, command, position,
                      front_impression_id)


def read_sheet_impressions(db, sheet_id):
    rows = db.execute(
        """SELECT impression_id, proof_id, face, command, position, front_impression_id
           FROM impressions WHERE sheet_id = ? ORDER BY impression_id""",
        (sheet_id,),
    )
    return tuple(
        Impression(row["impression_id"], sheet_id, row["proof_id"], row["face"], row["command"],
                   tuple(tuple(point) for point in json.loads(row["position"])), row["front_impression_id"])
        for row in rows
    )


def read_print_facts(db, sheet_id):
    sheet = read_sheet(db, sheet_id)
    return PrintFacts(sheet, read_loaded_proof(db, sheet.proof_id), read_sheet_impressions(db, sheet_id))
