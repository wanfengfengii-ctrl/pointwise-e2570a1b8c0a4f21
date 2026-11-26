from paper.intake import read_sheet, register_sheet
from paper.observations import read_observations, read_sheet_directions, record_observation
from plate.geometry import read_grid_point
from proof.loading import read_loaded_proof
from workshop import fields, identifier, not_found, transaction


def handle_paper_request(db, method, path, payload):
    if method == "POST" and path == ("sheets",):
        fields(payload, "sheet_id", "proof_id")
        sheet = register_sheet(db, identifier(payload["sheet_id"], "sheet_id"),
                               identifier(payload["proof_id"], "proof_id"))
        return 201, sheet.to_data()
    if method == "POST" and path == ("observations",):
        fields(payload, "sheet_id", "probe", "point")
        item, directions = record_observation(
            db, identifier(payload["sheet_id"], "sheet_id"), payload["probe"],
            read_grid_point(payload["point"], "invalid_observation"),
        )
        return 201, {**item.to_data(), "directions": [direction.value for direction in directions]}
    if method == "GET" and len(path) == 2 and path[0] == "sheets":
        sheet_id = identifier(path[1], "sheet_id")
        with transaction(db):
            sheet = read_sheet(db, sheet_id)
            layout = read_loaded_proof(db, sheet.proof_id).layout
            observations = read_observations(db, sheet_id)
            directions = read_sheet_directions(db, sheet_id, layout)
        return 200, {
            **sheet.to_data(),
            "directions": [direction.value for direction in directions],
            "observations": [item.to_data() for item in observations],
        }
    raise not_found()
