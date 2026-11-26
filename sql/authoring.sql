CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY NOT NULL,
    spec TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editions (
    edition_id TEXT PRIMARY KEY NOT NULL,
    draft_id TEXT,
    spec TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issued_proofs (
    proof_id TEXT PRIMARY KEY NOT NULL,
    edition_id TEXT NOT NULL REFERENCES editions(edition_id),
    artifact TEXT NOT NULL
);
