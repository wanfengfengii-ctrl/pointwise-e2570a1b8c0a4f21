from plate.drafts import read_draft, save_draft
from plate.revisions import freeze_edition, read_frozen_edition
from workshop import BusinessError, fields, identifier, not_found


def handle_plate_request(db, method, path, payload):
    if len(path) == 2 and path[0] == "drafts":
        draft_id = identifier(path[1], "draft_id")
        if method == "PUT":
            fields(payload, "spec")
            return 200, save_draft(db, draft_id, payload["spec"]).to_data()
        if method == "GET":
            return 200, read_draft(db, draft_id).to_data()
    if method == "POST" and path == ("editions",):
        if payload.keys() == {"draft_id"}:
            edition = freeze_edition(db, draft_id=identifier(payload["draft_id"], "draft_id"))
        elif payload.keys() == {"spec"}:
            if not isinstance(payload["spec"], dict):
                raise BusinessError("invalid_layout", "Edition spec must be an object.", 422)
            edition = freeze_edition(db, spec=payload["spec"])
        else:
            raise BusinessError("invalid_request", "Supply a draft_id or a direct spec.")
        return 201, edition.to_data()
    if method == "GET" and len(path) == 2 and path[0] == "editions":
        edition = read_frozen_edition(db, identifier(path[1], "edition_id"))
        return 200, edition.to_data()
    raise not_found()
