import os
import uuid
from flask import (
    Blueprint, request, redirect, url_for, session, flash,
    send_from_directory, current_app,
)
from database.db import query_one, execute
from utils.decorators import login_required, role_required

files_bp = Blueprint("files", __name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "txt", "png", "jpg", "jpeg", "zip", "py"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _safe_save(file):
    """Сохраняет файл с уникальным именем, возвращает (оригинальное имя, путь)."""
    ext = file.filename.rsplit(".", 1)[1].lower()
    unique = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique)
    file.save(path)
    return file.filename, unique


# ── Загрузка файла к уроку (учитель) ─────────────────────────────

@files_bp.route("/lesson/<int:lesson_id>/upload", methods=["POST"])
@role_required("teacher", "admin")
def upload_to_lesson(lesson_id):
    lesson = query_one("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
    if not lesson:
        flash("Урок не найден.", "danger")
        return redirect(url_for("courses.course_list"))

    file = request.files.get("file")
    if not file or not _allowed(file.filename):
        flash("Недопустимый файл.", "danger")
        return redirect(url_for("courses.course_detail", course_id=lesson["course_id"]))

    orig_name, stored_name = _safe_save(file)
    execute(
        "INSERT INTO lesson_files (lesson_id, filename, filepath) VALUES (?, ?, ?)",
        (lesson_id, orig_name, stored_name),
    )
    flash("Файл загружен.", "success")
    return redirect(url_for("courses.course_detail", course_id=lesson["course_id"]))


# ── Скачивание файла ─────────────────────────────────────────────

@files_bp.route("/download/<int:file_id>")
@login_required
def download_file(file_id):
    f = query_one("SELECT * FROM lesson_files WHERE id = ?", (file_id,))
    if not f:
        flash("Файл не найден.", "danger")
        return redirect(url_for("courses.course_list"))

    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        f["filepath"],
        download_name=f["filename"],
        as_attachment=True,
    )


# ── Загрузка файла-решения (студент) ─────────────────────────────

@files_bp.route("/task/<int:task_id>/submit-file", methods=["POST"])
@role_required("student")
def upload_submission_file(task_id):
    task = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        flash("Задание не найдено.", "danger")
        return redirect(url_for("courses.course_list"))

    file = request.files.get("file")
    if not file or not _allowed(file.filename):
        flash("Недопустимый файл.", "danger")
        return redirect(url_for("tasks.task_detail", task_id=task_id))

    _, stored_name = _safe_save(file)
    execute(
        "INSERT INTO submissions (task_id, student_id, file_path) VALUES (?, ?, ?)",
        (task_id, session["user_id"], stored_name),
    )
    flash("Решение загружено.", "success")
    return redirect(url_for("tasks.task_detail", task_id=task_id))
