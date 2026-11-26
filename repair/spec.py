from dataclasses import dataclass

from plate.geometry import GridPoint, SheetSize, is_within_sheet, read_grid_point
from proof.layout import LoadingDirection
from workshop import BusinessError, fields

MAX_REPAIR_PLATES = 60


@dataclass(frozen=True)
class RepairPlate:
    position: GridPoint
    cells: tuple[GridPoint, ...]


@dataclass(frozen=True)
class RepairSpec:
    repairable: tuple[GridPoint, ...]
    forbidden: tuple[GridPoint, ...]
    plates: tuple[RepairPlate, ...]


def mirror_cells(direction, cells, width):
    if direction == LoadingDirection.RIGHT:
        return frozenset((width - 1 - x, y) for x, y in cells)
    return frozenset(cells)


def _read_zone(value, size, name):
    if not isinstance(value, list):
        raise BusinessError("invalid_repair", f"The repair {name} must be an array of grid points.", 422)
    points = tuple(sorted({read_grid_point(point, "invalid_repair") for point in value}))
    if not all(is_within_sheet(size, point) for point in points):
        raise BusinessError("invalid_repair", f"The repair {name} extends beyond the sheet.", 422)
    return points


def read_repair_spec(value, size: SheetSize) -> RepairSpec:
    fields(value, "repairable", "forbidden", "plates", code="invalid_repair", status=422)
    repairable = _read_zone(value["repairable"], size, "repairable")
    forbidden = _read_zone(value["forbidden"], size, "forbidden")
    plates_value = value["plates"]
    if not isinstance(plates_value, list):
        raise BusinessError("invalid_repair", "Repair plates must be an array.", 422)
    if len(plates_value) > MAX_REPAIR_PLATES:
        raise BusinessError("invalid_repair", "At most 60 repair plates can be registered.", 422)
    plates = []
    for item in plates_value:
        fields(item, "position", "cells", code="invalid_repair", status=422)
        position = read_grid_point(item["position"], "invalid_repair")
        if not is_within_sheet(size, position):
            raise BusinessError("invalid_repair", "A repair plate position lies beyond the sheet.", 422)
        cells = _read_zone(item["cells"], size, "plate cells")
        if not cells:
            raise BusinessError("invalid_repair", "A repair plate must cover at least one cell.", 422)
        plates.append(RepairPlate(position, cells))
    return RepairSpec(repairable, forbidden, tuple(plates))


def repair_spec_data(spec: RepairSpec):
    return {
        "repairable": [list(point) for point in spec.repairable],
        "forbidden": [list(point) for point in spec.forbidden],
        "plates": [
            {"position": list(plate.position), "cells": [list(point) for point in plate.cells]}
            for plate in spec.plates
        ],
    }
