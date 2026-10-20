CREATE TABLE IF NOT EXISTS main.course (
    course_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    teacher_id TEXT NOT NULL,
    term TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS main.dimension (
    dim_id TEXT PRIMARY KEY NOT NULL,
    course_id TEXT NOT NULL REFERENCES course (course_id),
    name TEXT NOT NULL,
    weight REAL NOT NULL CHECK (weight > 0 AND weight <= 1),
    UNIQUE (course_id, name)
);

-- Budgets use millionths of epsilon, avoiding cumulative floating-point drift.
-- Policy defaults and conversion belong to the business configuration slice.
CREATE TABLE IF NOT EXISTS main.budget_ledger (
    ledger_id TEXT PRIMARY KEY NOT NULL,
    course_id TEXT NOT NULL UNIQUE REFERENCES course (course_id),
    eps_total_micros INTEGER NOT NULL
        CHECK (typeof(eps_total_micros) = 'integer' AND eps_total_micros > 0),
    eps_used_micros INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(eps_used_micros) = 'integer'
            AND eps_used_micros >= 0 AND eps_used_micros <= eps_total_micros),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS main.audit_log (
    log_id TEXT PRIMARY KEY NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    course_id TEXT,
    stat_type TEXT,
    eps_cost_micros INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(eps_cost_micros) = 'integer' AND eps_cost_micros >= 0),
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS main.idx_audit_log_course_time
    ON audit_log (course_id, ts);

CREATE TRIGGER IF NOT EXISTS main.audit_log_no_update
    BEFORE UPDATE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'audit log is append-only');
    END;

CREATE TRIGGER IF NOT EXISTS main.audit_log_no_delete
    BEFORE DELETE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'audit log is append-only');
    END;
