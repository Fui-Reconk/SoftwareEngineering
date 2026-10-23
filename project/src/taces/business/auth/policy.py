"""Explicit role permissions, reusable by subsequent business services."""

from taces.business.errors import ServiceError


PERMISSIONS = {
    "admin": frozenset({"accounts:manage", "courses:manage", "audit:read", "privacy:configure"}),
    "teacher": frozenset({"courses:own", "statistics:own", "exports:own"}),
    "auditor": frozenset({"audit:read"}),
}


def require_permission(account, permission: str) -> None:
    if permission not in PERMISSIONS.get(account["role"], ()):
        raise ServiceError(403, "FORBIDDEN", "当前账号无权执行此操作。")


def require_course_access(account, course) -> None:
    """Course metadata access only; this does not grant statistics access."""
    if account["role"] == "admin":
        return
    require_permission(account, "courses:own")
    if course["teacher_id"] != account["user_id"]:
        raise ServiceError(403, "FORBIDDEN", "只能访问本人所授课程。")
