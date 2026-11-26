from repair.execute import execute_repair_action
from repair.orders import create_repair_order, read_order
from repair.prints import read_order_prints, read_repair_print
from workshop import BusinessError, fields, identifier, not_found, transaction


def handle_repair_request(db, method, path, payload):
    if method == "POST" and path == ("repair-orders",):
        fields(payload, "sheet_id", "impression_id", "readings")
        order = create_repair_order(
            db, identifier(payload["sheet_id"], "sheet_id"),
            payload["impression_id"], payload["readings"],
        )
        return 201, order.to_data()
    if method == "GET" and len(path) == 2 and path[0] == "repair-orders":
        order_id = identifier(path[1], "order_id")
        with transaction(db):
            order = read_order(db, order_id)
            executions = read_order_prints(db, order_id)
        return 200, order.to_data(executions)
    if method == "POST" and path == ("repair-executions",):
        fields(payload, "order_id", "action_no")
        repair_print, created = execute_repair_action(
            db, identifier(payload["order_id"], "order_id"), payload["action_no"],
        )
        return (201 if created else 200), repair_print.to_data()
    if method == "GET" and len(path) == 2 and path[0] == "repair-executions":
        if not path[1].isdecimal():
            raise BusinessError("invalid_request", "Invalid repair_id.")
        return 200, read_repair_print(db, int(path[1])).to_data()
    raise not_found()
