from plate.revisions import read_frozen_edition
from proof.checks import check_initial_alignment
from proof.issue import issue_proof, read_issued_proof
from proof.layout import build_proof_layout
from proof.loading import load_proof, read_loaded_proof
from workshop import BusinessError, fields, identifier, not_found


def handle_issue_request(db, method, path, payload):
    if method == "GET" and len(path) == 3 and path[0] == "editions" and path[2] == "check":
        edition = read_frozen_edition(db, identifier(path[1], "edition_id"))
        layout = build_proof_layout(edition.to_data()["spec"])
        return 200, {"edition_id": edition.edition_id, **check_initial_alignment(layout).to_data()}
    if method == "POST" and path == ("proofs",):
        if payload.keys() == {"edition_id"}:
            proof = issue_proof(db, identifier(payload["edition_id"], "edition_id"))
        elif payload.keys() == {"edition_id", "repair"}:
            proof = issue_proof(db, identifier(payload["edition_id"], "edition_id"), payload["repair"])
        else:
            raise BusinessError("invalid_request", "Supply an edition_id and an optional repair.")
        return 201, proof.artifact
    if method == "GET" and len(path) == 2 and path[0] == "proofs":
        return 200, read_issued_proof(db, identifier(path[1], "proof_id")).artifact
    raise not_found()


def handle_load_request(db, method, path, payload):
    if method == "POST" and path == ("proof-loads",):
        fields(payload, "proof_id", "edition_id", "artifact")
        proof, inserted = load_proof(
            db, identifier(payload["proof_id"], "proof_id"),
            identifier(payload["edition_id"], "edition_id"), payload["artifact"],
        )
        return (201 if inserted else 200), proof.artifact
    if method == "GET" and len(path) == 2 and path[0] == "proof-loads":
        return 200, read_loaded_proof(db, identifier(path[1], "proof_id")).artifact
    raise not_found()
