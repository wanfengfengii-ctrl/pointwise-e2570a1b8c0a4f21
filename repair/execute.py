from paper.observations import read_sheet_directions
from proof.loading import read_loaded_proof
from repair.orders import read_order
from repair.prints import RepairPrint, find_order_print
from workshop import BusinessError, canonical_json, transaction


def execute_repair_action(db, order_id, action_no):
    if type(action_no) is not int:
        raise BusinessError("invalid_request", "action_no must be an integer.")
    with transaction(db, write=True):
        order = read_order(db, order_id)
        existing = find_order_print(db, order_id, action_no)
        if existing is not None:
            return existing, False
        if order.status == "unsolvable":
            raise BusinessError("repair_unsolvable", "This repair order has no feasible action set.", 409)
        if order.status == "superseded":
            raise BusinessError("order_superseded", "This repair order was replaced by a newer one.", 409)
        layout = read_loaded_proof(db, order.proof_id).layout
        current = [direction.value for direction in read_sheet_directions(db, order.sheet_id, layout)]
        if current != list(order.directions):
            raise BusinessError(
                "stale_order",
                "The positioning state changed; request a new repair order before printing.",
                409,
            )
        action = next((item for item in order.actions if item["action_no"] == action_no), None)
        if action is None:
            raise BusinessError("repair_action_not_found", "This repair order has no such action.", 404)
        cells = tuple(sorted(tuple(point) for point in action["cells"]))
        cursor = db.execute(
            """INSERT INTO repair_prints(order_id, action_no, sheet_id, impression_id, coverage)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT(order_id, action_no) DO NOTHING""",
            (order_id, action_no, order.sheet_id, order.impression_id,
             canonical_json([list(point) for point in cells])),
        )
        if cursor.rowcount != 1:
            return find_order_print(db, order_id, action_no), False
        return RepairPrint(cursor.lastrowid, order_id, order.sheet_id, order.impression_id,
                           action_no, cells), True
