from __future__ import annotations

import os
from uuid import uuid4
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.sql import sqltypes


ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "users",
    "form_a",
    "form_b",
    "form_c",
    "form_d",
    "rec",
    "watched",
    "documents",
    "form_a_requirements",
    "form_uploads",
    "login_logs",
    "user_activity_logs",
    "user_information",
)
BATCH_SIZE = 50
RENAMED_COLUMNS = {
    "supervisor_form_status": "ethics_form_status",
    "supervisor_signature_date": "ethics_signature_date",
}


def database_urls() -> tuple[str, str]:
    target_url = os.getenv("DATABASE_URL")
    if not target_url:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                target_url = line.split("=", 1)[1].strip().strip("\"'")
                break
    if not target_url:
        raise RuntimeError("DATABASE_URL is required")

    target_url = make_url(target_url).set(drivername="postgresql+psycopg2").render_as_string(
        hide_password=False
    )
    source_url = os.getenv("ETHICS_SEED_DATABASE_URL")
    if not source_url:
        source_url = make_url(target_url).set(database="ethics_production_seed").render_as_string(
            hide_password=False
        )
    else:
        source_url = make_url(source_url).set(
            drivername="postgresql+psycopg2"
        ).render_as_string(hide_password=False)
    return source_url, target_url


def merge_users(source_engine, target_connection) -> tuple[dict[str, str], int, int]:
    source_metadata = MetaData()
    target_metadata = MetaData()
    source_table = Table("users", source_metadata, autoload_with=source_engine)
    target_table = Table("users", target_metadata, autoload_with=target_connection)
    common_columns = [
        column.name for column in source_table.columns if column.name in target_table.columns
    ]

    with source_engine.connect() as source_connection:
        source_rows = [
            dict(row)
            for row in source_connection.execute(
                select(*(source_table.c[name] for name in common_columns))
            ).mappings()
        ]

    target_rows = target_connection.execute(
        select(target_table.c.user_id, target_table.c.email)
    ).mappings()
    email_to_id = {
        row["email"].strip().lower(): str(row["user_id"])
        for row in target_rows
        if row["email"]
    }
    used_ids = set(email_to_id.values())
    user_id_map: dict[str, str] = {}

    for row in source_rows:
        old_id = str(row["user_id"])
        email = row["email"].strip().lower()
        effective_id = email_to_id.get(email)
        if not effective_id:
            effective_id = old_id
            while effective_id in used_ids:
                effective_id = str(uuid4())
            email_to_id[email] = effective_id
            used_ids.add(effective_id)
        user_id_map[old_id] = effective_id

    for row in source_rows:
        row["user_id"] = user_id_map[str(row["user_id"])]
        if row.get("email"):
            row["email"] = row["email"].strip().lower()
        supervisor_id = row.get("supervisor_id")
        if supervisor_id:
            row["supervisor_id"] = user_id_map.get(str(supervisor_id), supervisor_id)

    for start in range(0, len(source_rows), BATCH_SIZE):
        rows = source_rows[start : start + BATCH_SIZE]
        statement = insert(target_table).values(rows)
        update_columns = {
            name: getattr(statement.excluded, name)
            for name in common_columns
            if name not in {"user_id", "email"}
        }
        target_connection.execute(
            statement.on_conflict_do_update(
                index_elements=["email"],
                set_=update_columns,
            )
        )

    for row in source_rows:
        ethics_role = str(row["role"]).strip().lower()
        access_values = {
            "ethics_access": True,
            "ethics_role": ethics_role,
        }
        if ethics_role == "student":
            access_values.update(
                {
                    "mba_access": True,
                    "mba_role": "student",
                    "authenticated_student": True,
                    "authenticate_student": "true",
                }
            )
        target_connection.execute(
            target_table.update()
            .where(target_table.c.user_id == row["user_id"])
            .values(**access_values)
        )

    target_count = target_connection.execute(
        select(text("count(*)")).select_from(target_table)
    ).scalar_one()
    return user_id_map, len(source_rows), int(target_count)


def merge_table(
    source_engine,
    target_connection,
    table_name: str,
    user_id_map: dict[str, str],
) -> tuple[int, int]:
    source_metadata = MetaData()
    target_metadata = MetaData()
    source_table = Table(table_name, source_metadata, autoload_with=source_engine)
    target_table = Table(table_name, target_metadata, autoload_with=target_connection)

    common_columns = [
        column.name for column in source_table.columns if column.name in target_table.columns
    ]
    renamed_columns = {
        source_name: target_name
        for source_name, target_name in RENAMED_COLUMNS.items()
        if source_name in source_table.columns and target_name in target_table.columns
    }
    target_columns = common_columns + list(renamed_columns.values())
    primary_keys = [
        column.name for column in source_table.primary_key.columns if column.name in common_columns
    ]
    if not primary_keys:
        raise RuntimeError(f"{table_name} has no usable primary key")

    user_foreign_keys = {
        constrained_column
        for foreign_key in inspect(target_connection).get_foreign_keys(table_name)
        if foreign_key.get("referred_table") == "users"
        for constrained_column in foreign_key["constrained_columns"]
    }

    inserted_or_updated = 0
    with source_engine.connect() as source_connection:
        result = source_connection.execute(
            select(
                *(source_table.c[name] for name in common_columns),
                *(
                    source_table.c[source_name].label(target_name)
                    for source_name, target_name in renamed_columns.items()
                ),
            )
        ).mappings()
        while batch := result.fetchmany(BATCH_SIZE):
            rows = [dict(row) for row in batch]
            for row in rows:
                for column_name, value in row.items():
                    if (
                        value is not None
                        and isinstance(target_table.c[column_name].type, sqltypes.LargeBinary)
                        and isinstance(value, str)
                    ):
                        row[column_name] = value.encode("utf-8")
                for column_name in user_foreign_keys:
                    value = row.get(column_name)
                    if value is not None:
                        row[column_name] = user_id_map.get(str(value), value)
            statement = insert(target_table).values(rows)
            update_columns = {
                name: getattr(statement.excluded, name)
                for name in target_columns
                if name not in primary_keys
            }
            if update_columns:
                statement = statement.on_conflict_do_update(
                    index_elements=primary_keys,
                    set_=update_columns,
                )
            else:
                statement = statement.on_conflict_do_nothing(index_elements=primary_keys)
            target_connection.execute(statement)
            inserted_or_updated += len(rows)

    target_count = target_connection.execute(
        select(text("count(*)")).select_from(target_table)
    ).scalar_one()
    return inserted_or_updated, int(target_count)


def reset_sequences(target_connection) -> None:
    inspector = inspect(target_connection)
    for table_name in TABLES:
        for column in inspector.get_columns(table_name):
            default = column.get("default") or ""
            if not default.startswith("nextval("):
                continue
            column_name = column["name"]
            target_connection.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence(:table_name, :column_name), "
                    "COALESCE((SELECT MAX(" + f'"{column_name}"' + ") FROM "
                    + f'"{table_name}"' + "), 1), true)"
                ),
                {"table_name": table_name, "column_name": column_name},
            )


def main() -> None:
    source_url, target_url = database_urls()
    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)

    print("Merging ethics production seed into mba_ethics")
    with target_engine.begin() as target_connection:
        user_id_map, merged, total = merge_users(source_engine, target_connection)
        print(f"users: merged={merged} target_total={total}")
        for table_name in TABLES[1:]:
            merged, total = merge_table(
                source_engine, target_connection, table_name, user_id_map
            )
            print(f"{table_name}: merged={merged} target_total={total}")
        reset_sequences(target_connection)

    source_engine.dispose()
    target_engine.dispose()
    print("Merge completed successfully")


if __name__ == "__main__":
    main()
