-- Each submission has one row per dimension and a random submission_id.
-- No student, evaluation code, IP address, or exact submission time is recorded.
CREATE TABLE IF NOT EXISTS evaluation.rating (
    rating_id TEXT PRIMARY KEY NOT NULL,
    submission_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    dim_id TEXT NOT NULL,
    score INTEGER NOT NULL
        CHECK (typeof(score) = 'integer' AND score BETWEEN 1 AND 5),
    UNIQUE (submission_id, dim_id)
);

CREATE INDEX IF NOT EXISTS evaluation.idx_rating_course_submission
    ON rating (course_id, submission_id);

CREATE TABLE IF NOT EXISTS evaluation.open_text (
    text_id TEXT PRIMARY KEY NOT NULL,
    rating_id TEXT NOT NULL UNIQUE REFERENCES rating (rating_id),
    content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 500)
);
