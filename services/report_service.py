import io
import pandas as pd
from database.db import query_all


def _leaderboard_df(course_id: int | None = None) -> pd.DataFrame:
    """Собирает данные лидерборда в DataFrame."""
    if course_id:
        rows = query_all("""
            SELECT u.username  AS 'Студент',
                   c.title     AS 'Курс',
                   SUM(s.score) AS 'Баллы'
            FROM submissions s
            JOIN users u   ON u.id = s.student_id
            JOIN tasks t   ON t.id = s.task_id
            JOIN lessons l ON l.id = t.lesson_id
            JOIN courses c ON c.id = l.course_id
            WHERE s.score IS NOT NULL AND c.id = ?
            GROUP BY u.id
            ORDER BY 3 DESC
        """, (course_id,))
    else:
        rows = query_all("""
            SELECT u.username   AS 'Студент',
                   SUM(s.score) AS 'Баллы'
            FROM submissions s
            JOIN users u ON u.id = s.student_id
            WHERE s.score IS NOT NULL
            GROUP BY u.id
            ORDER BY 2 DESC
        """)

    columns = [desc[0] for desc in rows[0].keys()] if rows else []
    data = [dict(r) for r in rows]
    return pd.DataFrame(data)


def generate_csv(course_id: int | None = None) -> str:
    """Возвращает CSV-строку с рейтингом."""
    df = _leaderboard_df(course_id)
    return df.to_csv(index=False)


def generate_xlsx(course_id: int | None = None) -> bytes:
    """Возвращает байты XLSX-файла с рейтингом."""
    df = _leaderboard_df(course_id)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf.read()


def generate_pdf_html(course_id: int | None = None) -> str:
    """
    Возвращает HTML-строку для pdfkit.
    Если wkhtmltopdf не установлен — используй этот HTML как fallback.
    """
    df = _leaderboard_df(course_id)
    table_html = df.to_html(index=False, classes="table", border=0)
    return f"""
    <html>
    <head><meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        .table {{ border-collapse: collapse; width: 100%; }}
        .table th, .table td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
        .table th {{ background: #f5f5f5; }}
    </style>
    </head>
    <body>
        <h1>Отчёт об успеваемости — EduOnline</h1>
        {table_html}
    </body>
    </html>
    """
