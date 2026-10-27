"""Atomic, budgeted publication of immutable aggregate snapshots."""

import json
import math
from uuid import uuid4

from taces.business.auth.policy import require_course_access, require_permission
from taces.business.common import course_row, identifier, write_audit
from taces.business.errors import ServiceError
from taces.business.privacy.mechanism import VOCABULARY, release
from taces.business.timezone import shanghai_stamp, utc_stamp


def aggregate(connection, course_id, dimensions):
    rows = connection.execute(
        "SELECT r.submission_id,r.dim_id,r.score,t.content FROM evaluation.rating r "
        "LEFT JOIN evaluation.open_text t ON t.rating_id=r.rating_id WHERE r.course_id=?",
        (course_id,),
    )
    submissions = {}
    for row in rows:
        scores, texts = submissions.setdefault(row["submission_id"], ({}, []))
        scores[row["dim_id"]] = row["score"]
        if row["content"]:
            texts.append(row["content"])
    expected = {dim["dim_id"] for dim in dimensions}
    if not expected or any(set(scores) != expected for scores, _ in submissions.values()):
        raise ServiceError(409, "COURSE_NOT_CONFIGURED", "课程评价维度不完整，请联系管理员。")
    n = len(submissions)
    totals = {dim_id: 0 for dim_id in expected}
    histogram = [0] * 5
    word_counts = [0] * len(VOCABULARY)
    text_count = 0
    for scores, texts in submissions.values():
        for dim_id, score in scores.items():
            totals[dim_id] += score
        bucket = min(5, max(1, math.floor(sum(scores.values()) / len(scores) + .5)))
        histogram[bucket - 1] += 1
        if texts:
            text_count += 1
            # Cap contribution per submission, including legacy multi-row texts.
            words = [i for i, word in enumerate(VOCABULARY) if any(word in text for text in texts)][:3]
            for i in words:
                word_counts[i] += 1
    return ([totals[dim["dim_id"]] / n for dim in dimensions], histogram, word_counts, text_count)


class StatisticsService:
    def __init__(self, database, auth):
        self.database = database
        self.auth = auth

    def get(self, token, course_id):
        course_id = identifier(course_id)
        with self.auth._operation(token, "statistics.read", write=True) as (con, actor):
            require_permission(actor, "statistics:own")
            course = course_row(con, course_id)
            require_course_access(actor, course)
            policy = con.execute("SELECT * FROM main.privacy_policy WHERE singleton=1").fetchone()
            state = con.execute("SELECT * FROM main.course_state WHERE course_id=?", (course_id,)).fetchone()
            ledger = con.execute("SELECT * FROM main.budget_ledger WHERE course_id=?", (course_id,)).fetchone()
            if policy is None or state is None or ledger is None:
                raise ServiceError(409, "COURSE_NOT_CONFIGURED", "课程发布配置不完整。")
            remaining = ledger["eps_total_micros"] - ledger["eps_used_micros"]
            cost = policy["epsilon_micros"]
            cached = con.execute(
                "SELECT payload FROM main.agg_result WHERE course_id=? AND data_version=? AND policy_revision=?",
                (course_id, state["data_version"], policy["revision"]),
            ).fetchone()
            previous = cached or con.execute(
                "SELECT payload FROM main.agg_result WHERE course_id=? ORDER BY rowid DESC LIMIT 1", (course_id,),
            ).fetchone()
            if cached:
                return self._saved(con, actor, course, cached, remaining < cost)
            n = con.execute("SELECT count(DISTINCT submission_id) FROM evaluation.rating WHERE course_id=?", (course_id,)).fetchone()[0]
            if n < policy["threshold"] or remaining < cost:
                if previous:
                    return self._saved(con, actor, course, previous, remaining < cost)
                write_audit(con, actor["user_id"], "statistics.refused", course_id=course_id)
                return {"state": "unpublished", "reason": "below_threshold" if n < policy["threshold"] else "budget_exhausted",
                        "sample": n, "threshold": policy["threshold"], "shortfall": max(0, policy["threshold"] - n), "charged": False}
            dimensions = con.execute("SELECT * FROM main.dimension WHERE course_id=? ORDER BY rowid", (course_id,)).fetchall()
            means, hist, words, texts = aggregate(con, course_id, dimensions)
            result = release(means, hist, words, texts, n, [row["weight"] for row in dimensions], cost / 1_000_000)
            published_at = utc_stamp()
            data = {"state": "published", "publicationId": uuid4().hex,
                    "courseCode": course_id, "courseTitle": course["name"], "term": course["term"],
                    "responses": n,
                    "enrolled": con.execute("SELECT count(*) FROM identity.enroll_code WHERE course_id=?", (course_id,)).fetchone()[0],
                    "publishedAt": shanghai_stamp(published_at),
                    "dimensions": [{"name": row["name"], "value": value} for row, value in zip(dimensions, result.pop("values"))],
                    **result}
            changed = con.execute(
                "UPDATE main.budget_ledger SET eps_used_micros=eps_used_micros+?,updated_at=? "
                "WHERE course_id=? AND eps_used_micros+?<=eps_total_micros", (cost, published_at, course_id, cost),
            ).rowcount
            if changed != 1:
                raise ServiceError(409, "BUDGET_EXHAUSTED", "课程隐私预算已耗尽。")
            con.execute("INSERT INTO main.agg_result (publication_id,course_id,data_version,policy_revision,payload,published_at) VALUES (?,?,?,?,?,?)",
                        (data["publicationId"], course_id, state["data_version"], policy["revision"], json.dumps(data, ensure_ascii=False), published_at))
            write_audit(con, actor["user_id"], "statistics.publish", course_id=course_id, eps_cost_micros=cost)
            return {**data, "charged": True, "budgetExhausted": remaining - cost < cost}

    @staticmethod
    def _saved(con, actor, course, saved, exhausted):
        write_audit(con, actor["user_id"], "statistics.read", course_id=course["course_id"])
        return {**json.loads(saved["payload"]), "charged": False, "budgetExhausted": exhausted}
