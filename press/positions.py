from plate.geometry import FaceMap
from proof.layout import project_back, project_front


PressPosition = FaceMap


def front_position(layout, command) -> PressPosition | None:
    return project_front(layout, command)


def back_position(layout, direction, command) -> PressPosition | None:
    return project_back(layout, direction, command)


def matches_front_impression(front: PressPosition, back: PressPosition | None) -> bool:
    return back is not None and back == front
