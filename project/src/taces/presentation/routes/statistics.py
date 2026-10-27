"""Teacher-owned statistics; publication is serialized by the service."""

from flask import Blueprint, current_app, jsonify

from taces.business.stats.service import StatisticsService
from .auth import protected, service, token


statistics = Blueprint("statistics", __name__)


@statistics.get("/courses/<course_id>/statistics")
@protected()
def course_statistics(course_id):
    stats = StatisticsService(current_app.extensions["taces_database"], service())
    return jsonify(data=stats.get(token(), course_id))
