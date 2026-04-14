from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database.db import query_one, query_all, execute
from utils.decorators import login_required, role_required
from services.grading_service import auto_check_test

tasks_bp = Blueprint("tasks", __name__)


# ── Создание задания ─────────────────────────────────────────────

@tasks_bp.route("/lesson/<int:lesson_id>/new", methods=["GET", "POST"])
@role_required("teacher", "admin")
def create_task(lesson_id):
    lesson = query_one("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
    if not lesson:
        flash("Урок не найден.", "danger")
        return redirect(url_for("courses.course_list"))

    if request.method == "GET":
        return render_template("tasks/create.html", lesson=lesson)

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    task_type = request.form.get("task_type", "test")
    correct_answer = request.form.get("correct_answer", "").strip() or None
    max_score = int(request.form.get("max_score", 10))

    max_pos = query_one(
        "SELECT COALESCE(MAX(position), 0) AS mp FROM tasks WHERE lesson_id = ?",
        (lesson_id,),
    )
    task_id = execute(
        """INSERT INTO tasks (lesson_id, title, description, task_type,
           correct_answer, max_score, position) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (lesson_id, title, description, task_type, correct_answer,
         max_score, (max_pos["mp"] or 0) + 1),
    )

    # Если тест — добавляем варианты ответов
    if task_type == "test":
        options = request.form.getlist("options")
        correct_indices = request.form.getlist("correct_options")  # индексы правильных
        for i, label in enumerate(options):
            if label.strip():
                execute(
                    "INSERT INTO task_options (task_id, label, is_correct) VALUES (?, ?, ?)",
                    (task_id, label.strip(), 1 if str(i) in correct_indices else 0),
                )

    flash("Задание создано!", "success")
    return redirect(url_for("courses.course_detail", course_id=lesson["course_id"]))


# ── Просмотр задания + форма ответа ──────────────────────────────

@tasks_bp.route("/<int:task_id>")
@login_required
def task_detail(task_id):
    task = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        flash("Задание не найдено.", "danger")
        return redirect(url_for("courses.course_list"))

    options = query_all("SELECT * FROM task_options WHERE task_id = ?", (task_id,))
    lesson = query_one("SELECT * FROM lessons WHERE id = ?", (task["lesson_id"],))

    # Предыдущий ответ студента (если есть)
    submission = query_one(
        "SELECT * FROM submissions WHERE task_id = ? AND student_id = ? ORDER BY submitted_at DESC",
        (task_id, session.get("user_id")),
    )
    return render_template(
        "tasks/detail.html",
        task=task, options=options, lesson=lesson, submission=submission,
    )


# ── Отправка ответа ──────────────────────────────────────────────

@tasks_bp.route("/<int:task_id>/submit", methods=["POST"])
@role_required("student")
def submit_answer(task_id):
    task = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        flash("Задание не найдено.", "danger")
        return redirect(url_for("courses.course_list"))

    answer = request.form.get("answer", "").strip()

    sub_id = execute(
        "INSERT INTO submissions (task_id, student_id, answer) VALUES (?, ?, ?)",
        (task_id, session["user_id"], answer),
    )

    # Автопроверка для тестов
    if task["task_type"] == "test":
        score = auto_check_test(sub_id)
        if score is not None:
            flash(f"Автопроверка: {score} из {task['max_score']} баллов.", "info")
        else:
            flash("Ответ отправлен.", "success")
    else:
        flash("Ответ отправлен на проверку преподавателю.", "success")

    return redirect(url_for("tasks.task_detail", task_id=task_id))


# ── Ручная проверка (для учителя) ────────────────────────────────

@tasks_bp.route("/submissions")
@role_required("teacher", "admin")
def submissions_list():
    """Список ответов на ручную проверку (open-задания, без оценки)."""
    subs = query_all("""
        SELECT s.*, t.title AS task_title, t.max_score, u.username,
               t.task_type, l.course_id
        FROM submissions s
        JOIN tasks t   ON t.id = s.task_id
        JOIN users u   ON u.id = s.student_id
        JOIN lessons l ON l.id = t.lesson_id
        JOIN courses c ON c.id = l.course_id
        WHERE c.teacher_id = ? AND s.score IS NULL AND t.task_type = 'open'
        ORDER BY s.submitted_at
    """, (session["user_id"],))
    return render_template("tasks/submissions.html", submissions=subs)


@tasks_bp.route("/submissions/<int:sub_id>/grade", methods=["POST"])
@role_required("teacher", "admin")
def grade_submission(sub_id):
    score = request.form.get("score")
    if score is None:
        flash("Укажите оценку.", "danger")
        return redirect(url_for("tasks.submissions_list"))

    execute(
        """UPDATE submissions
           SET score = ?, checked_by = ?, checked_at = datetime('now')
           WHERE id = ?""",
        (int(score), session["user_id"], sub_id),
    )
    flash("Оценка выставлена.", "success")
    return redirect(url_for("tasks.submissions_list"))
