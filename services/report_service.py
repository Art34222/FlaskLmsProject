import io

import pandas as pd

from database.db import query_all


def _leaderboard_df(course_id: int | None = None) -> pd.DataFrame:
    """Собирает данные лидерборда в DataFrame."""
    if course_id:
        rows = query_all("""
                         SELECT u.username AS 'Студент', c.title AS 'Курс', SUM(s.score) AS 'Баллы'
                         FROM submissions s
                                  JOIN users u ON u.id = s.student_id
                                  JOIN tasks t ON t.id = s.task_id
                                  JOIN lessons l ON l.id = t.lesson_id
                                  JOIN courses c ON c.id = l.course_id
                         WHERE s.score IS NOT NULL
                           AND c.id = ?
                         GROUP BY u.id
                         ORDER BY 3 DESC
                         """, (course_id,))
    else:
        rows = query_all("""
                         SELECT u.username AS 'Студент', SUM(s.score) AS 'Баллы'
                         FROM submissions s
                                  JOIN users u ON u.id = s.student_id
                         WHERE s.score IS NOT NULL
                         GROUP BY u.id
                         ORDER BY 2 DESC
                         """)

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


def generate_pdf(course_id: int | None = None) -> bytes:
    """
    Генерирует PDF-документ с помощью fpdf2 и возвращает байты.
    """
    from fpdf import FPDF
    import os

    df = _leaderboard_df(course_id)

    class PDF(FPDF):
        def header(self):
            self.set_font("Roboto", style="B", size=16)
            self.cell(0, 10, "Отчёт об успеваемости — EduOnline", align="C", new_x="LMARGIN", new_y="NEXT")
            self.ln(10)

    pdf = PDF()
    
    # Добавляем шрифт с поддержкой кириллицы
    font_path = os.path.join(os.path.dirname(__file__), "..", "static", "fonts", "Roboto-Regular.ttf")
    pdf.add_font("Roboto", style="", fname=font_path)
    pdf.add_font("Roboto", style="B", fname=font_path) # Используем тот же файл для жирного (или нужно добавить Roboto-Bold)

    pdf.add_page()
    pdf.set_font("Roboto", size=12)

    # Заголовок таблицы
    pdf.set_fill_color(240, 240, 240)
    for col in df.columns:
        pdf.cell(60, 10, str(col), border=1, fill=True, align="C")
    pdf.ln()

    # Данные таблицы
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(60, 10, str(item), border=1, align="C")
        pdf.ln()

    return pdf.output()