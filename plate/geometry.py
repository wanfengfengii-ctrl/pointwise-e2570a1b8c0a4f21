from dataclasses import dataclass

from workshop import BusinessError, fields


GridPoint = tuple[int, int]
FaceMap = tuple[GridPoint, ...]


@dataclass(frozen=True)
class SheetSize:
    width: int
    height: int

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in (self.width, self.height)):
            raise BusinessError("invalid_layout", "Sheet dimensions must be positive integers.", 422)


def is_within_sheet(size: SheetSize, point: GridPoint) -> bool:
    x, y = point
    return 0 <= x < size.width and 0 <= y < size.height


def read_grid_point(value, code="invalid_layout") -> GridPoint:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise BusinessError(code, "A grid point must have exactly two coordinates.", 422)
    x, y = value
    if type(x) is not int or type(y) is not int:
        raise BusinessError(code, "Grid coordinates must be integers.", 422)
    return x, y


def validate_face_maps(size: SheetSize, sides: str, faces) -> dict[str, FaceMap]:
    if sides not in ("single", "double"):
        raise BusinessError("invalid_layout", "Sides must be single or double.", 422)
    names = ("front",) if sides == "single" else ("front", "back")
    fields(faces, *names, code="invalid_layout", status=422)
    normalized = {}
    for name in names:
        points = faces[name]
        if not isinstance(points, (list, tuple)) or not points:
            raise BusinessError("invalid_layout", f"The {name} map must be nonempty.", 422)
        grid = tuple(sorted({read_grid_point(point) for point in points}))
        if not all(is_within_sheet(size, point) for point in grid):
            raise BusinessError("invalid_layout", f"The {name} map extends beyond the sheet.", 422)
        normalized[name] = grid
    return normalized


def read_plate_spec(spec):
    fields(spec, "width", "height", "sides", "faces", code="invalid_layout", status=422)
    size = SheetSize(spec["width"], spec["height"])
    sides = spec["sides"]
    return size, sides, validate_face_maps(size, sides, spec["faces"])


def plate_spec_data(size, sides, faces):
    return {
        "width": size.width,
        "height": size.height,
        "sides": sides,
        "faces": {name: [list(point) for point in grid] for name, grid in faces.items()},
    }
