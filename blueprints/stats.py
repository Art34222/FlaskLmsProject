from flask import Blueprint, render_template, request, Response, session
from database.db import query_all
from utils.decorators import login_required
from services.grading_service import get_leaderboard
from services.report_service import generate_csv, generate_xlsx, generate_pdf_html

stats_bp = Blueprint("stats", __name__)


@stats_bp.route("/leaderboard")
@login_required
def leaderboard():
    course_id = request.args.get("course_id", type=int)
    courses = query_all("SELECT id, title FROM courses ORDER BY title")
    board = get_leaderboard(course_id)
    return render_template(
        "stats/leaderboard.html",
        board=board, courses=courses, selected_course=course_id,
    )


@stats_bp.route("/report/csv")
@login_required
def report_csv():
    course_id = request.args.get("course_id", type=int)
    csv_data = generate_csv(course_id)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=report.csv"},
    )


@stats_bp.route("/report/xlsx")
@login_required
def report_xlsx():
    course_id = request.args.get("course_id", type=int)
    data = generate_xlsx(course_id)
    return Response(
        data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=report.xlsx"},
    )


@stats_bp.route("/report/pdf")
@login_required
def report_pdf():
    """
    Генерация PDF. Если wkhtmltopdf установлен — отдаём PDF,
    иначе — отдаём HTML как fallback.
    """
    course_id = request.args.get("course_id", type=int)
    html = generate_pdf_html(course_id)

    try:
        import pdfkit
        pdf = pdfkit.from_string(html, False)
        return Response(
            pdf,
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=report.pdf"},
        )
    except Exception:
        # wkhtmltopdf не установлен — отдаём HTML
        return Response(html, mimetype="text/html")
