from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database.db import query_one, query_all, execute
from utils.decorators import login_required, role_required

courses_bp = Blueprint("courses", __name__)


# ── Список курсов ────────────────────────────────────────────────

@courses_bp.route("/")
@login_required
def course_list():
    if session["role"] == "teacher":
        courses = query_all(
            "SELECT * FROM courses WHERE teacher_id = ? ORDER BY created_at DESC",
            (session["user_id"],),
        )
    elif session["role"] == "admin":
        courses = query_all("SELECT * FROM courses ORDER BY created_at DESC")
    else:
        # Студент видит курсы, на которые записан
        courses = query_all("""
            SELECT c.* FROM courses c
            JOIN enrollments e ON e.course_id = c.id
            WHERE e.user_id = ?
            ORDER BY c.created_at DESC
        """, (session["user_id"],))

    all_courses = query_all("SELECT * FROM courses ORDER BY created_at DESC")
    return render_template("courses/list.html", courses=courses, all_courses=all_courses)


# ── Создание курса ───────────────────────────────────────────────

@courses_bp.route("/new", methods=["GET", "POST"])
@role_required("teacher", "admin")
def create_course():
    if request.method == "GET":
        return render_template("courses/create.html")

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()

    if not title:
        flash("Название курса обязательно.", "danger")
        return redirect(url_for("courses.create_course"))

    execute(
        "INSERT INTO courses (title, description, teacher_id) VALUES (?, ?, ?)",
        (title, description, session["user_id"]),
    )
    flash("Курс создан!", "success")
    return redirect(url_for("courses.course_list"))


# ── Просмотр курса с уроками ────────────────────────────────────

@courses_bp.route("/<int:course_id>")
@login_required
def course_detail(course_id):
    course = query_one("SELECT * FROM courses WHERE id = ?", (course_id,))
    if not course:
        flash("Курс не найден.", "danger")
        return redirect(url_for("courses.course_list"))

    lessons = query_all(
        "SELECT * FROM lessons WHERE course_id = ? ORDER BY position",
        (course_id,),
    )
    return render_template("courses/detail.html", course=course, lessons=lessons)


# ── Запись на курс (для студентов) ───────────────────────────────

@courses_bp.route("/<int:course_id>/enroll", methods=["POST"])
@role_required("student")
def enroll(course_id):
    existing = query_one(
        "SELECT id FROM enrollments WHERE user_id = ? AND course_id = ?",
        (session["user_id"], course_id),
    )
    if existing:
        flash("Вы уже записаны на этот курс.", "info")
    else:
        execute(
            "INSERT INTO enrollments (user_id, course_id) VALUES (?, ?)",
            (session["user_id"], course_id),
        )
        flash("Вы записались на курс!", "success")
    return redirect(url_for("courses.course_detail", course_id=course_id))


# ── Добавление урока ─────────────────────────────────────────────

@courses_bp.route("/<int:course_id>/lessons/new", methods=["GET", "POST"])
@role_required("teacher", "admin")
def create_lesson(course_id):
    course = query_one("SELECT * FROM courses WHERE id = ?", (course_id,))
    if not course:
        flash("Курс не найден.", "danger")
        return redirect(url_for("courses.course_list"))

    if request.method == "GET":
        return render_template("courses/create_lesson.html", course=course)

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    max_pos = query_one(
        "SELECT COALESCE(MAX(position), 0) AS mp FROM lessons WHERE course_id = ?",
        (course_id,),
    )
    execute(
        "INSERT INTO lessons (course_id, title, content, position) VALUES (?, ?, ?, ?)",
        (course_id, title, content, (max_pos["mp"] or 0) + 1),
    )
    flash("Урок добавлен!", "success")
    return redirect(url_for("courses.course_detail", course_id=course_id))
