import importlib.util
import importlib
import os
import secrets
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

from jinja2 import FileSystemLoader
from config import Config


_MOUNTED_APP = None


def _resolve_sqlite_db_path(default_path: Path) -> Path:
    database_url = os.getenv("ETHICS_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    if not database_url.startswith("sqlite:///"):
        return default_path

    parsed = urlparse(database_url)
    sqlite_path = unquote(parsed.path or "")
    if sqlite_path.startswith("/") and len(sqlite_path) > 2 and sqlite_path[2] == ":":
        sqlite_path = sqlite_path.lstrip("/")
    return Path(sqlite_path) if sqlite_path else default_path


def _ensure_sqlite_compatibility(db_path: Path):
    if not db_path.exists():
        return

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        existing_columns = {row[1] for row in cur.fetchall()}

        required_user_columns = {
            "staff_number": "ALTER TABLE users ADD COLUMN staff_number VARCHAR(255)",
            "specialisation": "ALTER TABLE users ADD COLUMN specialisation VARCHAR(255)",
            "authenticate_student": "ALTER TABLE users ADD COLUMN authenticate_student VARCHAR DEFAULT 'false'",
        }

        for column_name, ddl in required_user_columns.items():
            if column_name not in existing_columns:
                cur.execute(ddl)

        conn.commit()
    finally:
        conn.close()


def get_mounted_app():
    global _MOUNTED_APP
    if _MOUNTED_APP is not None:
        return _MOUNTED_APP

    app_dir = Path(__file__).resolve().parent
    app_file = app_dir / "app.py"
    db_file = _resolve_sqlite_db_path(app_dir / "ethics.db")

    os.environ.setdefault("SECRET_KEY", Config.SECRET_KEY)
    os.environ.setdefault("ETHICS_DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    _ensure_sqlite_compatibility(db_file)

    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    project_root = app_dir.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    models_module = importlib.import_module("app.models")
    models_module.Base.metadata.create_all(models_module.engine)

    spec = importlib.util.spec_from_file_location("ethics_production_runtime", app_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load production ethics app from {app_file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.app.template_folder = str(app_dir / "templates")
    module.app.static_folder = str(app_dir / "static")
    module.app.jinja_loader = FileSystemLoader(str(app_dir / "templates"))
    _MOUNTED_APP = module.app
    return _MOUNTED_APP
