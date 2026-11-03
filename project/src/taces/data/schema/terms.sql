-- Terms are reusable across courses; legacy course labels remain unchanged.
CREATE TABLE main.academic_term (
    term TEXT PRIMARY KEY NOT NULL
        CHECK (instr(term, char(0)) = 0 AND length(term) = 5
               AND term GLOB '[0-9][0-9][0-9][0-9][春秋]' AND substr(term, 1, 4) <> '0000')
);

INSERT OR IGNORE INTO main.academic_term (term)
SELECT term FROM main.course
WHERE instr(term, char(0)) = 0 AND length(term) = 5
  AND term GLOB '[0-9][0-9][0-9][0-9][春秋]' AND substr(term, 1, 4) <> '0000';
