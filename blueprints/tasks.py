from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from database.db import query_one, query_all, execute
from services.grading_service import auto_check_test
from utils.decorators import login_required, role_required

tasks_bp = Blueprint("tasks", __name__)

MAX_SCORE_CEILING = 1000


def _user_can_edit_lesson(lesson) -> bool:
    """Учитель может править только уроки своих курсов; админ — все."""
    if not lesson:
        return False
    if session.get("role") == "admin":
        return True
    course = query_one("SELECT teacher_id FROM courses WHERE id = ?", (lesson["course_id"],))
    return bool(course) and course["teacher_id"] == session.get("user_id")


def _student_has_access_to_task(task) -> bool:
    """Студент должен быть записан на курс, к которому принадлежит задание."""
    lesson = query_one("SELECT course_id FROM lessons WHERE id = ?", (task["lesson_id"],))
    if not lesson:
        return False
    enrolled = query_one(
        "SELECT id FROM enrollments WHERE user_id = ? AND course_id = ?",
        (session["user_id"], lesson["course_id"]),
    )
    return enrolled is not None


# ── Создание задания ─────────────────────────────────────────────

@tasks_bp.route("/lesson/<int:lesson_id>/new", methods=["GET", "POST"])
@role_required("teacher", "admin")
def create_task(lesson_id):
    lesson = query_one("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
    if not lesson:
        flash("Урок не найден.", "danger")
        return redirect(url_for("courses.course_list"))

    if not _user_can_edit_lesson(lesson):
        flash("Нет прав на редактирование этого урока.", "danger")
        return redirect(url_for("courses.course_list"))

    if request.method == "GET":
        return render_template("tasks/create.html", lesson=lesson)

    # ── Получение и валидация ВСЕХ полей ДО INSERT ──────────────
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    task_type = request.form.get("task_type", "test")
    correct_answer = request.form.get("correct_answer", "").strip() or None
    max_score_raw = request.form.get("max_score")

    if not title:
        flash("Название задания обязательно.", "danger")
        return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

    if len(title) > 150:
        flash("Название слишком длинное (максимум 150 символов).", "danger")
        return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

    if len(description) > 2000:
        flash("Описание слишком длинное (максимум 2000 символов).", "danger")
        return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

    if task_type not in ("test", "open"):
        flash("Неверный тип задания.", "danger")
        return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

    try:
        max_score = int(max_score_raw) if max_score_raw else 10
    except ValueError:
        flash("Максимальный балл должен быть числом.", "danger")
        return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

    if not 1 <= max_score <= MAX_SCORE_CEILING:
        flash(f"Максимальный балл должен быть от 1 до {MAX_SCORE_CEILING}.", "danger")
        return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

    if correct_answer and len(correct_answer) > 2000:
        flash("Эталонный ответ слишком длинный (максимум 2000 символов).", "danger")
        return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

    # Для open-заданий игнорируем correct_answer из формы теста и наоборот
    options = []
    correct_indices = []
    if task_type == "test":
        options = request.form.getlist("options")
        correct_indices = request.form.getlist("correct_options")

        valid_options = [(i, o.strip()) for i, o in enumerate(options) if o.strip()]

        if len(valid_options) < 2:
            flash("Тест должен иметь минимум 2 варианта ответа.", "danger")
            return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

        for _, label in valid_options:
            if len(label) > 200:
                flash("Вариант ответа слишком длинный (максимум 200 символов).", "danger")
                return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

        has_correct = any(str(i) in correct_indices for i, _ in valid_options)
        if not has_correct:
            flash("Отметьте хотя бы один правильный вариант.", "danger")
            return redirect(url_for("tasks.create_task", lesson_id=lesson_id))

        # Для теста correct_answer не используем
        correct_answer = None
    else:
        # Для open варианты и correct_options не используем
        pass

    # ── Всё валидно — можно вставлять ───────────────────────────
    max_pos = query_one(
        "SELECT COALESCE(MAX(position), 0) AS mp FROM tasks WHERE lesson_id = ?",
        (lesson_id,),
    )
    task_id = execute(
        """INSERT INTO tasks (lesson_id, title, description, task_type,
                              correct_answer, max_score, position)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (lesson_id, title, description, task_type, correct_answer,
         max_score, (max_pos["mp"] or 0) + 1),
    )

    if task_type == "test":
        for i, label in enumerate(options):
            label = label.strip()
            if label:
                execute(
                    "INSERT INTO task_options (task_id, label, is_correct) VALUES (?, ?, ?)",
                    (task_id, label, 1 if str(i) in correct_indices else 0),
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

    lesson = query_one("SELECT * FROM lessons WHERE id = ?", (task["lesson_id"],))
    if not lesson:
        flash("Урок не найден.", "danger")
        return redirect(url_for("courses.course_list"))

    # Проверка доступа
    role = session.get("role")
    if role == "student":
        if not _student_has_access_to_task(task):
            flash("Нет доступа к этому заданию.", "danger")
            return redirect(url_for("courses.course_list"))
    elif role == "teacher":
        if not _user_can_edit_lesson(lesson):
            flash("Нет доступа к этому заданию.", "danger")
            return redirect(url_for("courses.course_list"))

    options = query_all("SELECT id, task_id, label FROM task_options WHERE task_id = ?", (task_id,))

    # Скрываем correct_answer от студентов — передаём очищенную копию task
    task_safe = dict(task)
    if role == "student":
        task_safe.pop("correct_answer", None)

    # Предыдущий ответ студента (если есть)
    submission = None
    if role == "student":
        submission = query_one(
            "SELECT * FROM submissions WHERE task_id = ? AND student_id = ? "
            "ORDER BY submitted_at DESC",
            (task_id, session.get("user_id")),
        )
    return render_template(
        "tasks/detail.html",
        task=task_safe, options=options, lesson=lesson, submission=submission,
    )


# ── Отправка ответа ──────────────────────────────────────────────

@tasks_bp.route("/<int:task_id>/submit", methods=["POST"])
@role_required("student")
def submit_answer(task_id):
    task = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        flash("Задание не найдено.", "danger")
        return redirect(url_for("courses.course_list"))

    if not _student_has_access_to_task(task):
        flash("Нет доступа к этому заданию.", "danger")
        return redirect(url_for("courses.course_list"))

    answer = request.form.get("answer", "").strip()

    if not answer:
        flash("Ответ не может быть пустым.", "danger")
        return redirect(url_for("tasks.task_detail", task_id=task_id))

    if len(answer) > 5000:
        flash("Ваш ответ слишком длинный (максимум 5000 символов).", "danger")
        return redirect(url_for("tasks.task_detail", task_id=task_id))

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
    if session.get("role") == "admin":
        subs = query_all("""
                         SELECT s.id,
                                s.answer,
                                s.submitted_at,
                                t.title AS task_title,
                                t.max_score,
                                u.username
                         FROM submissions s
                                  JOIN tasks t ON t.id = s.task_id
                                  JOIN users u ON u.id = s.student_id
                                  JOIN lessons l ON l.id = t.lesson_id
                         WHERE s.score IS NULL
                           AND t.task_type = 'open'
                         ORDER BY s.submitted_at
                         """)
    else:
        subs = query_all("""
                         SELECT s.id,
                                s.answer,
                                s.submitted_at,
                                t.title AS task_title,
                                t.max_score,
                                u.username
                         FROM submissions s
                                  JOIN tasks t ON t.id = s.task_id
                                  JOIN users u ON u.id = s.student_id
                                  JOIN lessons l ON l.id = t.lesson_id
                                  JOIN courses c ON c.id = l.course_id
                         WHERE c.teacher_id = ?
                           AND s.score IS NULL
                           AND t.task_type = 'open'
                         ORDER BY s.submitted_at
                         """, (session["user_id"],))
    return render_template("tasks/submissions.html", submissions=subs)


@tasks_bp.route("/submissions/<int:sub_id>/grade", methods=["POST"])
@role_required("teacher", "admin")
def grade_submission(sub_id):
    # Проверка существования submission + прав на оценку
    sub = query_one("""
                    SELECT s.id, t.max_score, c.teacher_id
                    FROM submissions s
                             JOIN tasks t ON t.id = s.task_id
                             JOIN lessons l ON l.id = t.lesson_id
                             JOIN courses c ON c.id = l.course_id
                    WHERE s.id = ?
                    """, (sub_id,))
    if not sub:
        flash("Работа не найдена.", "danger")
        return redirect(url_for("tasks.submissions_list"))

    if session.get("role") != "admin" and sub["teacher_id"] != session.get("user_id"):
        flash("Нет прав на оценку этой работы.", "danger")
        return redirect(url_for("tasks.submissions_list"))

    score_raw = request.form.get("score", "").strip()
    if not score_raw:
        flash("Укажите оценку.", "danger")
        return redirect(url_for("tasks.submissions_list"))

    try:
        score = int(score_raw)
    except ValueError:
        flash("Оценка должна быть числом!", "danger")
        return redirect(url_for("tasks.submissions_list"))

    if not 0 <= score <= sub["max_score"]:
        flash(f"Оценка должна быть от 0 до {sub['max_score']}.", "danger")
        return redirect(url_for("tasks.submissions_list"))

    execute(
        """UPDATE submissions
           SET score      = ?,
               checked_by = ?,
               checked_at = datetime('now')
           WHERE id = ?""",
        (score, session["user_id"], sub_id),
    )
    flash("Оценка выставлена.", "success")
    return redirect(url_for("tasks.submissions_list"))