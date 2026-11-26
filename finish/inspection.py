from dataclasses import dataclass

from press.history import PrintFacts
from press.positions import front_position, matches_front_impression


@dataclass(frozen=True)
class Completion:
    complete: bool
    entry: dict


def check_sheet_completion(facts: PrintFacts) -> Completion:
    sheet = facts.sheet
    proof = facts.proof
    layout = proof.layout
    entry = {"sheet_id": sheet.sheet_id, "proof_id": proof.proof_id, "edition_id": proof.edition_id}
    impressions = facts.impressions
    expected_faces = ("front", "back") if layout.sides == "double" else ("front",)
    if tuple(item.face for item in impressions) != expected_faces:
        return Completion(False, {**entry, "reason": "missing_impression"})
    if any(item.sheet_id != sheet.sheet_id or item.proof_id != sheet.proof_id for item in impressions):
        return Completion(False, {**entry, "reason": "impression_origin_mismatch"})
    front = impressions[0]
    if front.position != front_position(layout, front.command) or front.front_impression_id is not None:
        return Completion(False, {**entry, "reason": "invalid_front_position"})
    if layout.sides == "double":
        back = impressions[1]
        if back.front_impression_id != front.impression_id or not matches_front_impression(front.position, back.position):
            return Completion(False, {**entry, "reason": "back_misaligned"})
    return Completion(True, {**entry, "impressions": [item.to_data() for item in impressions]})
