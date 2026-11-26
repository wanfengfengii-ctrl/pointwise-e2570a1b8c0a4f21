import json
from dataclasses import dataclass

from paper.intake import read_sheet
from paper.orientation import remaining_directions
from plate.geometry import GridPoint
from proof.loading import read_loaded_proof
from workshop import canonical_json, transaction


@dataclass(frozen=True)
class Observation:
    observation_id: int
    sheet_id: str
    probe: str
    point: GridPoint

    def to_data(self):
        return {
            "observation_id": self.observation_id,
            "sheet_id": self.sheet_id,
            "probe": self.probe,
            "point": list(self.point),
        }


def read_observations(db, sheet_id):
    rows = db.execute(
        """SELECT observation_id, probe, point FROM observations
           WHERE sheet_id = ? ORDER BY observation_id""",
        (sheet_id,),
    )
    return [
        Observation(row["observation_id"], sheet_id, row["probe"], tuple(json.loads(row["point"])))
        for row in rows
    ]


def _readings(observations):
    return [(item.probe, item.point) for item in observations]


def read_sheet_directions(db, sheet_id, layout):
    return remaining_directions(layout, _readings(read_observations(db, sheet_id)))


def record_observation(db, sheet_id, probe, point):
    with transaction(db, write=True):
        sheet = read_sheet(db, sheet_id)
        layout = read_loaded_proof(db, sheet.proof_id).layout
        readings = _readings(read_observations(db, sheet_id))
        directions = remaining_directions(layout, [*readings, (probe, point)])
        cursor = db.execute(
            "INSERT INTO observations(sheet_id, probe, point) VALUES (?, ?, ?)",
            (sheet_id, probe, canonical_json(point)),
        )
        observation = Observation(cursor.lastrowid, sheet_id, probe, point)
    return observation, directions
