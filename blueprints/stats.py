from flask import Blueprint, render_template, request, Response, session, flash, redirect, url_for, abort

from database.db import query_one, query_all
from services.grading_service import get_leaderboard
from services.report_service import generate_csv, generate_xlsx, generate_pdf_html
from utils.decorators import login_required, role_required

stats_bp = Blueprint("stats", __name__)


def _user_can_access_course_stats(course_id: int) -> bool:
    """
    Кто имеет право смотреть статистику курса:
      admin   — любой курс;
      teacher — только свой курс;
      student — только курсы, на которые записан.
    """
    if not course_id:
        return False
    role = session.get("role")
    user_id = session.get("user_id")

    if role == "admin":
        return query_one("SELECT 1 FROM courses WHERE id = ?", (course_id,)) is not None
    if role == "teacher":
        return query_one(
            "SELECT 1 FROM courses WHERE id = ? AND teacher_id = ?",
            (course_id, user_id),
        ) is not None
    if role == "student":
        return query_one(
            "SELECT 1 FROM enrollments WHERE user_id = ? AND course_id = ?",
            (user_id, course_id),
        ) is not None
    return False


def _courses_visible_to_user():
    """Список курсов для селекта в UI — только те, к которым есть доступ."""
    role = session.get("role")
    user_id = session.get("user_id")

    if role == "admin":
        return query_all("SELECT id, title FROM courses ORDER BY title")
    if role == "teacher":
        return query_all(
            "SELECT id, title FROM courses WHERE teacher_id = ? ORDER BY title",
            (user_id,),
        )
    if role == "student":
        return query_all("""
                         SELECT c.id, c.title
                         FROM courses c
                                  JOIN enrollments e ON e.course_id = c.id
                         WHERE e.user_id = ?
                         ORDER BY c.title
                         """, (user_id,))
    return []


@stats_bp.route("/leaderboard")
@login_required
def leaderboard():
    course_id = request.args.get("course_id", type=int)
    role = session.get("role")

    # Общий лидерборд (без course_id) — только админ.
    # Остальным — пустой экран с просьбой выбрать курс из списка.
    if course_id is None:
        if role != "admin":
            courses = _courses_visible_to_user()
            return render_template(
                "stats/leaderboard.html",
                board=[], courses=courses, selected_course=None,
            )
        board = get_leaderboard(None)
    else:
        if not _user_can_access_course_stats(course_id):
            flash("Нет доступа к статистике этого курса.", "danger")
            return redirect(url_for("stats.leaderboard"))
        board = get_leaderboard(course_id)

    courses = _courses_visible_to_user()
    return render_template(
        "stats/leaderboard.html",
        board=board, courses=courses, selected_course=course_id,
    )


# ── Отчёты — только для учителей и админа ───────────────────────

def _check_report_access(course_id):
    """Проверка прав на выгрузку отчёта. Отбивает 403 если доступа нет."""
    if course_id is None:
        # Общий отчёт по всей системе — только админ
        if session.get("role") != "admin":
            abort(403)
        return
    if not _user_can_access_course_stats(course_id):
        abort(403)


@stats_bp.route("/report/csv")
@role_required("teacher", "admin")
def report_csv():
    course_id = request.args.get("course_id", type=int)
    _check_report_access(course_id)
    csv_data = generate_csv(course_id)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=report.csv"},
    )


@stats_bp.route("/report/xlsx")
@role_required("teacher", "admin")
def report_xlsx():
    course_id = request.args.get("course_id", type=int)
    _check_report_access(course_id)
    data = generate_xlsx(course_id)
    return Response(
        data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=report.xlsx"},
    )


@stats_bp.route("/report/pdf")
@role_required("teacher", "admin")
def report_pdf():
    """
    Генерация PDF. Если wkhtmltopdf установлен — отдаём PDF,
    иначе — отдаём HTML как fallback.
    """
    course_id = request.args.get("course_id", type=int)
    _check_report_access(course_id)
    html = generate_pdf_html(course_id)

    try:
        import pdfkit
        pdf = pdfkit.from_string(html, False)
        return Response(
            pdf,
            mimetype="application/pdf",
            headers={"Content-Disposition": "inline; filename=report.pdf"},
        )
    except (ImportError, OSError):
        return Response(html, mimetype="text/html")
