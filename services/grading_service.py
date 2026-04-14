from database.db import query_one, query_all, execute


def auto_check_test(submission_id: int) -> int | None:
    """
    Автоматическая проверка тестового задания.
    Сравнивает ответ студента с правильным ответом (без учёта регистра).
    Возвращает набранный балл или None, если задание не тестовое.
    """
    sub = query_one("SELECT * FROM submissions WHERE id = ?", (submission_id,))
    if not sub:
        return None

    task = query_one("SELECT * FROM tasks WHERE id = ?", (sub["task_id"],))
    if not task or task["task_type"] != "test":
        return None

    # Проверяем: либо по correct_answer в tasks, либо по task_options
    options = query_all(
        "SELECT * FROM task_options WHERE task_id = ? AND is_correct = 1",
        (task["id"],),
    )

    student_answer = (sub["answer"] or "").strip().lower()

    if options:
        correct_labels = [o["label"].strip().lower() for o in options]
        is_correct = student_answer in correct_labels
    elif task["correct_answer"]:
        is_correct = student_answer == task["correct_answer"].strip().lower()
    else:
        return None  # нечем проверять

    score = task["max_score"] if is_correct else 0
    execute(
        "UPDATE submissions SET score = ?, checked_at = datetime('now') WHERE id = ?",
        (score, submission_id),
    )
    return score


def get_leaderboard(course_id: int | None = None):
    """
    Рейтинг студентов по сумме баллов.
    Если course_id указан — только по заданиям этого курса.
    """
    if course_id:
        return query_all("""
            SELECT u.id, u.username, COALESCE(SUM(s.score), 0) AS total_score
            FROM users u
            JOIN submissions s ON s.student_id = u.id
            JOIN tasks t ON t.id = s.task_id
            JOIN lessons l ON l.id = t.lesson_id
            WHERE l.course_id = ? AND s.score IS NOT NULL
            GROUP BY u.id
            ORDER BY total_score DESC
        """, (course_id,))
    else:
        return query_all("""
            SELECT u.id, u.username, COALESCE(SUM(s.score), 0) AS total_score
            FROM users u
            JOIN submissions s ON s.student_id = u.id
            WHERE s.score IS NOT NULL
            GROUP BY u.id
            ORDER BY total_score DESC
        """)
