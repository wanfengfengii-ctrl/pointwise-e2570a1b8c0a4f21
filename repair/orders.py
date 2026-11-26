import json
from dataclasses import dataclass
from uuid import uuid4

from paper.observations import read_sheet_directions
from plate.geometry import is_within_sheet, read_grid_point
from press.history import read_print_facts
from repair.prints import read_sheet_repair_prints
from repair.solve import solve_exact_cover
from repair.spec import mirror_cells
from workshop import BusinessError, canonical_json, transaction

MAX_REPAIR_READINGS = 20


@dataclass(frozen=True)
class RepairOrder:
    order_id: str
    sheet_id: str
    proof_id: str
    impression_id: int
    readings: tuple
    directions: tuple
    status: str
    demand: tuple
    interpretation: dict
    actions: tuple

    def to_data(self, executions=()):
        return {
            "order_id": self.order_id,
            "sheet_id": self.sheet_id,
            "proof_id": self.proof_id,
            "impression_id": self.impression_id,
            "readings": [list(point) for point in self.readings],
            "directions": list(self.directions),
            "status": self.status,
            "demand": [list(point) for point in self.demand],
            "interpretation": self.interpretation,
            "actions": [dict(action) for action in self.actions],
            "executions": [item.to_data() for item in executions],
        }


def _row_to_order(row):
    return RepairOrder(
        row["order_id"], row["sheet_id"], row["proof_id"], row["impression_id"],
        tuple(tuple(point) for point in json.loads(row["readings"])),
        tuple(json.loads(row["directions"])),
        row["status"],
        tuple(tuple(point) for point in json.loads(row["demand"])),
        json.loads(row["interpretation"]),
        tuple(json.loads(row["actions"])),
    )


def read_order(db, order_id):
    row = db.execute("SELECT * FROM repair_orders WHERE order_id = ?", (order_id,)).fetchone()
    if row is None:
        raise BusinessError("repair_order_not_found", "Repair order does not exist.", 404)
    return _row_to_order(row)


def read_latest_order(db, sheet_id):
    row = db.execute(
        "SELECT * FROM repair_orders WHERE sheet_id = ? ORDER BY rowid DESC LIMIT 1",
        (sheet_id,),
    ).fetchone()
    return _row_to_order(row) if row is not None else None


def create_repair_order(db, sheet_id, impression_id, readings):
    if type(impression_id) is not int:
        raise BusinessError("invalid_request", "impression_id must be an integer.")
    if not isinstance(readings, list) or not readings:
        raise BusinessError("invalid_readings", "Readings must be a nonempty array of grid points.", 422)
    points = tuple(sorted({read_grid_point(point, "invalid_readings") for point in readings}))
    if len(points) > MAX_REPAIR_READINGS:
        raise BusinessError("invalid_readings", "At most 20 missing cells per sheet.", 422)
    with transaction(db, write=True):
        facts = read_print_facts(db, sheet_id)
        layout = facts.proof.layout
        if not all(is_within_sheet(layout.size, point) for point in points):
            raise BusinessError("invalid_readings", "A reading lies beyond the sheet.", 422)
        repair = facts.proof.repair
        if repair is None:
            raise BusinessError("repair_not_registered", "This proof carries no repair registration.", 409)
        front = next((item for item in facts.impressions if item.face == "front"), None)
        if front is None:
            raise BusinessError("invalid_sequence", "Repair requires a printed front.", 409)
        target = next((item for item in facts.impressions if item.impression_id == impression_id), None)
        if target is None:
            raise BusinessError("impression_not_found", "This paper has no such impression.", 404)
        if target.face != "front":
            raise BusinessError("impression_mismatch", "Readings must cite the front impression.", 409)
        directions = read_sheet_directions(db, sheet_id, layout)
        width = layout.size.width
        observed = frozenset(points)
        executed = read_sheet_repair_prints(db, sheet_id, front.impression_id)
        covered = frozenset().union(*(item.cells for item in executed)) if executed else frozenset()
        remaining = observed - covered
        front_cells = frozenset(front.position)
        repairable = frozenset(repair.repairable)
        forbidden = frozenset(repair.forbidden)
        interpretation = {}
        missing_by_direction = {}
        intact_by_direction = {}
        for direction in directions:
            missing = mirror_cells(direction, remaining, width)
            missing_by_direction[direction] = missing
            interpretation[direction.value] = {"missing": [list(point) for point in sorted(missing)]}
            intact_by_direction[direction] = (front_cells | mirror_cells(direction, covered, width)) - missing
        demand_repairable = all(
            missing_by_direction[direction] <= repairable for direction in directions
        )
        candidates = []
        for action_no, plate in enumerate(repair.plates, start=1):
            cells = frozenset(plate.cells)
            usable = all(
                not (mirror_cells(direction, cells, width) & forbidden)
                and not (mirror_cells(direction, cells, width) & intact_by_direction[direction])
                for direction in directions
            )
            if usable:
                candidates.append((action_no, cells))
        plan = solve_exact_cover(remaining, candidates) if demand_repairable else None
        actions = []
        if plan is not None:
            plates = {action_no: plate for action_no, plate in enumerate(repair.plates, start=1)}
            for action_no in plan:
                plate = plates[action_no]
                cells = frozenset(plate.cells)
                actions.append({
                    "action_no": action_no,
                    "position": list(plate.position),
                    "cells": [list(point) for point in sorted(cells)],
                    "coverage": {
                        direction.value: [
                            list(point)
                            for point in sorted(mirror_cells(direction, cells & remaining, width))
                        ]
                        for direction in directions
                    },
                })
        status = "open" if plan is not None else "unsolvable"
        db.execute(
            "UPDATE repair_orders SET status = 'superseded' WHERE sheet_id = ? AND status != 'superseded'",
            (sheet_id,),
        )
        order_id = uuid4().hex
        db.execute(
            """INSERT INTO repair_orders(order_id, sheet_id, proof_id, impression_id, readings,
                                        directions, status, demand, interpretation, actions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order_id, sheet_id, facts.sheet.proof_id, front.impression_id,
                canonical_json([list(point) for point in points]),
                canonical_json([direction.value for direction in directions]),
                status,
                canonical_json([list(point) for point in sorted(remaining)]),
                canonical_json(interpretation),
                canonical_json(actions),
            ),
        )
        order = RepairOrder(
            order_id, sheet_id, facts.sheet.proof_id, front.impression_id, points,
            tuple(direction.value for direction in directions), status,
            tuple(sorted(remaining)), interpretation, tuple(actions),
        )
    return order
