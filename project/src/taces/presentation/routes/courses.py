"""Administrator course management; course listing keeps its existing shape."""

from flask import Blueprint, current_app, jsonify

from taces.business.courses.service import CourseService
from .auth import payload, protected, token


courses_admin = Blueprint("courses_admin", __name__)


def course_service():
    return CourseService(current_app.extensions["taces_database"], current_app.extensions["taces_auth"])


@courses_admin.get("/admin/courses")
@protected()
def list_courses_for_management():
    return jsonify(data={"courses": course_service().list_for_management(token())})


@courses_admin.post("/admin/courses")
@protected(write=True)
def create_course():
    body = payload({"course_id", "name", "teacher_id", "term"}, {"dimensions", "closes_at"})
    return jsonify(data={"course": course_service().create(token(), body)}), 201


@courses_admin.patch("/admin/courses/<course_id>")
@protected(write=True)
def update_course(course_id):
    body = payload(set(), {"name", "teacher_id", "term", "closes_at"})
    return jsonify(data={"course": course_service().update(token(), course_id, body)})


@courses_admin.post("/admin/courses/<course_id>/evaluation-codes")
@protected(write=True)
def issue_codes(course_id):
    body = payload({"count"}, {"expires_at"})
    return jsonify(data={"codes": course_service().issue_codes(token(), course_id, body["count"], body.get("expires_at"))}), 201
