from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import Column, MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.sql import sqltypes


TARGET_DB = Path(__file__).resolve().parents[1] / "app" / "ethics_production_app" / "ethics.db"
CHUNK_SIZE = 500


def build_source_url() -> str:
    source_url = os.getenv("SOURCE_DATABASE_URL")
    if source_url:
        return source_url

    required = ["SOURCE_DB_SERVER", "SOURCE_DB_PORT", "SOURCE_DB_NAME", "SOURCE_DB_USER", "SOURCE_DB_PASSWORD"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing source database configuration. Provide SOURCE_DATABASE_URL or all SOURCE_DB_* variables."
        )

    db_server = os.getenv("SOURCE_DB_SERVER")
    db_port = os.getenv("SOURCE_DB_PORT")
    db_name = os.getenv("SOURCE_DB_NAME")
    db_user = quote_plus(os.getenv("SOURCE_DB_USER"))
    db_password = quote_plus(os.getenv("SOURCE_DB_PASSWORD"))
    db_sslmode = os.getenv("SOURCE_DB_SSLMODE") or ("require" if "render.com" in db_server else "disable")
    return (
        f"postgresql+psycopg2://{db_user}:{db_password}@{db_server}:{db_port}/{db_name}"
        f"?sslmode={db_sslmode}"
    )


def backup_target_db(target_db: Path) -> Path | None:
    if not target_db.exists():
        return None

    backup_dir = target_db.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{target_db.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{target_db.suffix}"
    shutil.copy2(target_db, backup_path)
    return backup_path


def ensure_target_schema():
    import importlib
    import sys

    app_dir = TARGET_DB.parent
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    models_module = importlib.import_module("models")
    models_module.Base.metadata.create_all(models_module.engine)
    if hasattr(models_module, "db_session"):
        models_module.db_session.remove()
    models_module.engine.dispose()


def create_sqlite_compatible_table(source_table: Table, target_engine):
    target_metadata = MetaData()
    columns = []
    for source_column in source_table.columns:
        column_type = source_column.type.as_generic()
        columns.append(
            Column(
                source_column.name,
                column_type,
                primary_key=source_column.primary_key,
                nullable=source_column.nullable,
            )
        )

    simple_table = Table(source_table.name, target_metadata, *columns)
    target_metadata.create_all(target_engine)


def normalize_value_for_target(table_name, value, target_column):
    if value is None:
        return None
    if isinstance(target_column.type, sqltypes.LargeBinary) and isinstance(value, str):
        return value.encode("utf-8")
    return value


def copy_table_data(source_engine, target_engine, table_name: str) -> tuple[int, int]:
    source_metadata = MetaData()
    source_table = Table(table_name, source_metadata, autoload_with=source_engine)

    target_metadata = MetaData()
    target_metadata.reflect(bind=target_engine)

    if table_name not in target_metadata.tables:
        create_sqlite_compatible_table(source_table, target_engine)
        target_metadata.clear()
        target_metadata.reflect(bind=target_engine)

    target_table = target_metadata.tables[table_name]
    common_columns = [column.name for column in source_table.columns if column.name in target_table.columns]

    with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
        target_conn.execute(text(f'DELETE FROM "{table_name}"'))

        source_count = source_conn.execute(select(source_table)).mappings().all()
        rows = []
        for row in source_count:
            rows.append(
                {
                    name: normalize_value_for_target(table_name, row[name], target_table.columns[name])
                    for name in common_columns
                }
            )

        if rows:
            for start in range(0, len(rows), CHUNK_SIZE):
                batch = rows[start:start + CHUNK_SIZE]
                target_conn.execute(target_table.insert(), batch)

    with target_engine.connect() as target_conn:
        target_count = target_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()

    return len(source_count), int(target_count)


def main():
    ensure_target_schema()
    backup_path = backup_target_db(TARGET_DB)
    source_url = build_source_url()

    source_engine = create_engine(source_url)
    target_engine = create_engine(f"sqlite:///{TARGET_DB.as_posix()}")

    source_tables = inspect(source_engine).get_table_names(schema="public")
    target_tables_before = set(inspect(target_engine).get_table_names())

    print(f"Target DB: {TARGET_DB}")
    if backup_path:
        print(f"Backup created: {backup_path}")
    else:
        print("No existing target DB backup was needed.")

    copied = []
    with target_engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))

    try:
        for table_name in source_tables:
            source_count, target_count = copy_table_data(source_engine, target_engine, table_name)
            copied.append((table_name, source_count, target_count, table_name in target_tables_before))
            print(f"{table_name}: source={source_count} target={target_count}")
    finally:
        with target_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = ON"))

    mismatches = [item for item in copied if item[1] != item[2]]
    if mismatches:
        print("Count mismatches detected:")
        for table_name, source_count, target_count, _ in mismatches:
            print(f" - {table_name}: source={source_count}, target={target_count}")
        raise SystemExit(1)

    print("Ethics database copy completed successfully.")


if __name__ == "__main__":
    main()
