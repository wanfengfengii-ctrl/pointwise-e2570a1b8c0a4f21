from paper.intake import read_sheet
from press.history import read_sheet_impressions
from press.imprint import imprint_sheet
from workshop import fields, identifier, not_found, transaction


def handle_imprint_request(db, method, path, payload):
    if method == "POST" and path == ("impressions",):
        fields(payload, "sheet_id", "face", "command")
        result = imprint_sheet(db, identifier(payload["sheet_id"], "sheet_id"), payload["face"], payload["command"])
        return 201, result.to_data()
    if method == "GET" and len(path) == 2 and path[0] == "impressions":
        sheet_id = identifier(path[1], "sheet_id")
        with transaction(db):
            read_sheet(db, sheet_id)
            impressions = read_sheet_impressions(db, sheet_id)
        return 200, {"sheet_id": sheet_id, "impressions": [item.to_data() for item in impressions]}
    raise not_found()
