from dataclasses import dataclass

from press.positions import PressPosition, back_position, matches_front_impression
from proof.layout import BACK_OFFSETS


@dataclass(frozen=True)
class BackEligibility:
    status: str
    position: PressPosition | None = None


def evaluate_back_request(layout, actual_front, directions, requested):
    placements = []
    for direction in directions:
        eligible = {}
        for command in BACK_OFFSETS:
            position = back_position(layout, direction, command)
            if matches_front_impression(actual_front, position):
                eligible[command] = position
        placements.append(eligible)

    if not any(placements):
        return BackEligibility("incompatible")
    common = set(placements[0]).intersection(*placements[1:])
    if requested in common:
        return BackEligibility("printed", placements[0][requested])
    if not common:
        return BackEligibility("needs_orientation")
    return BackEligibility("incompatible")
