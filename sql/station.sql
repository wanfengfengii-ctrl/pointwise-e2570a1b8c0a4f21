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

CREATE TABLE IF NOT EXISTS repair_orders (
    order_id TEXT PRIMARY KEY NOT NULL,
    sheet_id TEXT NOT NULL,
    proof_id TEXT NOT NULL,
    impression_id INTEGER NOT NULL REFERENCES impressions(impression_id),
    readings TEXT NOT NULL,
    directions TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'unsolvable', 'superseded')),
    demand TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    actions TEXT NOT NULL,
    FOREIGN KEY (sheet_id, proof_id) REFERENCES sheets(sheet_id, proof_id)
);

CREATE INDEX IF NOT EXISTS repair_orders_by_sheet ON repair_orders(sheet_id);

CREATE TABLE IF NOT EXISTS repair_prints (
    repair_id INTEGER PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES repair_orders(order_id),
    action_no INTEGER NOT NULL,
    sheet_id TEXT NOT NULL,
    impression_id INTEGER NOT NULL,
    coverage TEXT NOT NULL,
    UNIQUE (order_id, action_no)
);

CREATE INDEX IF NOT EXISTS repair_prints_by_sheet ON repair_prints(sheet_id, impression_id);
