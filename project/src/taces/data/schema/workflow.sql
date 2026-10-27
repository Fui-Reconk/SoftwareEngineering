-- Workflow metadata is deliberately separate from anonymous evaluation rows.
CREATE TABLE main.course_state (
    course_id TEXT PRIMARY KEY NOT NULL REFERENCES course (course_id),
    closes_at INTEGER NOT NULL CHECK (typeof(closes_at) = 'integer' AND closes_at >= 0),
    data_version INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(data_version) = 'integer' AND data_version >= 0)
);

CREATE TABLE identity.code_state (
    code_hash TEXT PRIMARY KEY NOT NULL REFERENCES enroll_code (code_hash),
    expires_at INTEGER NOT NULL CHECK (typeof(expires_at) = 'integer' AND expires_at >= 0)
);

CREATE TABLE main.privacy_policy (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    epsilon_micros INTEGER NOT NULL CHECK (typeof(epsilon_micros) = 'integer' AND epsilon_micros BETWEEN 10000 AND 1000000),
    threshold INTEGER NOT NULL CHECK (typeof(threshold) = 'integer' AND threshold BETWEEN 3 AND 50),
    total_micros INTEGER NOT NULL CHECK (typeof(total_micros) = 'integer' AND total_micros BETWEEN 100000 AND 20000000),
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision > 0)
);
INSERT INTO main.privacy_policy VALUES (1, 100000, 5, 4000000, 1);

CREATE TABLE main.agg_result (
    publication_id TEXT PRIMARY KEY NOT NULL,
    course_id TEXT NOT NULL REFERENCES course (course_id),
    data_version INTEGER NOT NULL CHECK (typeof(data_version) = 'integer' AND data_version >= 0),
    policy_revision INTEGER NOT NULL CHECK (typeof(policy_revision) = 'integer' AND policy_revision > 0),
    payload TEXT NOT NULL,
    published_at TEXT NOT NULL,
    UNIQUE (course_id, data_version, policy_revision)
);
CREATE INDEX main.idx_agg_result_course ON agg_result (course_id, published_at);

-- Legacy windows/codes remain closed until an administrator reconfigures them.
INSERT INTO main.course_state (course_id, closes_at, data_version)
SELECT course_id, 0, (SELECT count(DISTINCT submission_id) FROM evaluation.rating r
                     WHERE r.course_id=c.course_id) FROM main.course c;
INSERT INTO identity.code_state (code_hash, expires_at)
SELECT code_hash, 0 FROM identity.enroll_code;
