from dataclasses import dataclass

from press.history import PrintFacts
from press.positions import front_position, matches_front_impression


@dataclass(frozen=True)
class Completion:
    category: str
    entry: dict

    @property
    def complete(self):
        return self.category == "complete"


def _repair_provenance(order):
    return {
        "order_id": order.order_id,
        "impression_id": order.impression_id,
        "readings": [list(point) for point in order.readings],
        "directions": list(order.directions),
    }


def check_sheet_completion(facts: PrintFacts, repair_order=None, repair_prints=()) -> Completion:
    sheet = facts.sheet
    proof = facts.proof
    layout = proof.layout
    entry = {"sheet_id": sheet.sheet_id, "proof_id": proof.proof_id, "edition_id": proof.edition_id}
    if repair_order is not None and repair_order.status == "unsolvable":
        return Completion("unsolvable", {**entry, "reason": "repair_unsolvable",
                                         "repair": _repair_provenance(repair_order)})
    impressions = facts.impressions
    expected_faces = ("front", "back") if layout.sides == "double" else ("front",)
    if tuple(item.face for item in impressions) != expected_faces:
        return Completion("unfinished", {**entry, "reason": "missing_impression"})
    if any(item.sheet_id != sheet.sheet_id or item.proof_id != sheet.proof_id for item in impressions):
        return Completion("unfinished", {**entry, "reason": "impression_origin_mismatch"})
    front = impressions[0]
    if front.position != front_position(layout, front.command) or front.front_impression_id is not None:
        return Completion("unfinished", {**entry, "reason": "invalid_front_position"})
    if layout.sides == "double":
        back = impressions[1]
        if back.front_impression_id != front.impression_id or not matches_front_impression(front.position, back.position):
            return Completion("unfinished", {**entry, "reason": "back_misaligned"})
    if repair_order is not None and repair_order.status == "open":
        planned = {action["action_no"] for action in repair_order.actions}
        done = {item.action_no for item in repair_prints if item.order_id == repair_order.order_id}
        if planned - done:
            return Completion("unfinished", {
                **entry,
                "reason": "repair_pending",
                "repair": {
                    **_repair_provenance(repair_order),
                    "completed_actions": sorted(planned & done),
                    "pending_actions": sorted(planned - done),
                },
            })
    entry = {**entry, "impressions": [item.to_data() for item in impressions]}
    if repair_prints:
        entry["repairs"] = [item.to_data() for item in repair_prints]
    return Completion("complete", entry)
