import json
from dataclasses import dataclass
from hashlib import sha256

from proof.layout import LoadingDirection, ProofLayout, build_proof_layout
from workshop import BusinessError, canonical_json, fields, identifier, transaction


@dataclass(frozen=True)
class LoadedProof:
    proof_id: str
    edition_id: str
    layout: ProofLayout
    artifact: dict


def _decode_artifact(artifact):
    try:
        fields(artifact, "version", "body", "digest")
        if type(artifact["version"]) is not int or artifact["version"] != 1:
            raise BusinessError("invalid_artifact", "Unsupported proof version.")
        body = fields(artifact["body"], "proof_id", "edition_id", "layout", "nominal_summary")
        proof_id = identifier(body["proof_id"], "proof_id")
        edition_id = identifier(body["edition_id"], "edition_id")
        expected = sha256(canonical_json(body).encode("ascii")).hexdigest()
        if artifact["digest"] != expected:
            raise BusinessError("invalid_artifact", "Proof checksum differs from the supplied body.")
        layout = build_proof_layout(body["layout"])
        if layout.to_spec() != body["layout"]:
            raise BusinessError("invalid_artifact", "Proof layout is not in canonical form.")
        names = tuple(direction.value for direction in LoadingDirection) if layout.sides == "double" else ()
        summary = fields(body["nominal_summary"], *names)
        if any(type(value) is not bool for value in summary.values()) or (names and not any(summary.values())):
            raise BusinessError("invalid_artifact", "Invalid nominal proof summary.")
    except BusinessError as exc:
        raise BusinessError("invalid_artifact", str(exc), 422) from exc
    return LoadedProof(proof_id, edition_id, layout, artifact)


def load_proof(db, proof_id, edition_id, artifact):
    proof = _decode_artifact(artifact)
    if (proof_id, edition_id) != (proof.proof_id, proof.edition_id):
        raise BusinessError("proof_origin_mismatch", "Declared origin differs from the issued proof.", 409)
    payload = canonical_json(artifact)
    with transaction(db, write=True):
        row = db.execute(
            "SELECT edition_id, artifact FROM loaded_proofs WHERE proof_id = ?", (proof_id,)
        ).fetchone()
        if row is None:
            db.execute(
                "INSERT INTO loaded_proofs(proof_id, edition_id, artifact) VALUES (?, ?, ?)",
                (proof_id, edition_id, payload),
            )
        elif (row["edition_id"], row["artifact"]) != (edition_id, payload):
            raise BusinessError("proof_conflict", "This proof number already identifies another artifact.", 409)
        else:
            return proof, False
    return proof, True


def read_loaded_proof(db, proof_id):
    row = db.execute("SELECT artifact FROM loaded_proofs WHERE proof_id = ?", (proof_id,)).fetchone()
    if row is None:
        raise BusinessError("proof_not_loaded", "Load the proof at this station first.", 404)
    return _decode_artifact(json.loads(row["artifact"]))
