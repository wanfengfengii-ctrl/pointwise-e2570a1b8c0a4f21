import json
from dataclasses import dataclass

from workshop import BusinessError


@dataclass(frozen=True)
class RepairPrint:
    repair_id: int
    order_id: str
    sheet_id: str
    impression_id: int
    action_no: int
    cells: tuple

    def to_data(self):
        return {
            "repair_id": self.repair_id,
            "order_id": self.order_id,
            "sheet_id": self.sheet_id,
            "impression_id": self.impression_id,
            "action_no": self.action_no,
            "coverage": [list(point) for point in self.cells],
        }


def _row_to_print(row):
    return RepairPrint(
        row["repair_id"], row["order_id"], row["sheet_id"], row["impression_id"],
        row["action_no"], tuple(tuple(point) for point in json.loads(row["coverage"])),
    )


def read_sheet_repair_prints(db, sheet_id, impression_id=None):
    if impression_id is None:
        rows = db.execute(
            "SELECT * FROM repair_prints WHERE sheet_id = ? ORDER BY repair_id", (sheet_id,)
        )
    else:
        rows = db.execute(
            "SELECT * FROM repair_prints WHERE sheet_id = ? AND impression_id = ? ORDER BY repair_id",
            (sheet_id, impression_id),
        )
    return tuple(_row_to_print(row) for row in rows)


def read_order_prints(db, order_id):
    rows = db.execute(
        "SELECT * FROM repair_prints WHERE order_id = ? ORDER BY repair_id", (order_id,)
    )
    return tuple(_row_to_print(row) for row in rows)


def find_order_print(db, order_id, action_no):
    row = db.execute(
        "SELECT * FROM repair_prints WHERE order_id = ? AND action_no = ?",
        (order_id, action_no),
    ).fetchone()
    return _row_to_print(row) if row is not None else None


def read_repair_print(db, repair_id):
    row = db.execute(
        "SELECT * FROM repair_prints WHERE repair_id = ?", (repair_id,)
    ).fetchone()
    if row is None:
        raise BusinessError("repair_print_not_found", "Repair print does not exist.", 404)
    return _row_to_print(row)
