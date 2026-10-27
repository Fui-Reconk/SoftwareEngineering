"""Role-controlled audit projection; no evaluation text or staff secrets."""

from datetime import datetime, time, timedelta, timezone
import re

from taces.business.auth.policy import require_permission
from taces.business.auth.service import invalid
from taces.business.common import identifier
from taces.business.timezone import SHANGHAI, shanghai_stamp


ACTIONS = {"account.create": "创建账号", "account.update": "修改账号", "account.password": "修改密码",
           "auth.login": "登录", "auth.logout": "退出登录", "access.denied": "拒绝访问",
           "course.create": "创建课程", "course.update": "修改课程", "codes.issue": "发行评价码",
           "statistics.publish": "发布统计", "statistics.read": "读取统计", "statistics.refused": "暂缓发布",
           "privacy.configure": "修改隐私参数", "export.csv": "导出CSV", "export.pdf": "导出PDF"}


def date_bound(value, *, end=False):
    try:
        if any(len(digits) > 6 for digits in re.findall(r"[.,]([0-9]+)", value)):
            raise ValueError
        is_date = re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is not None
        if is_date:
            instant = datetime.combine(datetime.fromisoformat(value).date(), time(), SHANGHAI)
            if end:
                instant += timedelta(days=1)
        else:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.tzinfo is None or instant.utcoffset() is None:
                raise ValueError
        return instant.astimezone(timezone.utc), is_date and end
    except (ValueError, OverflowError):
        raise invalid("日期须为有效的本地日期或带时区ISO时间。") from None


def page_number(value, minimum, maximum):
    if not re.fullmatch(r"[0-9]{1,10}", value):
        raise invalid("分页参数不合法。")
    result = int(value)
    if not minimum <= result <= maximum:
        raise invalid("分页参数不合法。")
    return result


def epoch_micros(value):
    """Integer comparison avoids SQLite julianday's millisecond rounding."""
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        delta = instant.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    except (ValueError, OverflowError):
        return None


class AuditService:
    def __init__(self, database, auth):
        self.database = database
        self.auth = auth

    def list(self, token, filters):
        with self.auth._operation(token, "audit.read") as (con, actor):
            require_permission(actor, "audit:read")
            if filters.keys() - {"from", "to", "course", "limit", "offset"}:
                raise invalid()
            limit = page_number(filters.get("limit", "50"), 1, 100)
            offset = page_number(filters.get("offset", "0"), 0, 2**31 - 1)
            start = date_bound(filters["from"])[0] if filters.get("from") else None
            end, exclusive = date_bound(filters["to"], end=True) if filters.get("to") else (None, False)
            if start and end and (start > end or (exclusive and start == end)):
                raise invalid("起始日期不能晚于结束日期。")
            conditions, values = [], []
            con.create_function("audit_micros", 1, epoch_micros, deterministic=True)
            if start:
                conditions.append("audit_micros(l.ts)>=?")
                values.append(epoch_micros(start.isoformat()))
            if end:
                conditions.append("audit_micros(l.ts)" + ("<" if exclusive else "<=") + "?")
                values.append(epoch_micros(end.isoformat()))
            if filters.get("course"):
                conditions.append("l.course_id=?")
                values.append(identifier(filters["course"]))
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            rows = con.execute(
                "SELECT l.*,a.username,c.name FROM main.audit_log l "
                "LEFT JOIN identity.account a ON a.user_id=l.actor "
                "LEFT JOIN main.course c ON c.course_id=l.course_id" + where +
                " ORDER BY audit_micros(l.ts) DESC,l.rowid DESC LIMIT ? OFFSET ?", (*values, limit + 1, offset),
            ).fetchall()
            accounts = {row["user_id"]: row["username"] for row in con.execute("SELECT user_id,username FROM identity.account")}
            entries = []
            for row in rows[:limit]:
                action, _, target = row["action"].partition(":")
                entries.append({"at": shanghai_stamp(row["ts"]),
                    "actor": row["username"] or ("系统" if row["actor"] == "system:bootstrap" else "历史账号"),
                    "action": ACTIONS.get(action, "历史操作"), "target": row["name"] or accounts.get(target, "系统"),
                    "epsCost": row["eps_cost_micros"] / 1_000_000})
            courses = [dict(row) for row in con.execute("SELECT course_id,name FROM main.course ORDER BY course_id")]
            return {"entries": entries, "next": offset + limit if len(rows) > limit else None, "courses": courses}
