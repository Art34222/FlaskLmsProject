import os
import uuid

from flask import (
    Blueprint, request, redirect, url_for, session, flash,
    send_from_directory, current_app,
)
from werkzeug.utils import secure_filename

from database.db import query_one, execute
from utils.decorators import login_required, role_required

files_bp = Blueprint("files", __name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "txt", "png", "jpg", "jpeg", "zip", "py"}


def _get_extension(filename: str) -> str | None:
    """Возвращает расширение в нижнем регистре или None."""
    if not filename or "." not in filename:
        return None
    return filename.rsplit(".", 1)[1].lower()


def _safe_save(file):
    """
    Санитизирует имя, проверяет расширение на уже очищенном имени,
    сохраняет файл под уникальным именем.
    Возвращает (оригинальное имя, уникальное имя на диске).
    При некорректном имени/расширении бросает ValueError.
    """
    original = secure_filename(file.filename) or ""
    ext = _get_extension(original)
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise ValueError("bad filename or extension")
    unique = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique)
    file.save(path)
    return original, unique


def _user_owns_lesson(lesson_id) -> bool:
    """Проверка, что текущий учитель владеет курсом, к которому привязан урок."""
    if session.get("role") == "admin":
        return True
    row = query_one("""
                    SELECT c.teacher_id
                    FROM lessons l
                             JOIN courses c ON c.id = l.course_id
                    WHERE l.id = ?
                    """, (lesson_id,))
    return bool(row) and row["teacher_id"] == session.get("user_id")


def _user_can_access_lesson(lesson_id) -> bool:
    """Может ли текущий пользователь скачивать файлы этого урока."""
    role = session.get("role")
    if role == "admin":
        return True
    if role == "teacher":
        return _user_owns_lesson(lesson_id)
    if role == "student":
        row = query_one("""
                        SELECT e.id
                        FROM lessons l
                                 JOIN enrollments e ON e.course_id = l.course_id
                        WHERE l.id = ?
                          AND e.user_id = ?
                        """, (lesson_id, session.get("user_id")))
        return row is not None
    return False


def _student_enrolled_for_task(task_id) -> bool:
    row = query_one("""
                    SELECT e.id
                    FROM tasks t
                             JOIN lessons l ON l.id = t.lesson_id
                             JOIN enrollments e ON e.course_id = l.course_id
                    WHERE t.id = ?
                      AND e.user_id = ?
                    """, (task_id, session.get("user_id")))
    return row is not None


# ── Загрузка файла к уроку (учитель) ─────────────────────────────

@files_bp.route("/lesson/<int:lesson_id>/upload", methods=["POST"])
@role_required("teacher", "admin")
def upload_to_lesson(lesson_id):
    lesson = query_one("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
    if not lesson:
        flash("Урок не найден.", "danger")
        return redirect(url_for("courses.course_list"))

    if not _user_owns_lesson(lesson_id):
        flash("Нет прав на загрузку файлов в этот урок.", "danger")
        return redirect(url_for("courses.course_list"))

    file = request.files.get("file")

    if not file or not file.filename:
        flash("Файл не выбран.", "danger")
        return redirect(url_for("courses.course_detail", course_id=lesson["course_id"]))

    if len(file.filename) > 255:
        flash("Имя файла слишком длинное (максимум 255 символов).", "danger")
        return redirect(url_for("courses.course_detail", course_id=lesson["course_id"]))

    try:
        orig_name, stored_name = _safe_save(file)
    except ValueError:
        flash("Некорректное имя файла или недопустимый формат.", "danger")
        return redirect(url_for("courses.course_detail", course_id=lesson["course_id"]))

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

    # Проверка доступа: студент должен быть записан, учитель — владеть курсом
    if not _user_can_access_lesson(f["lesson_id"]):
        flash("Нет доступа к этому файлу.", "danger")
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

    # Сначала проверка доступа, потом все остальные проверки.
    # Иначе студент может энумерейтить id заданий и узнавать их типы.
    if not _student_enrolled_for_task(task_id):
        flash("Нет доступа к этому заданию.", "danger")
        return redirect(url_for("courses.course_list"))

    # Файлы — только для open-заданий
    if task["task_type"] != "open":
        flash("Файлы можно загружать только к заданиям с развёрнутым ответом.", "danger")
        return redirect(url_for("tasks.task_detail", task_id=task_id))

    file = request.files.get("file")
    if not file or not file.filename:
        flash("Файл не выбран.", "danger")
        return redirect(url_for("tasks.task_detail", task_id=task_id))

    if len(file.filename) > 255:
        flash("Имя файла слишком длинное (максимум 255 символов).", "danger")
        return redirect(url_for("tasks.task_detail", task_id=task_id))

    try:
        _, stored_name = _safe_save(file)
    except ValueError:
        flash("Некорректное имя файла или недопустимый формат.", "danger")
        return redirect(url_for("tasks.task_detail", task_id=task_id))

    execute(
        "INSERT INTO submissions (task_id, student_id, file_path) VALUES (?, ?, ?)",
        (task_id, session["user_id"], stored_name),
    )
    flash("Решение загружено.", "success")
    return redirect(url_for("tasks.task_detail", task_id=task_id))
