from dataclasses import dataclass

from paper.observations import read_sheet_directions
from press.candidates import evaluate_back_request
from press.history import Impression, append_impression, read_print_facts
from press.positions import front_position
from proof.layout import BACK_OFFSETS, FRONT_OFFSETS
from workshop import BusinessError, transaction


@dataclass(frozen=True)
class ImprintResult:
    impression: Impression

    def to_data(self):
        return {"status": "printed", **self.impression.to_data()}


def imprint_sheet(db, sheet_id, face, command):
    if face not in ("front", "back"):
        raise BusinessError("invalid_face", "Face must be front or back.", 422)
    offsets = FRONT_OFFSETS if face == "front" else BACK_OFFSETS
    if not isinstance(command, str) or command not in offsets:
        raise BusinessError("invalid_command", "Unknown command for this face.", 422)

    with transaction(db, write=True):
        facts = read_print_facts(db, sheet_id)
        layout = facts.proof.layout
        by_face = {item.face: item for item in facts.impressions}
        if face in by_face:
            raise BusinessError("already_printed", "This face already has an impression.", 409)
        front_id = None
        if face == "front":
            position = front_position(layout, command)
            if position is None:
                raise BusinessError("incompatible", "The front placement falls outside the sheet.", 409)
        else:
            front = by_face.get("front")
            if layout.sides != "double" or front is None:
                raise BusinessError("invalid_sequence", "Back printing requires a printed front on a double-sided sheet.", 409)
            directions = read_sheet_directions(db, sheet_id, layout)
            eligibility = evaluate_back_request(layout, front.position, directions, command)
            if eligibility.status == "needs_orientation":
                raise BusinessError("needs_orientation", "No common command. Take a paper reading and retry.", 409)
            if eligibility.status == "incompatible":
                raise BusinessError("incompatible", "The requested placement cannot be used on this paper.", 409)
            position = eligibility.position
            front_id = front.impression_id
        impression = append_impression(db, facts.sheet, face, command, position, front_id)
    return ImprintResult(impression)
