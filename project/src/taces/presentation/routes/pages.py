"""Browser pages.

These routes render shells only. Every number a page shows comes from `/api`
through `static/js/api.js`, so a page can be built before its endpoint exists
and later swap mock data for the real thing without touching the template.
"""

from flask import Blueprint, render_template

pages = Blueprint("pages", __name__)


@pages.get("/login")
def login():
    return render_template("auth/login.html")
