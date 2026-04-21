from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from database.db import query_one, execute
from services.auth_service import (
    hash_password, verify_password,
    generate_otp_secret, verify_otp, generate_qr_base64,
)

auth_bp = Blueprint("auth", __name__)

MAX_2FA_ATTEMPTS = 5


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/register.html")

    email = request.form.get("email", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    password_confirm = request.form.get("password_confirm", "")
    role = request.form.get("role", "student")

    if not email or not username or not password or not password_confirm:
        flash("Заполните все поля.", "danger")
        return redirect(url_for("auth.register"))

    if len(email) > 100 or len(username) > 50 or len(password) > 100:
        flash("Превышен лимит символов (email и пароль до 100, имя до 50).", "danger")
        return redirect(url_for("auth.register"))

    if len(password) < 8:
        flash("Слабый пароль (минимум 8 символов).", "danger")
        return redirect(url_for("auth.register"))

    if password != password_confirm:
        flash("Пароли не совпадают.", "danger")
        return redirect(url_for("auth.register"))

    if role not in ("student", "teacher"):
        role = "student"

    if query_one("SELECT id FROM users WHERE email = ?", (email,)):
        flash("Пользователь с таким email уже существует.", "danger")
        return redirect(url_for("auth.register"))

    if query_one("SELECT id FROM users WHERE username = ?", (username,)):
        flash("Имя пользователя занято.", "danger")
        return redirect(url_for("auth.register"))

    execute(
        "INSERT INTO users (email, username, password_hash, role) VALUES (?, ?, ?, ?)",
        (email, username, hash_password(password), role),
    )
    flash("Регистрация прошла успешно! Войдите.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if len(email) > 100 or len(password) > 100:
        flash("Превышен лимит символов (email и пароль до 100).", "danger")
        return redirect(url_for("auth.login"))

    user = query_one("SELECT * FROM users WHERE email = ?", (email,))
    if not user or not verify_password(user["password_hash"], password):
        flash("Неверный email или пароль.", "danger")
        return redirect(url_for("auth.login"))

    # Если 2FA включена — перенаправляем на проверку кода
    if user["otp_enabled"]:
        if not user["otp_secret"]:
            # Рассинхронизация: включено, но секрета нет. Сбрасываем флаг.
            execute("UPDATE users SET otp_enabled = 0 WHERE id = ?", (user["id"],))
        else:
            # Защита от session fixation — чистим старую сессию
            session.clear()
            session["pending_2fa_user_id"] = user["id"]
            return redirect(url_for("auth.verify_2fa"))

    session.clear()
    _login_user(user)
    return redirect(url_for("courses.course_list"))


@auth_bp.route("/2fa/verify", methods=["GET", "POST"])
def verify_2fa():
    user_id = session.get("pending_2fa_user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    if request.method == "GET":
        return render_template("auth/2fa_verify.html")

    # Защита от брутфорса: после MAX_2FA_ATTEMPTS неудач сбрасываем сессию
    # и заставляем начать вход заново.
    attempts = session.get("2fa_attempts", 0)
    if attempts >= MAX_2FA_ATTEMPTS:
        session.clear()
        flash("Слишком много неудачных попыток. Войдите заново.", "danger")
        return redirect(url_for("auth.login"))

    code = request.form.get("code", "").strip()

    if len(code) != 6 or not code.isdigit():
        session["2fa_attempts"] = attempts + 1
        flash("Неверный формат кода.", "danger")
        return redirect(url_for("auth.verify_2fa"))

    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))

    if user and user["otp_secret"] and verify_otp(user["otp_secret"], code):
        session.pop("pending_2fa_user_id", None)
        session.pop("2fa_attempts", None)
        _login_user(user)
        return redirect(url_for("courses.course_list"))

    session["2fa_attempts"] = attempts + 1
    flash("Неверный код. Попробуйте ещё раз.", "danger")
    return redirect(url_for("auth.verify_2fa"))


@auth_bp.route("/2fa/setup", methods=["GET", "POST"])
def setup_2fa():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user = query_one("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    if request.method == "GET":
        secret = user["otp_secret"] or generate_otp_secret()
        if not user["otp_secret"]:
            execute("UPDATE users SET otp_secret = ? WHERE id = ?", (secret, user["id"]))
        qr = generate_qr_base64(secret, user["email"])
        return render_template("auth/2fa_setup.html", qr=qr, secret=secret)

    # POST: пользователь подтверждает, что отсканировал QR и вводит код
    attempts = session.get("2fa_setup_attempts", 0)
    if attempts >= MAX_2FA_ATTEMPTS:
        session.pop("2fa_setup_attempts", None)
        flash("Слишком много неудачных попыток. Попробуйте настроить 2FA заново.", "danger")
        return redirect(url_for("courses.course_list"))

    code = request.form.get("code", "").strip()

    if len(code) != 6 or not code.isdigit():
        session["2fa_setup_attempts"] = attempts + 1
        flash("Неверный формат кода.", "danger")
        return redirect(url_for("auth.setup_2fa"))

    if user["otp_secret"] and verify_otp(user["otp_secret"], code):
        execute("UPDATE users SET otp_enabled = 1 WHERE id = ?", (user["id"],))
        session.pop("2fa_setup_attempts", None)
        flash("Двухфакторная аутентификация включена!", "success")
        return redirect(url_for("courses.course_list"))

    session["2fa_setup_attempts"] = attempts + 1
    flash("Неверный код. Попробуйте ещё раз.", "danger")
    return redirect(url_for("auth.setup_2fa"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("auth.login"))


def _login_user(user):
    """Записывает данные пользователя в сессию."""
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]