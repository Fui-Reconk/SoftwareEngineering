"""Generate synthetic TACES databases, request cases and independent truth data.

Run from project/: python scripts/generate_test_data.py --check --install-demo
Only fixture scores/text are seeded; capabilities, IDs, password salts and actual
privacy noise always use the application's normal secure randomness.
"""

import argparse
import copy
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import secrets
import shutil
import sqlite3
import sys
import tempfile
import time
from uuid import uuid4


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from taces import create_app
from taces.business.courses.service import CourseService, DEFAULT_DIMENSIONS
from taces.business.privacy.mechanism import VOCABULARY
from taces.business.stats.service import StatisticsService
from taces.business.submission.service import SubmissionService
from taces.data.database import Database


DEFAULT_OUTPUT = PROJECT / "tests" / "experiments" / "output" / "testdata"
PASSWORD = "Taces-demo-2026!"
SEED = 20261027


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def truth_for(rows, comments, weights):
    """Compute the oracle from input records, before inserting into SQLite."""
    n = len(rows)
    means = [sum(row[i] for row in rows) / n for i in range(len(weights))] if n else []
    histogram = [0] * 5
    words = dict.fromkeys(VOCABULARY, 0)
    for row, comment in zip(rows, comments):
        histogram[int(sum(row) / len(row) + .5) - 1] += 1
        for word in [word for word in VOCABULARY if word in comment][:3]:
            words[word] += 1
    return {"responses": n, "means": means, "histogram": histogram,
            "weighted_mean": sum(m * w for m, w in zip(means, weights)),
            "text_responses": sum(bool(text) for text in comments),
            "max_text_length": max(map(len, comments), default=0), "word_counts": words}


def fill_course(db, course_id, count, pattern, text_pattern, rng):
    """Bulk-insert complete synthetic submissions, without an identity/code join."""
    with db.transaction() as con:
        dimensions = con.execute("SELECT * FROM main.dimension WHERE course_id=? ORDER BY rowid", (course_id,)).fetchall()
        rows, comments, rating_rows, text_rows = [], [], [], []
        for index in range(count):
            if pattern == "low":
                scores = [1] * len(dimensions)
            elif pattern == "high":
                scores = [5] * len(dimensions)
            elif pattern == "uniform":
                scores = [index % 5 + 1] * len(dimensions)
            elif pattern == "polarized":
                scores = [1 if index % 2 == 0 else 5] * len(dimensions)
            elif pattern == "weighted":
                scores = [1, 3, 4]
            else:
                scores = [rng.choices([1, 2, 3, 4, 5], weights=[1, 2, 3, 6, 8])[0] for _ in dimensions]
            if text_pattern == "empty":
                comment = ""
            elif text_pattern == "long":
                comment = "反馈" * 250
            elif text_pattern == "special":
                comment = ["<script>alert('synthetic')</script> 清晰 🧪",
                           "' OR 1=1; -- 反馈\n第二行\t\"引号\"",
                           "=SUM(1,2) 作业，作业，作业",
                           "非公开词样例 UNIQUE_SYNTHETIC_TEXT", "考核、答疑、难度、内容"][index % 5]
            else:
                comment = ["", "作业反馈清晰", "节奏实验互动实践例子", "反馈反馈反馈", "🧪 English 示例"][index % 5]
            submission_id = uuid4().hex
            ids = [uuid4().hex for _ in dimensions]
            rating_rows.extend((rid, submission_id, course_id, dim["dim_id"], score)
                               for rid, dim, score in zip(ids, dimensions, scores))
            if comment:
                text_rows.append((uuid4().hex, ids[0], comment))
            rows.append(scores)
            comments.append(comment)
        con.executemany("INSERT INTO evaluation.rating VALUES (?,?,?,?,?)", rating_rows)
        con.executemany("INSERT INTO evaluation.open_text VALUES (?,?,?)", text_rows)
        # Independent capability pool; never persist which code submitted which row.
        used_codes = [secrets.token_hex(16) for _ in range(count)]
        rng.shuffle(used_codes)
        con.executemany("INSERT INTO identity.enroll_code VALUES (?,?,1)",
                        [(hashlib.sha256(code.encode("ascii")).hexdigest(), course_id) for code in used_codes])
        con.executemany("INSERT INTO identity.code_state VALUES (?,0)",
                        [(hashlib.sha256(code.encode("ascii")).hexdigest(),) for code in used_codes])
        con.execute("UPDATE main.course_state SET data_version=? WHERE course_id=?", (count, course_id))
    return truth_for(rows, comments, [d["weight"] for d in dimensions]), used_codes[:1]


def build_api_cases(manifest):
    """A portable ordered request corpus; no running server is required to replay."""
    cases = []
    codes = manifest["codes"]
    ratings = [{"dimension": name, "score": score} for name, score in zip(DEFAULT_DIMENSIONS, [1, 3, 5])]
    body = {"code": codes["valid"], "ratings": ratings}

    def add(name, method, path, status=200, *, actor="anonymous", payload=None, expected=None, **options):
        item = {"name": name, "actor": actor, "method": method, "path": path,
                "status": status, "expected": expected or {}}
        if payload is not None:
            item["json"] = copy.deepcopy(payload)
        item.update(options)
        cases.append(item)

    for state in ("valid", "used", "expired", "closed", "unknown"):
        reason = {"used": "used", "expired": "expired", "closed": "expired", "unknown": "unknown"}.get(state)
        expected = {"data.valid": state == "valid"}
        if reason:
            expected["data.reason"] = reason
        add("code_" + state, "POST", "/api/evaluation-codes/verify", payload={"code": codes[state]}, expected=expected)
    add("code_uppercase", "POST", "/api/evaluation-codes/verify", payload={"code": codes["valid"].upper()}, expected={"data.valid": True})
    for index, value in enumerate(("", "g" * 32, "a" * 31, None, 123, True, [])):
        add(f"code_malformed_{index}", "POST", "/api/evaluation-codes/verify", payload={"code": value}, expected={"data.valid": False})
    for state, status, error in (("used", 409, "CODE_USED"), ("expired", 409, "WINDOW_CLOSED"),
                                 ("closed", 409, "WINDOW_CLOSED"), ("unknown", 400, "INVALID_CODE")):
        add("submit_" + state, "POST", "/api/submissions", status, payload={**body, "code": codes[state]}, expected={"error.code": error})
    for index, score in enumerate((0, 6, -1, True, False, 1.0, 1.5, "3", None, [], {})):
        invalid = copy.deepcopy(body)
        invalid["ratings"][0]["score"] = score
        add(f"score_invalid_{index}", "POST", "/api/submissions", 400, payload=invalid, expected={"error.code": "INVALID_INPUT"})
    malformed = {
        "missing_dimension": ratings[:2], "extra_dimension": ratings + [{"dimension": "额外", "score": 3}],
        "duplicate_dimension": [ratings[0], ratings[0], ratings[2]],
        "unknown_dimension": [{"dimension": "不存在", "score": 3}, *ratings[1:]],
        "missing_score": [{"dimension": DEFAULT_DIMENSIONS[0]}, *ratings[1:]],
        "extra_score_field": [{**ratings[0], "student_id": "synthetic"}, *ratings[1:]],
        "null_ratings": None, "object_ratings": {}, "empty_ratings": [],
    }
    for name, invalid in malformed.items():
        add(name, "POST", "/api/submissions", 400, payload={**body, "ratings": invalid})
    for name, value in (("501", "评" * 501), ("null", None), ("number", 1), ("list", []), ("nul", "a\x00b")):
        add("text_invalid_" + name, "POST", "/api/submissions", 400, payload={**body, "openText": value})
    add("unexpected_identity", "POST", "/api/submissions", 400, payload={**body, "student_id": "synthetic"})
    add("missing_code", "POST", "/api/submissions", 400, payload={"ratings": ratings})
    add("malformed_json", "POST", "/api/submissions", 400, raw="{", content_type="application/json")
    add("wrong_content_type", "POST", "/api/submissions", 415, raw="plain", content_type="text/plain")
    add("oversized_body", "POST", "/api/submissions", 413, payload={**body, "openText": "x" * 17000})
    add("anonymous_statistics", "GET", "/api/courses/at_k/statistics", 401)
    for actor in ("admin", "auditor", "other_teacher"):
        add(actor + "_statistics_forbidden", "GET", "/api/courses/at_k/statistics", 403, actor=actor)
    for actor in ("teacher", "auditor"):
        add(actor + "_config_forbidden", "GET", "/api/admin/config", 403, actor=actor)
    add("teacher_audit_forbidden", "GET", "/api/admin/audit", 403, actor="teacher")
    add("auditor_courses_forbidden", "GET", "/api/courses", 403, actor="auditor")
    add("teacher_foreign_export", "GET", "/api/courses/foreign/export", 403, actor="teacher")
    add("teacher_foreign_course", "GET", "/api/courses/foreign", 403, actor="teacher")
    add("course_not_found", "GET", "/api/courses/does-not-exist/statistics", 404, actor="teacher")
    add("config_missing_csrf", "PATCH", "/api/admin/config", 403, actor="admin", payload={"k": 5}, csrf=False)
    add("config_foreign_origin", "PATCH", "/api/admin/config", 403, actor="admin", payload={"k": 5}, origin="https://invalid.example")
    for key, values in {"epsilon": (0, .009, 1.001, True, "0.1", None, .1000001),
                        "k": (2, 51, 5.0, True, "5", None),
                        "epsilonTotal": (0, .099, 20.001, True, "4", None)}.items():
        for index, value in enumerate(values):
            add(f"config_invalid_{key}_{index}", "PATCH", "/api/admin/config", 422, actor="admin", payload={key: value}, expected={"error.code": "INVALID_VALUE"})
    for name, invalid in (("empty", {}), ("unknown", {"unknown": 1}), ("wrapped", {"values": {"k": 5}}),
                          ("cost_exceeds_total", {"epsilon": 1, "epsilonTotal": .1})):
        add("config_invalid_" + name, "PATCH", "/api/admin/config", 422, actor="admin", payload=invalid)
    add("config_extreme_exponent", "PATCH", "/api/admin/config", 422, actor="admin", raw='{"epsilon":1e999999}', content_type="application/json")
    for index, query in enumerate(("limit=0", "limit=101", "offset=-1", "limit=1&limit=2", "unknown=1",
                                   "from=2026-02-30", "from=2026-10-27T00:00:00", "from=2026-10-28&to=2026-10-27")):
        add(f"audit_invalid_{index}", "GET", "/api/admin/audit?" + query, 400, actor="auditor")
    for index, value in enumerate((0, 1001, True, 1.5, "1")):
        add(f"issue_invalid_{index}", "POST", "/api/admin/courses/validation/evaluation-codes", 400, actor="admin", payload={"count": value})
    add("issue_closed", "POST", "/api/admin/courses/closed/evaluation-codes", 409, actor="admin", payload={"count": 1})
    for index, query in enumerate(("format=xml", "publication=bad", "format=csv&format=pdf", "unknown=1")):
        add(f"export_invalid_{index}", "GET", "/api/courses/at_k/export?" + query, 400, actor="teacher")
    add("export_unpublished", "GET", "/api/courses/empty/export", 409, actor="teacher")
    add("export_unknown_publication", "GET", "/api/courses/at_k/export?publication=" + "0" * 32, 404, actor="teacher")
    add("disabled_account", "POST", "/api/auth/login", 401, payload={"username": "demo_disabled", "password": PASSWORD}, headers={"X-TACES-Request": "1"}, expected={"error.code": "INVALID_CREDENTIALS"})
    add("login_wrong_password", "POST", "/api/auth/login", 401, payload={"username": "demo_teacher", "password": "wrong-password"}, headers={"X-TACES-Request": "1"})
    add("login_missing_header", "POST", "/api/auth/login", 403, payload={"username": "demo_teacher", "password": PASSWORD})
    for index, comment in enumerate((None, "", "评" * 500, "  清晰 🧪\n反馈  ", " \n\t ")):
        valid = {"code": codes["submit"][index], "ratings": ratings}
        if comment is not None:
            valid["openText"] = comment
        add(f"submit_valid_{index}", "POST", "/api/submissions", 201, payload=valid)
    add("submit_replay", "POST", "/api/submissions", 409, payload=valid, expected={"error.code": "CODE_USED"})
    return cases


def generate_dataset(output, *, seed=SEED, performance_rows=10000):
    if type(performance_rows) is not int or (performance_rows != 0 and performance_rows < 5):
        raise ValueError("performance_rows must be 0 or an integer >= 5")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    output = Path(output).resolve()
    # Even an empty existing directory is refused: no implicit reset or append.
    output.mkdir(parents=True, exist_ok=False)
    db = Database(output / "db")
    db.initialize()
    app = create_app({"TESTING": True, "DATA_DIR": output / "db"})
    auth = app.extensions["taces_auth"]
    admin = auth.bootstrap_admin("demo_admin", PASSWORD)
    admin_token, _ = auth.login(admin["username"], PASSWORD)
    accounts = {"admin": admin}
    for role, username, actual_role in (("teacher", "demo_teacher", "teacher"),
                                         ("other_teacher", "demo_other", "teacher"),
                                         ("auditor", "demo_auditor", "auditor"),
                                         ("disabled", "demo_disabled", "teacher")):
        accounts[role] = auth.create_account(admin_token, username, PASSWORD, actual_role)
    auth.update_account(admin_token, accounts["disabled"]["user_id"], {"is_active": False})
    courses = CourseService(db, auth)
    submissions = SubmissionService(db)
    stats = StatisticsService(db, auth)
    teacher_token, _ = auth.login("demo_teacher", PASSWORD)
    rng = random.Random(seed)
    deadline = int(time.time()) + 30 * 86400
    specs = [
        ("empty", "零份评价", 0, "random", "empty"),
        ("below_k", "门槛前 k-1", 4, "uniform", "mixed"),
        ("at_k", "恰好达到 k", 5, "uniform", "mixed"),
        ("above_k", "超过门槛 k+1", 6, "uniform", "mixed"),
        ("all_low", "全体最低分", 10, "low", "mixed"),
        ("all_high", "全体最高分", 10, "high", "mixed"),
        ("uniform", "五档均匀分布", 25, "uniform", "mixed"),
        ("polarized", "两极分化", 20, "polarized", "mixed"),
        ("random", "随机偏高分样本", 36, "random", "mixed"),
        ("weighted", "不等权维度", 10, "weighted", "mixed"),
        ("one_dimension", "单维度边界", 5, "uniform", "mixed"),
        ("ten_dimensions", "十维度边界", 5, "uniform", "mixed"),
        ("text_empty", "全体不填开放题", 5, "uniform", "empty"),
        ("text_500", "开放题500字", 5, "uniform", "long"),
        ("text_special", "特殊字符与重复词", 10, "uniform", "special"),
        ("budget_empty", "无缓存且预算耗尽", 5, "uniform", "mixed"),
        ("budget_last", "恰够最后一次发布", 5, "uniform", "mixed"),
        ("cache_exhausted", "预算耗尽仍可读缓存", 5, "uniform", "mixed"),
        ("stale_cache", "新增评价后返回旧快照", 5, "uniform", "mixed"),
        ("refresh", "新增评价后重新发布", 5, "uniform", "mixed"),
        ("closed", "已关闭评价窗口", 5, "uniform", "mixed"),
        ("foreign", "另一位教师的课程", 5, "uniform", "mixed"),
        ("validation", "非法请求不消耗评价码", 0, "random", "empty"),
        ("submit_valid", "有效提交与文本边界", 0, "random", "empty"),
    ]
    if performance_rows:
        specs.append(("performance", "大批量性能测试", performance_rows, "random", "mixed"))
    manifest = {"format_version": 1, "synthetic": True, "seed": seed,
                "generated_at": datetime.now(timezone.utc).isoformat(), "valid_until": deadline,
                "database_dir": "db", "policy": {"epsilon": .1, "k": 5, "epsilonTotal": 4},
                "accounts": {role: {"username": account["username"], "password": PASSWORD,
                                    "role": account["role"], "active": role != "disabled"}
                             for role, account in accounts.items()}, "courses": [], "codes": {}}
    truth, spare_codes = {}, {}
    for cid, name, count, pattern, text_pattern in specs:
        teacher = accounts["other_teacher" if cid == "foreign" else "teacher"]
        body = {"course_id": cid, "name": name, "teacher_id": teacher["user_id"],
                "term": "2026秋（合成演示）", "closes_at": deadline}
        if cid == "weighted":
            body["dimensions"] = [{"name": n, "weight": w} for n, w in zip(DEFAULT_DIMENSIONS, [.7, .2, .1])]
        elif cid in {"one_dimension", "ten_dimensions"}:
            size = 1 if cid == "one_dimension" else 10
            body["dimensions"] = [{"name": f"维度{i + 1}", "weight": 1 / size} for i in range(size)]
        courses.create(admin_token, body)
        truth[cid], used = fill_course(db, cid, count, pattern, text_pattern, rng)
        spare_codes[cid] = courses.issue_codes(admin_token, cid, 5 if cid == "submit_valid" else 2)
        if cid == "at_k":
            manifest["codes"]["used"] = used[0]
        expected = {"id": cid, "name": name, "responses": count, "owner": "other_teacher" if cid == "foreign" else "teacher",
                    "state": "unpublished" if count < 5 or cid == "budget_empty" else "published",
                    "charged": count >= 5 and cid not in {"budget_empty", "cache_exhausted", "stale_cache"}}
        if expected["state"] == "unpublished":
            expected["reason"] = "budget_exhausted" if cid == "budget_empty" else "below_threshold"
        manifest["courses"].append(expected)
    with db.transaction() as con:
        con.execute("UPDATE main.budget_ledger SET eps_used_micros=eps_total_micros WHERE course_id='budget_empty'")
        con.execute("UPDATE main.budget_ledger SET eps_total_micros=100000 WHERE course_id IN ('budget_last','cache_exhausted','stale_cache')")
        con.execute("UPDATE main.course_state SET closes_at=? WHERE course_id='closed'", (int(time.time()) - 3600,))
        expired = spare_codes["validation"][1]
        con.execute("UPDATE identity.code_state SET expires_at=? WHERE code_hash=?",
                    (int(time.time()) - 3600, hashlib.sha256(expired.encode("ascii")).hexdigest()))
    for cid in ("cache_exhausted", "stale_cache", "refresh"):
        stats.get(teacher_token, cid)
        if cid != "cache_exhausted":
            submissions.submit({"code": spare_codes[cid][0],
                                "ratings": [{"dimension": n, "score": 3} for n in DEFAULT_DIMENSIONS]})
            # The first five uniform records plus the newly submitted [3,3,3].
            rows = [[score] * 3 for score in range(1, 6)] + [[3] * 3]
            comments = ["", "作业反馈清晰", "节奏实验互动实践例子", "反馈反馈反馈", "🧪 English 示例", ""]
            truth[cid] = truth_for(rows, comments, [1 / 3] * 3)
            for entry in manifest["courses"]:
                if entry["id"] == cid:
                    entry["responses"] = 6
                    if cid == "stale_cache":
                        entry["published_responses"] = 5
    manifest["codes"].update({"valid": spare_codes["validation"][0], "expired": expired,
                               "student_demo": spare_codes["at_k"][0],
                               "closed": spare_codes["closed"][0], "unknown": secrets.token_hex(16),
                               "submit": spare_codes["submit_valid"],
                               "refresh": spare_codes["refresh"][1]})
    # Leave reusable credentials but no seeded live sessions in the demo databases.
    with db.transaction() as con:
        con.execute("DELETE FROM identity.auth_session")
    write_json(output / "ground_truth.json", truth)
    write_json(output / "api_cases.json", build_api_cases(manifest))
    # Manifest is the completion marker; a partially generated folder has none.
    write_json(output / "manifest.json", manifest)
    return manifest


def verify_dataset(output):
    from verify_test_data import verify_dataset as verify
    return verify(Path(output))


def install_demo(output, destination=None):
    """Install verified fixtures into the local demo DB, preserving a backup."""
    output = Path(output).resolve()
    destination = Path(destination).resolve() if destination is not None else PROJECT / "db"
    source = Database(output / "db")
    source.check_ready()
    if destination == source.paths.metadata.parent:
        raise ValueError("Demo destination must differ from the generated database directory")
    files = ("metadata.db", "identity.db", "evaluation.db")
    present = [(destination / name).is_file() for name in files]
    if any(present) and not all(present):
        raise ValueError("Demo destination has an incomplete database; refusing to replace it")
    backup = None
    if all(present):
        backup_root = PROJECT / "tests" / "experiments" / "output" / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix="before-demo-", dir=backup_root))
        # Read all attached DBs first to hold a consistent three-file snapshot.
        current = Database(destination)
        with current.read_current() as con:
            for schema, _ in current.paths.items():
                con.execute(f"SELECT count(*) FROM {schema}.sqlite_master").fetchone()
            for schema, path in current.paths.items():
                with closing(sqlite3.connect(backup / path.name)) as target:
                    con.backup(target, name=schema)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        for name in files:
            shutil.copy2(output / "db" / name, destination / name)
        Database(destination).check_ready()
    except BaseException:
        if backup is not None:
            for name in files:
                shutil.copy2(backup / name, destination / name)
        raise
    return backup


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate comprehensive synthetic TACES test/demo data (never overwrite a dataset).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="new dataset directory; relative paths use the current working directory")
    parser.add_argument("--seed", type=int, default=SEED, help="seed for scores and text, never for privacy noise or capabilities")
    parser.add_argument("--performance-rows", type=int, default=10000, help="performance submissions: 0 to skip, otherwise >= 5")
    parser.add_argument("--check", action="store_true", help="verify real APIs on a temporary copy and save verification.json")
    parser.add_argument("--verify-only", type=Path, help="verify an existing dataset without generating or consuming its codes")
    parser.add_argument("--install-demo", action="store_true", help="verify, back up and replace project/db for local demonstration; stop the demo server first")
    args = parser.parse_args(argv)
    if args.verify_only is not None and args.install_demo:
        parser.error("--verify-only and --install-demo cannot be combined")
    output = args.verify_only if args.verify_only is not None else args.output
    try:
        if args.verify_only is None:
            manifest = generate_dataset(output, seed=args.seed, performance_rows=args.performance_rows)
            print(f"Generated {len(manifest['courses'])} courses: {output}")
        if args.check or args.verify_only is not None or args.install_demo:
            report = verify_dataset(output)
            write_json(output / "verification.json", report)
            print(f"Checks: {report['passed']} passed, {report['failed']} failed")
            for check in report["checks"]:
                if not check["passed"]:
                    print(f"FAIL {check['name']}: {check['detail']}")
            if report["performance_seconds"] is not None:
                print(f"First performance publication: {report['performance_seconds']:.3f}s")
            if report["failed"]:
                return 1
        if args.install_demo:
            backup = install_demo(output)
            print(f"Demo installed in project/db; previous database backup: {backup or 'no previous databases'}")
        return 0
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Test data operation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
