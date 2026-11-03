import os
import sqlite3
from contextlib import contextmanager

import bcrypt

from auth_service.config import DATABASE_PATH, LEGACY_DATABASE_PATH


@contextmanager
def connect_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def _copy_legacy_admins(connection):
    if not LEGACY_DATABASE_PATH.is_file():
        return 0

    source = sqlite3.connect(LEGACY_DATABASE_PATH)
    source.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "admins" not in tables:
            return 0

        columns = {
            row["name"] for row in source.execute("PRAGMA table_info(admins)")
        }
        if not {"id", "username", "password"}.issubset(columns):
            return 0

        admins = source.execute(
            "SELECT id, username, password FROM admins"
        ).fetchall()
    finally:
        source.close()

    connection.executemany(
        """INSERT OR IGNORE INTO admins (id, username, password_hash)
           VALUES (?, ?, ?)""",
        [(admin["id"], admin["username"], admin["password"]) for admin in admins],
    )
    return len(admins)


def initialize_database():
    with connect_db() as connection:
        with connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS admins (
                       id TEXT PRIMARY KEY,
                       username TEXT UNIQUE NOT NULL,
                       password_hash TEXT NOT NULL
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS revoked_tokens (
                       token_id TEXT PRIMARY KEY,
                       revoked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                   )"""
            )
            admin_count = connection.execute(
                "SELECT COUNT(*) FROM admins"
            ).fetchone()[0]
            if admin_count == 0:
                _copy_legacy_admins(connection)
                admin_count = connection.execute(
                    "SELECT COUNT(*) FROM admins"
                ).fetchone()[0]

            username = os.environ.get("INITIAL_ADMIN_USERNAME", "").strip()
            password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
            if not admin_count and username and password:
                password_hash = bcrypt.hashpw(
                    password.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8")
                connection.execute(
                    "INSERT OR IGNORE INTO admins (id, username, password_hash) VALUES (?, ?, ?)",
                    ("initial-admin", username, password_hash),
                )


def find_admin(username):
    with connect_db() as connection:
        return connection.execute(
            "SELECT id, username, password_hash FROM admins WHERE username = ?",
            (username,),
        ).fetchone()


def token_is_revoked(token_id):
    with connect_db() as connection:
        return connection.execute(
            "SELECT 1 FROM revoked_tokens WHERE token_id = ?", (token_id,)
        ).fetchone() is not None


def revoke_token(token_id):
    with connect_db() as connection:
        with connection:
            connection.execute(
                "INSERT OR IGNORE INTO revoked_tokens (token_id) VALUES (?)",
                (token_id,),
            )
