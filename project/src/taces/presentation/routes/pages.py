"""Browser pages.

These routes render shells only. Every number a page shows comes from `/api`
through `static/js/api.js`, so a page can be built before its endpoint exists
and later swap mock data for the real thing without touching the template.
"""

from flask import Blueprint, render_template

pages = Blueprint("pages", __name__)


@pages.get("/workspace")
def staff_entry():
    # Role-based landing happens in the browser: the session cookie is scoped
    # to /api, so a page route cannot read who is logged in.
    return render_template("entry.html")


@pages.get("/login")
def login():
    return render_template("auth/login.html")


@pages.get("/teacher/<course_id>")
def teacher_board(course_id: str):
    return render_template("teacher/board.html", shell="staff", course_id=course_id)


@pages.get("/teacher/exports/history")
def teacher_exports():
    return render_template("teacher/exports.html", shell="staff")


@pages.get("/student")
@pages.get("/")
def student_code():
    return render_template("student/code.html")


@pages.get("/student/evaluate")
def student_evaluate():
    return render_template("student/evaluate.html")


@pages.get("/admin/accounts")
def admin_accounts():
    return render_template("admin/accounts.html", shell="staff")


@pages.get("/admin/courses")
def admin_courses():
    return render_template("admin/courses.html", shell="staff")


@pages.get("/admin/config")
def admin_config():
    return render_template("admin/config.html", shell="staff")


@pages.get("/admin/audit")
def admin_audit():
    return render_template("admin/audit.html", shell="staff")
