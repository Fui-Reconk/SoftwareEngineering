"""Export only saved publications; this module never computes private aggregates."""

import csv
import hashlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
from threading import RLock
from xml.sax.saxutils import escape

from taces.business.auth.policy import require_course_access, require_permission
from taces.business.auth.service import invalid
from taces.business.common import course_row, identifier, write_audit
from taces.business.errors import ServiceError


PDF_LOCK = RLock()
LABELS = {"publicationId": "发布编号", "courseCode": "课程编号", "courseTitle": "课程名称", "term": "学期",
          "publishedAt": "发布时间", "responses": "参与份数（公开）", "enrolled": "发行码数（公开）",
          "pooledMean": "加权均分", "interval": "同时噪声误差界", "spread": "维度差距", "distinguishable": "是否可区分"}


def snapshot_rows(data):
    rows = [(key, data[key]) for key in LABELS]
    rows.extend(("dimension:" + row["name"], row["value"]) for row in data["dimensions"])
    rows.extend(("score:" + str(row["score"]), row["count"]) for row in data["distribution"])
    rows.append(("openText.responses", data["openText"]["responses"]))
    rows.extend(("term:" + row["word"], row["count"]) for row in data["openText"]["terms"])
    return rows


def csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def render_csv(data):
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(("指标", "值"))
    for key, value in snapshot_rows(data):
        writer.writerow((csv_cell(key), csv_cell(value)))
    return buffer.getvalue().encode("utf-8-sig")


def pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    configured = os.environ.get("TACES_PDF_FONT")
    windows = os.environ.get("WINDIR")
    path = Path(configured).expanduser() if configured else (Path(windows) / "Fonts" / "simsun.ttc" if windows else None)
    if configured and not path.is_file():
        raise RuntimeError("Configured PDF font is unavailable")
    if path and path.is_file():
        name = "TacesCJK" + hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=0))
        return name
    name = "STSong-Light"
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(name))
    return name


def render_pdf(data):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    with PDF_LOCK:
        font = pdf_font()
        body = ParagraphStyle("snapshot", fontName=font, fontSize=10, leading=15, wordWrap="CJK")
        title = ParagraphStyle("heading", parent=body, fontSize=19, leading=26, spaceAfter=14)
        rows = [[Paragraph("指标", body), Paragraph("发布值", body)]]
        for key, value in snapshot_rows(data):
            label = LABELS.get(key)
            if label is None:
                if key.startswith("dimension:"):
                    label = "维度：" + key.removeprefix("dimension:")
                elif key.startswith("score:"):
                    label = "评分档：" + key.removeprefix("score:")
                elif key.startswith("term:"):
                    label = "词频：" + key.removeprefix("term:")
                else:
                    label = "开放题噪声份数"
            rows.append([Paragraph(escape(label), body), Paragraph(escape(str(value)), body)])
        table = Table(rows, colWidths=[170, 340], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eff4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#c8d2db")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=42, rightMargin=42,
                                topMargin=40, bottomMargin=40, title="TACES课程评价发布快照", author="TACES")
        story = [Paragraph("TACES 课程评价发布快照", title),
                 Paragraph("本文件复用已发布快照，导出不重新采样、不扣隐私预算。", body), Spacer(1, 12), table, Spacer(1, 12),
                 Paragraph("评分、分布和词频经过噪声处理。精确参与数为公开信息。区间表示90%同时噪声误差界，不是总体抽样置信区间。", body)]
        doc.build(story)
        return buffer.getvalue()


class ExportService:
    def __init__(self, database, auth):
        self.database = database
        self.auth = auth

    def get(self, token, course_id, format="csv", publication=None):
        course_id = identifier(course_id)
        if format not in ("csv", "pdf"):
            raise invalid("导出格式须为csv或pdf。")
        if publication is not None:
            if not isinstance(publication, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", publication):
                raise invalid("发布编号不合法。")
            publication = publication.lower()
        with self.auth._operation(token, "exports.read", write=True) as (con, actor):
            require_permission(actor, "exports:own")
            require_course_access(actor, course_row(con, course_id))
            query = "SELECT publication_id,payload FROM main.agg_result WHERE course_id=?"
            values = [course_id]
            if publication is not None:
                query += " AND publication_id=?"
                values.append(publication)
            saved = con.execute(query + " ORDER BY rowid DESC LIMIT 1", values).fetchone()
            if saved is None:
                if publication is not None:
                    raise ServiceError(404, "PUBLICATION_NOT_FOUND", "发布快照不存在。")
                raise ServiceError(409, "NOT_PUBLISHED", "课程尚未发布统计。")
            data = json.loads(saved["payload"])
            content = render_csv(data) if format == "csv" else render_pdf(data)
            write_audit(con, actor["user_id"], "export." + format, course_id=course_id)
            return content, "statistics-" + saved["publication_id"] + "." + format
