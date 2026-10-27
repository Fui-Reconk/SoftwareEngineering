"""Student capability APIs deliberately have no session or CSRF prerequisite."""

from flask import Blueprint, current_app, jsonify

from taces.business.submission.service import SubmissionService
from .auth import payload


submissions = Blueprint("submissions", __name__)


def submission_service():
    return SubmissionService(current_app.extensions["taces_database"])


@submissions.post("/evaluation-codes/verify")
def verify_code():
    body = payload({"code"})
    return jsonify(data=submission_service().verify(body["code"]))


@submissions.post("/submissions")
def submit_evaluation():
    body = payload({"code", "ratings"}, {"openText"})
    return jsonify(data=submission_service().submit(body)), 201
