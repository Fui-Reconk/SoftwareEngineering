import hashlib
from time import perf_counter

from tests.workflow_support import staff, create_course, login_role


def test_first_publication_for_ten_thousand_complete_submissions(staff):
    create_course(staff)
    with staff["db"].transaction() as con:
        dims = [row[0] for row in con.execute("SELECT dim_id FROM main.dimension WHERE course_id='c1' ORDER BY rowid")]
        con.executemany("INSERT INTO evaluation.rating VALUES (?,?,?,?,?)",
            ((f"r{i}-{d}", f"s{i}", "c1", dim, i % 5 + 1) for i in range(10000) for d, dim in enumerate(dims)))
        codes = [hashlib.sha256(f"perf-{i}".encode()).hexdigest() for i in range(10000)]
        con.executemany("INSERT INTO identity.enroll_code VALUES (?,'c1',1)", ((code,) for code in codes))
        con.executemany("INSERT INTO identity.code_state VALUES (?,0)", ((code,) for code in codes))
        con.execute("UPDATE main.course_state SET data_version=10000 WHERE course_id='c1'")
    teacher, _ = login_role(staff)
    started = perf_counter()
    response = teacher.get("/api/courses/c1/statistics")
    elapsed = perf_counter() - started
    assert response.status_code == 200
    assert response.json["data"]["responses"] == response.json["data"]["enrolled"] == 10000
    assert sum(row["count"] for row in response.json["data"]["distribution"]) == 10000
    assert elapsed < 5, f"10k first publication took {elapsed:.3f}s"
    print(f"10k first publication: {elapsed:.3f}s")
