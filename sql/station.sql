CREATE TABLE IF NOT EXISTS loaded_proofs (
    proof_id TEXT PRIMARY KEY NOT NULL,
    edition_id TEXT NOT NULL,
    artifact TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sheets (
    sheet_id TEXT PRIMARY KEY NOT NULL,
    proof_id TEXT NOT NULL REFERENCES loaded_proofs(proof_id),
    UNIQUE (sheet_id, proof_id)
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id INTEGER PRIMARY KEY,
    sheet_id TEXT NOT NULL REFERENCES sheets(sheet_id),
    probe TEXT NOT NULL CHECK (probe IN ('edge', 'top')),
    point TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS observations_by_sheet ON observations(sheet_id, observation_id);

CREATE TABLE IF NOT EXISTS impressions (
    impression_id INTEGER PRIMARY KEY,
    sheet_id TEXT NOT NULL,
    proof_id TEXT NOT NULL,
    face TEXT NOT NULL CHECK (face IN ('front', 'back')),
    command TEXT NOT NULL,
    position TEXT NOT NULL,
    front_impression_id INTEGER REFERENCES impressions(impression_id),
    FOREIGN KEY (sheet_id, proof_id) REFERENCES sheets(sheet_id, proof_id),
    UNIQUE (sheet_id, face),
    CHECK ((face = 'front' AND front_impression_id IS NULL) OR
           (face = 'back' AND front_impression_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS acceptances (
    acceptance_id TEXT PRIMARY KEY NOT NULL,
    receipt TEXT NOT NULL
);
