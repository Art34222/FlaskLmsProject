CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT    UNIQUE NOT NULL,
    username    TEXT    UNIQUE NOT NULL,
    password_hash TEXT  NOT NULL,
    role        TEXT    NOT NULL DEFAULT 'student'
                        CHECK (role IN ('student', 'teacher', 'admin')),
    otp_secret  TEXT,           -- секрет для pyotp (NULL = 2FA не включена)
    otp_enabled INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS courses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT,
    teacher_id  INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS enrollments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    course_id   INTEGER NOT NULL REFERENCES courses(id),
    enrolled_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, course_id)
);

CREATE TABLE IF NOT EXISTS lessons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id   INTEGER NOT NULL REFERENCES courses(id),
    title       TEXT    NOT NULL,
    content     TEXT,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lesson_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id   INTEGER NOT NULL REFERENCES lessons(id),
    filename    TEXT    NOT NULL,
    filepath    TEXT    NOT NULL,
    uploaded_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id       INTEGER NOT NULL REFERENCES lessons(id),
    title           TEXT    NOT NULL,
    description     TEXT,
    task_type       TEXT    NOT NULL DEFAULT 'test'
                            CHECK (task_type IN ('test', 'open')),
    correct_answer  TEXT,   -- для test: правильный ответ; для open: NULL
    max_score       INTEGER NOT NULL DEFAULT 10,
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_options (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id),
    label       TEXT    NOT NULL,
    is_correct  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS submissions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id),
    student_id  INTEGER NOT NULL REFERENCES users(id),
    answer      TEXT,
    file_path   TEXT,
    score       INTEGER,            -- NULL пока не проверено
    checked_by  INTEGER REFERENCES users(id),
    submitted_at TEXT   NOT NULL DEFAULT (datetime('now')),
    checked_at  TEXT
);
