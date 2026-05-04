import os

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from config import Config
from database.db import init_db, close_db
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    csrf.init_app(app)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Database lifecycle
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db(app)

    # Register blueprints
    from blueprints.auth import auth_bp
    from blueprints.courses import courses_bp
    from blueprints.tasks import tasks_bp
    from blueprints.files import files_bp
    from blueprints.stats import stats_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(courses_bp, url_prefix="/courses")
    app.register_blueprint(tasks_bp, url_prefix="/tasks")
    app.register_blueprint(files_bp, url_prefix="/files")
    app.register_blueprint(stats_bp, url_prefix="/stats")

    # Контекстные функции для шаблонов
    @app.context_processor
    def inject_helpers():
        from database.db import query_all

        def get_lesson_tasks(lesson_id):
            return query_all(
                "SELECT * FROM tasks WHERE lesson_id = ? ORDER BY position", (lesson_id,)
            )

        def get_lesson_files(lesson_id):
            return query_all(
                "SELECT * FROM lesson_files WHERE lesson_id = ?", (lesson_id,)
            )

        return dict(get_lesson_tasks=get_lesson_tasks, get_lesson_files=get_lesson_files)

    # Index redirect
    @app.route("/")
    def index():
        from flask import redirect, url_for, session
        if "user_id" in session:
            return redirect(url_for("courses.course_list"))
        return redirect(url_for("auth.login"))
    

    return app