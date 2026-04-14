from functools import wraps

from flask import session, redirect, url_for, flash, abort


def login_required(f):
    """Редирект на логин, если пользователь не авторизован."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Пожалуйста, войдите в систему.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return wrapper


def role_required(*roles):
    """Проверка роли: @role_required('teacher', 'admin')."""

    def decorator(f):
        @wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                abort(403)
            return f(*args, **kwargs)

        return wrapper

    return decorator
