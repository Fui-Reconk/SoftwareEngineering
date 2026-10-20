-- No submission identifier or submission timestamp is stored in the identity file.
CREATE TABLE IF NOT EXISTS identity.student (
    student_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    class_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS identity.enroll_code (
    code_hash TEXT PRIMARY KEY NOT NULL CHECK (length(code_hash) = 64),
    course_id TEXT NOT NULL,
    used_flag INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(used_flag) = 'integer' AND used_flag IN (0, 1))
);

CREATE INDEX IF NOT EXISTS identity.idx_enroll_code_course
    ON enroll_code (course_id, used_flag);
