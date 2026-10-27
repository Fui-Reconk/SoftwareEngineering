"""Replay a generated corpus on a disposable DB copy; leave demo codes intact."""

import csv
from io import BytesIO, StringIO
import json
from pathlib import Path
import shutil
import tempfile
import time

from taces import create_app
from taces.business.privacy.mechanism import VOCABULARY
from taces.business.stats.service import aggregate
from taces.data.database import Database


def expect(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(root, filename):
    return json.loads((root / filename).read_text(encoding="utf-8"))


def actual_truth(db, cid):
    """Reconstruct truth using SQL, independently of the generation algorithm."""
    with db.read_current() as con:
        dimensions = con.execute("SELECT * FROM main.dimension WHERE course_id=? ORDER BY rowid", (cid,)).fetchall()
        responses = con.execute("SELECT count(DISTINCT submission_id) FROM evaluation.rating WHERE course_id=?", (cid,)).fetchone()[0]
        means = [con.execute("SELECT avg(score) FROM evaluation.rating WHERE course_id=? AND dim_id=?", (cid, d["dim_id"])).fetchone()[0]
                 for d in dimensions] if responses else []
        hist = [0] * 5
        for row in con.execute("SELECT CAST(avg(score)+0.5 AS INTEGER),count(*) FROM "
                               "(SELECT submission_id,score FROM evaluation.rating WHERE course_id=?) "
                               "GROUP BY submission_id", (cid,)):
            hist[row[0] - 1] += 1
            expect(row[1] == len(dimensions), f"{cid}: incomplete submission")
        texts = [r[0] for r in con.execute("SELECT t.content FROM evaluation.open_text t JOIN evaluation.rating r "
                                           "ON r.rating_id=t.rating_id WHERE r.course_id=?", (cid,))]
        words = dict.fromkeys(VOCABULARY, 0)
        for text in texts:
            matched = 0
            for word in VOCABULARY:
                if word in text and matched < 3:
                    words[word] += 1
                    matched += 1
        return {"responses": responses, "means": means, "histogram": hist,
                "weighted_mean": sum(value * dim["weight"] for value, dim in zip(means, dimensions)),
                "text_responses": len(texts), "max_text_length": max(map(len, texts), default=0), "word_counts": words}


def verify_dataset(root):
    root = Path(root).resolve()
    manifest, truth, cases = (read_json(root, filename) for filename in ("manifest.json", "ground_truth.json", "api_cases.json"))
    report = {"passed": 0, "failed": 0, "performance_seconds": None, "aggregation_seconds": None, "checks": []}

    def check(name, operation):
        try:
            operation()
        except Exception as error:
            report["failed"] += 1
            report["checks"].append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"})
        else:
            report["passed"] += 1
            report["checks"].append({"name": name, "passed": True, "detail": "ok"})

    check("fixture_not_expired", lambda: expect(time.time() < manifest["valid_until"], "Fixture window expired; generate a fresh dataset"))
    with tempfile.TemporaryDirectory(prefix="taces-fixture-check-") as temporary:
        data_dir = Path(temporary) / "db"
        shutil.copytree(root / "db", data_dir)
        db = Database(data_dir)
        app = create_app({"TESTING": True, "DATA_DIR": data_dir})

        def integrity():
            with db.read_current() as con:
                for schema in ("main", "identity", "evaluation"):
                    expect(con.execute(f"PRAGMA {schema}.integrity_check").fetchone()[0] == "ok", schema + " integrity failed")
                    expect(not con.execute(f"PRAGMA {schema}.foreign_key_check").fetchall(), schema + " foreign keys failed")
                expect(con.execute("SELECT count(*) FROM identity.student").fetchone()[0] == 0, "Synthetic students must not be invented")
                expect(con.execute("SELECT count(*) FROM identity.auth_session").fetchone()[0] == 0, "Generated DB must not contain live sessions")
                for table in ("rating", "open_text"):
                    columns = {row[1] for row in con.execute(f"PRAGMA evaluation.table_info({table})")}
                    expect(not columns & {"student_id", "user_id", "code_hash", "ip", "created_at"}, "Identity leaked into evaluations")
                for table in ("enroll_code", "code_state"):
                    columns = {row[1] for row in con.execute(f"PRAGMA identity.table_info({table})")}
                    expect("submission_id" not in columns, "Submission linked to capability")

        check("database_integrity_and_identity_separation", integrity)
        for course in manifest["courses"]:
            cid = course["id"]

            def validate_truth(cid=cid):
                observed = actual_truth(db, cid)
                expect(observed == truth[cid], f"{cid}: stored data differs from ground_truth.json")
                with db.read_current() as con:
                    used = con.execute("SELECT count(*) FROM identity.enroll_code WHERE course_id=? AND used_flag=1", (cid,)).fetchone()[0]
                    version = con.execute("SELECT data_version FROM main.course_state WHERE course_id=?", (cid,)).fetchone()[0]
                    expect(used == version == observed["responses"], f"{cid}: used-code count/data version mismatch")
                    if observed["responses"]:
                        dimensions = con.execute("SELECT * FROM main.dimension WHERE course_id=? ORDER BY rowid", (cid,)).fetchall()
                        started = time.perf_counter()
                        means, hist, words, texts = aggregate(con, cid, dimensions)
                        elapsed = time.perf_counter() - started
                        expect(means == observed["means"] and hist == observed["histogram"]
                               and words == list(observed["word_counts"].values()) and texts == observed["text_responses"],
                               f"{cid}: business aggregate differs from oracle")
                        if cid == "performance":
                            report["aggregation_seconds"] = elapsed
                            expect(elapsed < 2, f"Raw aggregation exceeded 2 seconds: {elapsed:.3f}")
            check("truth_" + cid, validate_truth)

        clients = {"anonymous": (app.test_client(), {})}
        for actor in ("admin", "teacher", "other_teacher", "auditor"):
            client = app.test_client()
            account = manifest["accounts"][actor]
            response = client.post("/api/auth/login", json={"username": account["username"], "password": account["password"]}, headers={"X-TACES-Request": "1"})
            expect(response.status_code == 200, f"Fixture {actor} login failed: {response.get_json()}")
            clients[actor] = (client, {"X-CSRF-Token": response.json["data"]["csrf_token"]})

        def ledger(cid):
            with db.read_current() as con:
                return con.execute("SELECT eps_used_micros FROM main.budget_ledger WHERE course_id=?", (cid,)).fetchone()[0]

        published = {}
        for course in manifest["courses"]:
            cid = course["id"]
            client = clients[course["owner"]][0]

            def publication(course=course, cid=cid, client=client):
                before = ledger(cid)
                started = time.perf_counter()
                response = client.get(f"/api/courses/{cid}/statistics")
                elapsed = time.perf_counter() - started
                expect(response.status_code == 200, f"HTTP {response.status_code}: {response.get_json()}")
                data = response.json["data"]
                expect(data["state"] == course["state"], f"{cid}: unexpected publication state")
                expect(data["charged"] == course["charged"], f"{cid}: unexpected charge flag")
                expect(ledger(cid) - before == (100000 if course["charged"] else 0), f"{cid}: incorrect budget charge")
                if data["state"] == "published":
                    n = course.get("published_responses", course["responses"])
                    expect(data["responses"] == n, f"{cid}: wrong published response count")
                    expect(sum(row["count"] for row in data["distribution"]) == n, f"{cid}: histogram does not sum to n")
                    expect(all(type(row["count"]) is int and row["count"] >= 0 for row in data["distribution"]), f"{cid}: invalid count")
                    expect(all(1 <= row["value"] <= 5 for row in data["dimensions"]), f"{cid}: score outside [1,5]")
                    expect(0 <= data["openText"]["responses"] <= n, f"{cid}: invalid noisy text count")
                    expect(all(row["word"] in VOCABULARY and 0 <= row["count"] <= data["openText"]["responses"] for row in data["openText"]["terms"]), f"{cid}: invalid word count")
                    expect("UNIQUE_SYNTHETIC_TEXT" not in json.dumps(data), f"{cid}: raw text leaked")
                    published[cid] = data
                    for _ in range(10):
                        again = client.get(f"/api/courses/{cid}/statistics")
                        expect(again.status_code == 200 and again.json["data"] == {**data, "charged": False}, f"{cid}: cache changed or charged again")
                    expect(ledger(cid) - before == (100000 if course["charged"] else 0), f"{cid}: cache reads consumed budget")
                else:
                    expect(data["reason"] == course["reason"], f"{cid}: wrong refusal reason")
                    expect(data["sample"] == course["responses"], f"{cid}: wrong refused sample count")
                if cid == "performance":
                    report["performance_seconds"] = elapsed
                    expect(elapsed < 5, f"First publication exceeded 5 seconds: {elapsed:.3f}")
            check("publication_and_10_cache_reads_" + cid, publication)

        def mutation_snapshot():
            with db.read_current() as con:
                return (con.execute("SELECT count(*) FROM evaluation.rating").fetchone()[0],
                        con.execute("SELECT sum(used_flag) FROM identity.enroll_code").fetchone()[0],
                        tuple(tuple(row) for row in con.execute("SELECT course_id,data_version FROM main.course_state ORDER BY course_id")))

        for case in cases:
            def replay(case=case):
                client, csrf = clients[case["actor"]]
                headers = {**(csrf if case.get("csrf", True) else {}), **case.get("headers", {})}
                if "origin" in case:
                    headers["Origin"] = case["origin"]
                options = {"headers": headers}
                if "json" in case:
                    options["json"] = case["json"]
                if "raw" in case:
                    options.update(data=case["raw"], content_type=case["content_type"])
                rejected_submission = case["path"] == "/api/submissions" and case["status"] != 201
                before = mutation_snapshot() if rejected_submission else None
                response = client.open(case["path"], method=case["method"], **options)
                expect(response.status_code == case["status"], f"Expected HTTP {case['status']}, got {response.status_code}: {response.get_json()}")
                data = response.get_json()
                for field, expected in case["expected"].items():
                    value = data
                    for key in field.split("."):
                        value = value[key]
                    expect(value == expected, f"{field}: expected {expected!r}, got {value!r}")
                if rejected_submission:
                    expect(mutation_snapshot() == before, "Rejected request consumed a code or wrote evaluation data")
            check("api_" + case["name"], replay)

        teacher, _ = clients["teacher"]
        admin, admin_headers = clients["admin"]
        auditor, _ = clients["auditor"]

        def submission_boundaries():
            observed = actual_truth(db, "submit_valid")
            expect(observed["responses"] == 5 and observed["means"] == [1, 3, 5], "Valid score endpoints were not stored")
            expect(observed["text_responses"] == 2 and observed["max_text_length"] == 500, "Optional/trimmed/max-length text semantics differ")
        check("successful_submission_score_and_text_boundaries", submission_boundaries)

        def refresh_after_submission():
            before, previous = ledger("refresh"), published["refresh"]
            body = {"code": manifest["codes"]["refresh"], "ratings": [{"dimension": name, "score": 4} for name in ("教学内容", "教学方法", "考核方式")]}
            response = clients["anonymous"][0].post("/api/submissions", json=body)
            expect(response.status_code == 201, "Fresh submission failed")
            fresh = teacher.get("/api/courses/refresh/statistics").json["data"]
            expect(fresh["charged"] and fresh["publicationId"] != previous["publicationId"] and fresh["responses"] == 7, "Data version did not trigger a fresh publication")
            expect(ledger("refresh") == before + 100000, "New data version did not charge exactly once")
        check("new_submission_changes_publication_and_charges_once", refresh_after_submission)

        def verify_exports():
            from pypdf import PdfReader

            for cid in ("at_k", "text_special", "stale_cache"):
                snapshot, before = published[cid], ledger(cid)
                response = teacher.get(f"/api/courses/{cid}/export?format=csv")
                expect(response.status_code == 200, "CSV export failed")
                rows = dict(list(csv.reader(StringIO(response.data.decode("utf-8-sig"))))[1:])
                expect(rows["publicationId"] == snapshot["publicationId"] and int(rows["responses"]) == snapshot["responses"], "CSV did not reuse the snapshot")
                expect(float(rows["pooledMean"]) == snapshot["pooledMean"], "CSV mean differs from dashboard")
                for dimension in snapshot["dimensions"]:
                    expect(float(rows["dimension:" + dimension["name"]]) == dimension["value"], "CSV dimension differs from dashboard")
                for bucket in snapshot["distribution"]:
                    expect(int(rows["score:" + str(bucket["score"])]) == bucket["count"], "CSV histogram differs from dashboard")
                response = teacher.get(f"/api/courses/{cid}/export?format=pdf")
                expect(response.status_code == 200 and response.data.startswith(b"%PDF"), "PDF export failed")
                text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.data)).pages)
                expect(snapshot["publicationId"] in text, "PDF publication ID differs")
                expect("UNIQUE_SYNTHETIC_TEXT" not in text and "UNIQUE_SYNTHETIC_TEXT" not in str(rows), "Raw text leaked through an export")
                expect(ledger(cid) == before, "Exports charged budget")
        check("csv_pdf_use_identical_snapshot_without_budget_charge", verify_exports)

        def configuration_lifecycle():
            for values in ({"epsilon": .01, "k": 3}, {"epsilon": 1, "k": 50}, {"epsilon": .1, "k": 5}, {"epsilonTotal": 20}, {"epsilonTotal": 4}):
                response = admin.patch("/api/admin/config", json=values, headers=admin_headers)
                expect(response.status_code == 200, f"Valid boundary configuration rejected: {values}")
                saved = admin.get("/api/admin/config").json["data"]["values"]
                expect(all(saved[key] == value for key, value in values.items()), "Configuration did not persist")
            before = ledger("refresh")
            response = teacher.get("/api/courses/refresh/statistics")
            expect(response.status_code == 200 and response.json["data"]["charged"], "Policy revision did not invalidate the cache")
            expect(ledger("refresh") == before + 100000, "Policy revision charge incorrect")
            response = admin.patch("/api/admin/config", json={"epsilonTotal": .1}, headers=admin_headers)
            expect(response.status_code == 422 and admin.get("/api/admin/config").json["data"]["values"]["epsilonTotal"] == 4, "Budget decrease below spent amount did not roll back")
        check("configuration_boundaries_revision_and_budget_rollback", configuration_lifecycle)

        def audit_pagination():
            first = auditor.get("/api/admin/audit?course=refresh&limit=1")
            expect(first.status_code == 200, "Audit filter failed")
            data = first.json["data"]
            expect(data["next"] == 1 and len(data["entries"]) == 1, "Audit pagination missing")
            second = auditor.get("/api/admin/audit?course=refresh&limit=1&offset=1").json["data"]
            expect(data["entries"] != second["entries"], "Audit repeated first page")
            expect(any(course["course_id"] == "refresh" for course in data["courses"]), "Auditor did not receive course filter options")
        check("auditor_course_filter_and_pagination", audit_pagination)

        def throttle():
            client = app.test_client()
            for _ in range(5):
                response = client.post("/api/auth/login", json={"username": "synthetic_unknown", "password": "wrong-password"}, headers={"X-TACES-Request": "1"})
                expect(response.status_code == 401, "Login failed before the expected throttle threshold")
            response = client.post("/api/auth/login", json={"username": "synthetic_unknown", "password": "wrong-password"}, headers={"X-TACES-Request": "1"})
            expect(response.status_code == 429 and response.headers.get("Retry-After") == "900", "Login throttle did not activate")
        check("login_throttle_after_five_failures", throttle)
    return report
