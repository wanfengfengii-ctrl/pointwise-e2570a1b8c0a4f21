import json
from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from plate.revisions import read_frozen_edition
from proof.checks import check_initial_alignment
from proof.layout import build_proof_layout
from workshop import BusinessError, canonical_json, transaction


@dataclass(frozen=True)
class IssuedProof:
    proof_id: str
    edition_id: str
    artifact: dict


def issue_proof(db, edition_id):
    with transaction(db, write=True):
        edition = read_frozen_edition(db, edition_id)
        layout = build_proof_layout(edition.to_data()["spec"])
        check = check_initial_alignment(layout)
        if not check.eligible:
            raise BusinessError("initial_incompatible", "The nominal front has no matching back placement.", 409)
        proof_id = uuid4().hex
        body = {
            "proof_id": proof_id,
            "edition_id": edition.edition_id,
            "layout": layout.to_spec(),
            "nominal_summary": {direction.value: bool(commands) for direction, commands in check.allowed.items()},
        }
        digest = sha256(canonical_json(body).encode("ascii")).hexdigest()
        artifact = {"version": 1, "body": body, "digest": digest}
        db.execute(
            "INSERT INTO issued_proofs(proof_id, edition_id, artifact) VALUES (?, ?, ?)",
            (proof_id, edition_id, canonical_json(artifact)),
        )
    return IssuedProof(proof_id, edition_id, artifact)


def read_issued_proof(db, proof_id):
    row = db.execute(
        "SELECT edition_id, artifact FROM issued_proofs WHERE proof_id = ?", (proof_id,)
    ).fetchone()
    if row is None:
        raise BusinessError("proof_not_found", "Issued proof does not exist.", 404)
    return IssuedProof(proof_id, row["edition_id"], json.loads(row["artifact"]))
