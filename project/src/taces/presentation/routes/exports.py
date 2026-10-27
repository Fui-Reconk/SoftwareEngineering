"""Download a teacher-owned saved publication."""

from io import BytesIO

from flask import Blueprint, current_app, request, send_file

from taces.business.auth.service import invalid
from taces.business.export.service import ExportService
from .auth import protected, service, token


exports = Blueprint("exports", __name__)


@exports.get("/courses/<course_id>/export")
@protected()
def export_course(course_id):
    if set(request.args) - {"format", "publication"} or any(len(request.args.getlist(key)) != 1 for key in request.args):
        raise invalid()
    format = request.args.get("format", "csv")
    content, filename = ExportService(current_app.extensions["taces_database"], service()).get(
        token(), course_id, format, request.args.get("publication"))
    return send_file(BytesIO(content), mimetype="text/csv" if format == "csv" else "application/pdf",
                     as_attachment=True, download_name=filename, max_age=0, etag=False)
