"""Staff authentication with revocable, opaque sessions stored as digests.

All permission checks and writes share a transaction. No Flask dependency.
"""

from contextlib import contextmanager
import hashlib
import hmac
import re
import secrets
import time
from uuid import uuid4

from werkzeug.security import check_password_hash, generate_password_hash

from taces.business.auth.policy import PERMISSIONS, require_course_access, require_permission
from taces.business.errors import ServiceError


PASSWORD_METHOD = "scrypt:32768:8:1"
LOGIN_WINDOW = 900
LOGIN_FAILURE_LIMIT = 5
SESSION_LIMIT = 10


def invalid(message="请求字段不合法。"):
    return ServiceError(400, "INVALID_INPUT", message)


def username_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", value):
        raise invalid("用户名须为 3–64 位英文字母、数字、下划线、点或短横线。")
    return value.lower()


def password_value(value, minimum=12):
    if not isinstance(value, str) or not minimum <= len(value) <= 128:
        raise invalid(f"密码须为 {minimum}–128 个字符。")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise invalid("密码包含无效的 Unicode 字符。") from None
    return value


def token_digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def valid_token(token):
    return isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is not None


def csrf_token(token):
    return hmac.new(token.encode("ascii"), b"taces-csrf", hashlib.sha256).hexdigest()


def public_account(row):
    return {key: bool(row[key]) if key == "is_active" else row[key]
            for key in ("user_id", "username", "role", "is_active", "created_at")}


def audit(connection, actor, action):
    connection.execute(
        "INSERT INTO main.audit_log (log_id, actor, action) VALUES (?, ?, ?)",
        (uuid4().hex, actor, action),
    )


class AuthService:
    def __init__(self, database, session_seconds=28800):
        self.database = database
        self.session_seconds = session_seconds
        # Unknown usernames still incur password verification work.
        self._dummy_hash = generate_password_hash(secrets.token_urlsafe(32), method=PASSWORD_METHOD)

    @staticmethod
    def _authenticate(connection, token):
        row = None
        if valid_token(token):
            row = connection.execute(
                "SELECT a.*, s.expires_at FROM identity.auth_session s "
                "JOIN identity.account a ON a.user_id=s.user_id "
                "WHERE s.token_hash=? AND s.expires_at>? AND a.is_active=1",
                (token_digest(token), int(time.time())),
            ).fetchone()
        if row is None:
            raise ServiceError(401, "UNAUTHENTICATED", "请登录后重试。")
        return row

    @contextmanager
    def _operation(self, token, action, *, write=False):
        try:
            context = self.database.transaction if write else self.database.read_current
            with context() as connection:
                account = self._authenticate(connection, token)
                yield connection, account
        except ServiceError as error:
            if error.status == 403:
                self.record_denial(token, action)
            raise

    def record_denial(self, token, action):
        # Separate from the rejected transaction so rollback cannot erase denials.
        with self.database.transaction() as connection:
            try:
                account = self._authenticate(connection, token)
            except ServiceError:
                return
            audit(connection, account["user_id"], "access.denied:" + action)

    @staticmethod
    def _insert_account(connection, username, password_hash, role, actor):
        if connection.execute(
            "SELECT 1 FROM identity.account WHERE username=?", (username,)
        ).fetchone():
            raise ServiceError(409, "USERNAME_EXISTS", "用户名已存在。")
        user_id = uuid4().hex
        connection.execute(
            "INSERT INTO identity.account "
            "(user_id, username, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, password_hash, role, int(time.time())),
        )
        audit(connection, actor, "account.create:" + user_id)
        return public_account(connection.execute(
            "SELECT * FROM identity.account WHERE user_id=?", (user_id,)
        ).fetchone())

    def bootstrap_admin(self, username, password):
        username = username_value(username)
        password_hash = generate_password_hash(password_value(password), method=PASSWORD_METHOD)
        with self.database.transaction() as connection:
            if connection.execute("SELECT 1 FROM identity.account LIMIT 1").fetchone():
                raise ServiceError(409, "ALREADY_BOOTSTRAPPED", "已有账号，请由管理员管理账号。")
            return self._insert_account(connection, username, password_hash, "admin", "system:bootstrap")

    def login(self, username, password, previous_token=None):
        username = username_value(username)
        password_value(password, minimum=1)
        now = int(time.time())
        key = hashlib.sha256(username.encode("ascii")).hexdigest()
        failed = False
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM identity.login_throttle WHERE window_start<=?", (now - LOGIN_WINDOW,))
            throttle = connection.execute(
                "SELECT failures FROM identity.login_throttle WHERE username_hash=?", (key,)
            ).fetchone()
            if throttle and throttle[0] >= LOGIN_FAILURE_LIMIT:
                raise ServiceError(429, "LOGIN_THROTTLED", "登录失败次数过多，请稍后重试。")
            account = connection.execute(
                "SELECT * FROM identity.account WHERE username=?", (username,)
            ).fetchone()
            matches = check_password_hash(account["password_hash"] if account else self._dummy_hash, password)
            if not matches or account is None or not account["is_active"]:
                connection.execute(
                    "INSERT INTO identity.login_throttle (username_hash, failures, window_start) "
                    "VALUES (?, 1, ?) ON CONFLICT(username_hash) DO UPDATE SET failures=failures+1",
                    (key, now),
                )
                failed = True
            else:
                connection.execute("DELETE FROM identity.login_throttle WHERE username_hash=?", (key,))
                connection.execute("DELETE FROM identity.auth_session WHERE expires_at<=?", (now,))
                if valid_token(previous_token):
                    connection.execute("DELETE FROM identity.auth_session WHERE token_hash=?", (token_digest(previous_token),))
                # Bound live sessions without changing their absolute expiry.
                connection.execute(
                    "DELETE FROM identity.auth_session WHERE token_hash IN "
                    "(SELECT token_hash FROM identity.auth_session WHERE user_id=? "
                    "ORDER BY expires_at DESC, token_hash LIMIT -1 OFFSET ?)",
                    (account["user_id"], SESSION_LIMIT - 1),
                )
                token = secrets.token_urlsafe(32)
                expires_at = now + self.session_seconds
                connection.execute(
                    "INSERT INTO identity.auth_session (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                    (token_digest(token), account["user_id"], expires_at),
                )
                audit(connection, account["user_id"], "auth.login")
                result = {"account": public_account(account), "expires_at": expires_at, "csrf_token": csrf_token(token)}
        # Commit failed-attempt counters before returning the generic error.
        if failed:
            raise ServiceError(401, "INVALID_CREDENTIALS", "用户名或密码不正确。")
        return token, result

    def current(self, token):
        with self._operation(token, "auth.me") as (_, account):
            return {"account": public_account(account), "expires_at": account["expires_at"], "csrf_token": csrf_token(token)}

    def logout(self, token):
        with self._operation(token, "auth.logout", write=True) as (connection, account):
            connection.execute("DELETE FROM identity.auth_session WHERE token_hash=?", (token_digest(token),))
            audit(connection, account["user_id"], "auth.logout")

    def change_password(self, token, current_password, new_password):
        password_value(new_password)
        password_value(current_password, minimum=1)
        with self._operation(token, "auth.password", write=True) as (connection, account):
            if not check_password_hash(account["password_hash"], current_password):
                raise ServiceError(403, "INVALID_CURRENT_PASSWORD", "当前密码不正确。")
            connection.execute("UPDATE identity.account SET password_hash=? WHERE user_id=?", (
                generate_password_hash(new_password, method=PASSWORD_METHOD), account["user_id"],
            ))
            connection.execute("DELETE FROM identity.auth_session WHERE user_id=?", (account["user_id"],))
            audit(connection, account["user_id"], "account.password:" + account["user_id"])

    def list_accounts(self, token, limit=100, offset=0):
        with self._operation(token, "accounts.list") as (connection, account):
            require_permission(account, "accounts:manage")
            return [public_account(row) for row in connection.execute(
                "SELECT * FROM identity.account ORDER BY username LIMIT ? OFFSET ?", (limit, offset)
            )]

    def create_account(self, token, username, password, role):
        with self._operation(token, "accounts.create", write=True) as (connection, account):
            require_permission(account, "accounts:manage")
            username = username_value(username)
            password_value(password)
            if not isinstance(role, str) or role not in PERMISSIONS:
                raise invalid("角色须为 admin、teacher 或 auditor。")
            return self._insert_account(connection, username,
                generate_password_hash(password, method=PASSWORD_METHOD), role, account["user_id"])

    def update_account(self, token, user_id, changes):
        with self._operation(token, "accounts.update", write=True) as (connection, actor):
            require_permission(actor, "accounts:manage")
            if not changes or changes.keys() - {"role", "is_active", "password"}:
                raise invalid()
            target = connection.execute("SELECT * FROM identity.account WHERE user_id=?", (user_id,)).fetchone()
            if target is None:
                raise ServiceError(404, "ACCOUNT_NOT_FOUND", "账号不存在。")
            role = changes.get("role", target["role"])
            active = changes.get("is_active", bool(target["is_active"]))
            if not isinstance(role, str) or role not in PERMISSIONS or type(active) is not bool:
                raise invalid()
            if target["role"] == "admin" and target["is_active"] and (role != "admin" or not active):
                count = connection.execute("SELECT count(*) FROM identity.account WHERE role='admin' AND is_active=1").fetchone()[0]
                if count <= 1:
                    raise ServiceError(409, "LAST_ADMIN", "必须保留至少一个启用的管理员。")
            if target["role"] == "teacher" and role != "teacher" and connection.execute(
                "SELECT 1 FROM main.course WHERE teacher_id=? LIMIT 1", (user_id,)
            ).fetchone():
                raise ServiceError(409, "ROLE_IN_USE", "请先转移该教师的课程，再修改角色。")
            password_hash = target["password_hash"]
            if "password" in changes:
                password_hash = generate_password_hash(password_value(changes["password"]), method=PASSWORD_METHOD)
            connection.execute(
                "UPDATE identity.account SET role=?, is_active=?, password_hash=? WHERE user_id=?",
                (role, int(active), password_hash, user_id),
            )
            connection.execute("DELETE FROM identity.auth_session WHERE user_id=?", (user_id,))
            audit(connection, actor["user_id"], "account.update:" + user_id)
            return public_account(connection.execute("SELECT * FROM identity.account WHERE user_id=?", (user_id,)).fetchone())

    def list_courses(self, token):
        with self._operation(token, "courses.list") as (connection, account):
            if account["role"] == "admin":
                rows = connection.execute("SELECT * FROM main.course ORDER BY course_id")
            else:
                require_permission(account, "courses:own")
                rows = connection.execute("SELECT * FROM main.course WHERE teacher_id=? ORDER BY course_id", (account["user_id"],))
            return [dict(row) for row in rows]

    def get_course(self, token, course_id):
        with self._operation(token, "courses.get") as (connection, account):
            if account["role"] != "admin":
                require_permission(account, "courses:own")
            course = connection.execute("SELECT * FROM main.course WHERE course_id=?", (course_id,)).fetchone()
            if course is None:
                raise ServiceError(404, "COURSE_NOT_FOUND", "课程不存在。")
            require_course_access(account, course)
            return dict(course)
