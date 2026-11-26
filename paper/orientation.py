from plate.geometry import GridPoint, is_within_sheet
from proof.layout import LoadingDirection, ProofLayout
from workshop import BusinessError


def matching_directions(layout: ProofLayout, probe: str, point: GridPoint):
    if probe not in ("edge", "top") or not is_within_sheet(layout.size, point):
        raise BusinessError("invalid_observation", "Unknown probe or reading outside the sheet.", 422)
    width = layout.size.width
    left_x = 0 if probe == "edge" else width // 2
    expected = {LoadingDirection.LEFT: (left_x, 0), LoadingDirection.RIGHT: (width - 1 - left_x, 0)}
    return {direction for direction, expected_point in expected.items() if expected_point == point}


def remaining_directions(layout, readings):
    possible = set(LoadingDirection)
    for probe, point in readings:
        possible.intersection_update(matching_directions(layout, probe, point))
        if not possible:
            raise BusinessError("conflicting_observation", "The reading excludes every remaining direction.", 409)
    return tuple(direction for direction in LoadingDirection if direction in possible)
