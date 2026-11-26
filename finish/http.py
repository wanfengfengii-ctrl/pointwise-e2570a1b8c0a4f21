from finish.archive import read_receipt
from finish.batches import inspect_batch
from workshop import fields, identifier, not_found


def handle_finish_request(db, method, path, payload):
    if method == "POST" and path == ("acceptances",):
        fields(payload, "sheet_ids")
        return 201, inspect_batch(db, payload["sheet_ids"]).to_data()
    if method == "GET" and len(path) == 2 and path[0] == "acceptances":
        receipt = read_receipt(db, identifier(path[1], "acceptance_id"))
        return 200, receipt.to_data()
    raise not_found()
