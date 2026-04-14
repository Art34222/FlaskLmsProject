import os
import sqlite3

from flask import g, current_app


def get_db():
    """Возвращает соединение с БД, привязанное к текущему запросу."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row  # доступ по имени столбца
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    """Создаёт таблицы, если БД пустая."""
    db_path = app.config["DATABASE"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = sqlite3.connect(db_path)
    with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
        db.executescript(f.read())
    db.close()


# ── Вспомогательные функции ──────────────────────────────────────

def query_one(sql, args=()):
    """SELECT … вернуть одну строку (или None)."""
    return get_db().execute(sql, args).fetchone()


def query_all(sql, args=()):
    """SELECT … вернуть все строки."""
    return get_db().execute(sql, args).fetchall()


def execute(sql, args=()):
    """INSERT / UPDATE / DELETE — возвращает lastrowid."""
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid
