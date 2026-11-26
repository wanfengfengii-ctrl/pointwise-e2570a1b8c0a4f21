from dataclasses import dataclass
from enum import StrEnum

from plate.geometry import FaceMap, SheetSize, is_within_sheet, plate_spec_data, read_plate_spec


class LoadingDirection(StrEnum):
    LEFT = "left"
    RIGHT = "right"


FRONT_OFFSETS = {"P": 0, "S": 1, "Q": 2}
BACK_OFFSETS = {"P": 0, "Q": 2, "R": -1, "S": 1}


@dataclass(frozen=True)
class ProofLayout:
    size: SheetSize
    sides: str
    front: FaceMap
    back: FaceMap | None

    def to_spec(self):
        faces = {"front": self.front}
        if self.back is not None:
            faces["back"] = self.back
        return plate_spec_data(self.size, self.sides, faces)


def build_proof_layout(spec) -> ProofLayout:
    size, sides, faces = read_plate_spec(spec)
    return ProofLayout(size, sides, faces["front"], faces.get("back"))


def _position(size, grid, offset, *, reflected=False):
    translated = tuple((x + offset, y) for x, y in grid)
    if not all(is_within_sheet(size, point) for point in translated):
        return None
    if reflected:
        return tuple(sorted((size.width - 1 - x, y) for x, y in translated))
    return translated


def project_front(layout: ProofLayout, command: str) -> FaceMap | None:
    offset = FRONT_OFFSETS.get(command)
    if offset is None:
        return None
    return _position(layout.size, layout.front, offset)


def project_back(layout: ProofLayout, direction: LoadingDirection, command: str) -> FaceMap | None:
    offset = BACK_OFFSETS.get(command)
    if offset is None or layout.back is None:
        return None
    return _position(layout.size, layout.back, offset, reflected=direction == LoadingDirection.RIGHT)
