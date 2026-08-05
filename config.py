import os
import secrets
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _sqlite_database_is_healthy(path: Path) -> bool:
    if not path.exists():
        return False

    try:
        conn = sqlite3.connect(path)
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
            return bool(row) and row[0] == "ok"
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False


def _default_sqlite_database_uri() -> str:
    primary_db_path = BASE_DIR / "app.db"
    if _sqlite_database_is_healthy(primary_db_path):
        return f"sqlite:///{primary_db_path.as_posix()}"

    backup_paths = sorted(BASE_DIR.glob("app.db.backup-*"), reverse=True)
    for backup_path in backup_paths:
        if _sqlite_database_is_healthy(backup_path):
            return f"sqlite:///{backup_path.as_posix()}"

    return f"sqlite:///{primary_db_path.as_posix()}"


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
    MBA_DATA_ENCRYPTION_KEY = os.getenv("MBA_DATA_ENCRYPTION_KEY")
    PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        _default_sqlite_database_uri(),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = os.getenv("WTF_CSRF_ENABLED", "true").lower() in {"1", "true", "yes"}

    # Shared upload limits used by the mounted ethics application. The request
    # limit covers the complete multipart body; the file limit is per document.
    MAX_CONTENT_LENGTH = int(
        os.getenv("MAX_REQUEST_SIZE", os.getenv("MAX_FILE_SIZE", "536870912"))
    )
    MAX_FILE_LENGTH = int(os.getenv("MAX_DOCUMENT_SIZE", "524288000"))

    MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
    MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
    MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")
    MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI")

    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() in {"1", "true", "yes"}
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() in {"1", "true", "yes"}
    MAIL_USERNAME = os.getenv("MAIL_USERNAME") or os.getenv("EMAIL")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD") or os.getenv("EMAIL_CODE")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_USERNAME)
    MAIL_LOGO_URL = os.getenv("MAIL_LOGO_URL")
    MAIL_TIMEOUT = _env_float("MAIL_TIMEOUT", 20)
