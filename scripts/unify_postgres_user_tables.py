from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection


load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")


MBA_ROLE_TO_LEGACY_ROLE = {
    "main_admin": "SUPER_ADMIN",
    "admin": "ADMIN",
    "student": "STUDENT",
    "scholar": "SUPERVISOR",
    "examiner": "REVIEWER",
    "hdc": "REC",
}

ETHICS_ROLE_TO_LEGACY_ROLE = {
    "student": "STUDENT",
    "supervisor": "SUPERVISOR",
    "admin": "ADMIN",
    "rec": "REC",
    "reviewer": "REVIEWER",
    "dean": "DEAN",
    "super_admin": "SUPER_ADMIN",
}


@dataclass
class UnifiedRecord:
    email: str
    user_id: str
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = None
    legacy_role: str = "STUDENT"
    student_number: int | None = None
    supervisor_legacy_user_id: str | None = None
    staff_number: str | None = None
    specialisation: str | None = None
    reset_token: str | None = None
    reset_token_expiry: Any = None
    authenticate_student: str | None = None
    microsoft_subject: str | None = None
    is_active: bool = True
    popia_confirmed_at: Any = None
    popia_notice_version: str | None = None
    popia_confirmed_ip: str | None = None
    popia_confirmed_user_agent: str | None = None
    created_at: Any = None
    updated_at: Any = None
    mba_role: str | None = None
    scholar_role: str | None = None
    has_profile: bool = False
    has_signature: bool = False
    has_cv: bool = False
    ethics_role: str | None = None
    authenticated_student: bool = False
    watched_demo: bool = False
    mba_access: bool = False
    ethics_access: bool = False
    source_mba_id: int | None = None
    source_ethics_id: int | None = None


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower() or None


def split_name(full_name: str | None) -> tuple[str | None, str | None]:
    clean = (full_name or "").strip()
    if not clean:
        return None, None
    parts = clean.split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def full_name(first_name: str | None, last_name: str | None, email: str) -> str:
    combined = " ".join(part for part in [first_name, last_name] if part).strip()
    return combined or email.split("@", 1)[0]


def map_legacy_role(*, ethics_role: str | None, mba_role: str | None, scholar_role: str | None) -> str:
    if ethics_role:
        return ETHICS_ROLE_TO_LEGACY_ROLE.get(ethics_role, "STUDENT")
    if scholar_role == "supervisor":
        return "SUPERVISOR"
    if scholar_role == "examiner":
        return "REVIEWER"
    if scholar_role == "both":
        return "SUPERVISOR"
    return MBA_ROLE_TO_LEGACY_ROLE.get(mba_role or "", "STUDENT")


def ensure_unified_columns(conn: Connection) -> None:
    ddl = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS integrated_id BIGINT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS microsoft_subject VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS popia_confirmed_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS popia_notice_version VARCHAR(40)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS popia_confirmed_ip VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS popia_confirmed_user_agent VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mba_role VARCHAR(40)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS scholar_role VARCHAR(40)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS has_profile BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS has_signature BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS has_cv BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ethics_role VARCHAR(40)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS supervisor_integrated_id BIGINT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS authenticated_student BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS watched_demo BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mba_access BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ethics_access BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR(120)",
    ]
    for statement in ddl:
        conn.execute(text(statement))

    conn.execute(text("CREATE SEQUENCE IF NOT EXISTS users_integrated_id_seq"))
    conn.execute(text("ALTER TABLE users ALTER COLUMN integrated_id SET DEFAULT nextval('users_integrated_id_seq')"))
    conn.execute(text("UPDATE users SET integrated_id = nextval('users_integrated_id_seq') WHERE integrated_id IS NULL"))
    conn.execute(text("ALTER TABLE users ALTER COLUMN integrated_id SET NOT NULL"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_integrated_id ON users(integrated_id)"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower ON users((lower(email)))"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_legacy_user_id ON users(user_id)"))


def fetch_rows(conn: Connection, table_name: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text(f'SELECT * FROM "{table_name}"')).mappings()]


def build_unified_records(
    mba_rows: list[dict[str, Any]],
    ethics_rows: list[dict[str, Any]],
    legacy_rows: list[dict[str, Any]],
) -> tuple[list[UnifiedRecord], dict[int, str], dict[int, str]]:
    records: dict[str, UnifiedRecord] = {}
    mba_id_to_email: dict[int, str] = {}
    ethics_id_to_email: dict[int, str] = {}

    for row in legacy_rows:
        email = normalize_email(row.get("email"))
        if not email:
            continue
        first_name, last_name = split_name(row.get("full_name"))
        record = records.setdefault(
            email,
            UnifiedRecord(
                email=email,
                user_id=row["user_id"],
                full_name=row.get("full_name") or email,
            ),
        )
        record.password = row.get("password") or record.password
        record.legacy_role = row.get("role") or record.legacy_role
        record.student_number = row.get("student_number") or record.student_number
        record.staff_number = row.get("staff_number") or record.staff_number
        record.specialisation = row.get("specialisation") or record.specialisation
        record.reset_token = row.get("reset_token") or record.reset_token
        record.reset_token_expiry = row.get("reset_token_expiry") or record.reset_token_expiry
        record.authenticate_student = row.get("authenticate_student") or record.authenticate_student
        record.first_name = first_name or record.first_name
        record.last_name = last_name or record.last_name
        record.full_name = row.get("full_name") or record.full_name
        record.supervisor_legacy_user_id = row.get("supervisor_id") or record.supervisor_legacy_user_id

    for row in mba_rows:
        email = normalize_email(row.get("email"))
        if not email:
            continue
        mba_id_to_email[row["id"]] = email
        record = records.setdefault(
            email,
            UnifiedRecord(
                email=email,
                user_id=uuid.uuid4().hex,
                full_name=full_name(row.get("first_name"), row.get("last_name"), email),
            ),
        )
        record.first_name = row.get("first_name") or record.first_name
        record.last_name = row.get("last_name") or record.last_name
        record.full_name = full_name(record.first_name, record.last_name, email)
        record.password = row.get("password_hash") or record.password
        record.microsoft_subject = row.get("microsoft_subject") or record.microsoft_subject
        record.is_active = bool(row.get("is_active", True)) and record.is_active
        record.popia_confirmed_at = row.get("popia_confirmed_at") or record.popia_confirmed_at
        record.popia_notice_version = row.get("popia_notice_version") or record.popia_notice_version
        record.popia_confirmed_ip = row.get("popia_confirmed_ip") or record.popia_confirmed_ip
        record.popia_confirmed_user_agent = row.get("popia_confirmed_user_agent") or record.popia_confirmed_user_agent
        record.created_at = row.get("created_at") or record.created_at
        record.updated_at = row.get("updated_at") or record.updated_at
        record.mba_role = row.get("role") or record.mba_role
        record.scholar_role = row.get("scholar_role") or record.scholar_role
        record.has_profile = bool(row.get("has_profile")) or record.has_profile
        record.has_signature = bool(row.get("has_signature")) or record.has_signature
        record.has_cv = bool(row.get("has_cv")) or record.has_cv
        record.mba_access = True
        record.source_mba_id = row["id"]
        record.legacy_role = map_legacy_role(
            ethics_role=record.ethics_role,
            mba_role=record.mba_role,
            scholar_role=record.scholar_role,
        )

    for row in ethics_rows:
        email = normalize_email(row.get("email"))
        if not email:
            continue
        ethics_id_to_email[row["id"]] = email
        record = records.setdefault(
            email,
            UnifiedRecord(
                email=email,
                user_id=uuid.uuid4().hex,
                full_name=full_name(row.get("first_name"), row.get("last_name"), email),
            ),
        )
        record.first_name = row.get("first_name") or record.first_name
        record.last_name = row.get("last_name") or record.last_name
        record.full_name = full_name(record.first_name, record.last_name, email)
        record.password = row.get("password_hash") or record.password
        record.microsoft_subject = row.get("microsoft_subject") or record.microsoft_subject
        record.is_active = bool(row.get("is_active", True)) and record.is_active
        record.popia_confirmed_at = row.get("popia_confirmed_at") or record.popia_confirmed_at
        record.popia_notice_version = row.get("popia_notice_version") or record.popia_notice_version
        record.popia_confirmed_ip = row.get("popia_confirmed_ip") or record.popia_confirmed_ip
        record.popia_confirmed_user_agent = row.get("popia_confirmed_user_agent") or record.popia_confirmed_user_agent
        record.created_at = row.get("created_at") or record.created_at
        record.updated_at = row.get("updated_at") or record.updated_at
        record.ethics_role = row.get("role") or record.ethics_role
        record.student_number = int(row["student_number"]) if str(row.get("student_number") or "").isdigit() else record.student_number
        record.staff_number = row.get("staff_number") or record.staff_number
        record.specialisation = row.get("specialisation") or record.specialisation
        record.authenticated_student = bool(row.get("authenticated_student")) or record.authenticated_student
        record.watched_demo = bool(row.get("watched_demo")) or record.watched_demo
        record.authenticate_student = "true" if record.authenticated_student else record.authenticate_student
        record.ethics_access = True
        record.source_ethics_id = row["id"]
        record.legacy_role = map_legacy_role(
            ethics_role=record.ethics_role,
            mba_role=record.mba_role,
            scholar_role=record.scholar_role,
        )

    return list(records.values()), mba_id_to_email, ethics_id_to_email


def truncate_users_if_legacy_empty(conn: Connection, legacy_rows: list[dict[str, Any]]) -> None:
    if legacy_rows:
        raise RuntimeError("The legacy users table already contains data. Aborting automatic user-table unification.")
    conn.execute(text("DELETE FROM users"))


def insert_unified_records(conn: Connection, records: list[UnifiedRecord]) -> dict[str, tuple[int, str]]:
    email_to_ids: dict[str, tuple[int, str]] = {}
    for record in records:
        params = {
            "user_id": record.user_id,
            "full_name": record.full_name,
            "student_number": record.student_number,
            "email": record.email,
            "password": record.password or "!",
            "supervisor_id": record.supervisor_legacy_user_id,
            "staff_number": record.staff_number,
            "specialisation": record.specialisation,
            "role": record.legacy_role,
            "reset_token": record.reset_token,
            "reset_token_expiry": record.reset_token_expiry,
            "authenticate_student": record.authenticate_student or ("true" if record.authenticated_student else "false"),
            "microsoft_subject": record.microsoft_subject,
            "is_active": record.is_active,
            "popia_confirmed_at": record.popia_confirmed_at,
            "popia_notice_version": record.popia_notice_version,
            "popia_confirmed_ip": record.popia_confirmed_ip,
            "popia_confirmed_user_agent": record.popia_confirmed_user_agent,
            "created_at": record.created_at or datetime.utcnow(),
            "updated_at": record.updated_at or datetime.utcnow(),
            "mba_role": record.mba_role,
            "scholar_role": record.scholar_role,
            "has_profile": record.has_profile,
            "has_signature": record.has_signature,
            "has_cv": record.has_cv,
            "ethics_role": record.ethics_role,
            "authenticated_student": record.authenticated_student,
            "watched_demo": record.watched_demo,
            "mba_access": record.mba_access,
            "ethics_access": record.ethics_access,
            "first_name": record.first_name,
            "last_name": record.last_name,
        }
        row = conn.execute(
            text(
                """
                INSERT INTO users (
                    user_id, full_name, student_number, email, password, supervisor_id, staff_number, specialisation,
                    role, reset_token, reset_token_expiry, authenticate_student, microsoft_subject, is_active,
                    popia_confirmed_at, popia_notice_version, popia_confirmed_ip, popia_confirmed_user_agent,
                    created_at, updated_at, mba_role, scholar_role, has_profile, has_signature, has_cv,
                    ethics_role, authenticated_student, watched_demo, mba_access, ethics_access, first_name, last_name
                ) VALUES (
                    :user_id, :full_name, :student_number, :email, :password, :supervisor_id, :staff_number, :specialisation,
                    CAST(:role AS userrole), :reset_token, :reset_token_expiry, :authenticate_student, :microsoft_subject, :is_active,
                    :popia_confirmed_at, :popia_notice_version, :popia_confirmed_ip, :popia_confirmed_user_agent,
                    :created_at, :updated_at, :mba_role, :scholar_role, :has_profile, :has_signature, :has_cv,
                    :ethics_role, :authenticated_student, :watched_demo, :mba_access, :ethics_access, :first_name, :last_name
                )
                RETURNING integrated_id, user_id
                """
            ),
            params,
        ).mappings().one()
        email_to_ids[record.email] = (row["integrated_id"], row["user_id"])
    return email_to_ids


def update_supervisors(
    conn: Connection,
    records: list[UnifiedRecord],
    ethics_rows: list[dict[str, Any]],
    email_to_ids: dict[str, tuple[int, str]],
    ethics_id_to_email: dict[int, str],
) -> None:
    ethics_by_id = {row["id"]: row for row in ethics_rows}
    for record in records:
        if record.source_ethics_id is None:
            continue
        source_row = ethics_by_id.get(record.source_ethics_id)
        if not source_row:
            continue
        supervisor_old_id = source_row.get("supervisor_id")
        if not supervisor_old_id:
            continue
        supervisor_email = ethics_id_to_email.get(supervisor_old_id)
        if not supervisor_email or supervisor_email not in email_to_ids:
            continue
        supervisor_integrated_id, supervisor_legacy_user_id = email_to_ids[supervisor_email]
        conn.execute(
            text(
                """
                UPDATE users
                SET supervisor_integrated_id = :supervisor_integrated_id,
                    supervisor_id = :supervisor_legacy_user_id
                WHERE integrated_id = :integrated_id
                """
            ),
            {
                "integrated_id": email_to_ids[record.email][0],
                "supervisor_integrated_id": supervisor_integrated_id,
                "supervisor_legacy_user_id": supervisor_legacy_user_id,
            },
        )


def migrate_child_foreign_keys(conn: Connection) -> None:
    fk_rows = conn.execute(
        text(
            """
            select tc.constraint_name, tc.table_name, kcu.column_name, ccu.table_name as foreign_table_name
            from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu
              on tc.constraint_name = kcu.constraint_name and tc.table_schema = kcu.table_schema
            join information_schema.constraint_column_usage ccu
              on ccu.constraint_name = tc.constraint_name and ccu.table_schema = tc.table_schema
            where tc.constraint_type = 'FOREIGN KEY'
              and tc.table_schema = 'public'
              and ccu.table_name in ('mba_users', 'ethcis_users')
            order by tc.table_name, kcu.column_name
            """
        )
    ).mappings().all()

    for row in fk_rows:
        table_name = row["table_name"]
        column_name = row["column_name"]
        foreign_table_name = row["foreign_table_name"]
        conn.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT "{row["constraint_name"]}"'))
        if foreign_table_name == "mba_users":
            conn.execute(
                text(
                    f'''
                    UPDATE "{table_name}" AS target
                    SET "{column_name}" = source.integrated_id
                    FROM mba_users AS legacy
                    JOIN users AS source ON lower(source.email) = lower(legacy.email)
                    WHERE target."{column_name}" = legacy.id
                    '''
                )
            )
        else:
            conn.execute(
                text(
                    f'''
                    UPDATE "{table_name}" AS target
                    SET "{column_name}" = source.integrated_id
                    FROM ethcis_users AS legacy
                    JOIN users AS source ON lower(source.email) = lower(legacy.email)
                    WHERE target."{column_name}" = legacy.id
                    '''
                )
            )

        new_constraint_name = f'{table_name}_{column_name}_users_integrated_fkey'
        conn.execute(
            text(
                f'''
                ALTER TABLE "{table_name}"
                ADD CONSTRAINT "{new_constraint_name[:63]}"
                FOREIGN KEY ("{column_name}") REFERENCES users(integrated_id)
                '''
            )
        )


def replace_integrated_tables_with_views(conn: Connection) -> None:
    inspector = inspect(conn)
    if "mba_users_legacy" not in inspector.get_table_names():
        conn.execute(text("ALTER TABLE mba_users RENAME TO mba_users_legacy"))
    if "ethcis_users_legacy" not in inspector.get_table_names():
        conn.execute(text("ALTER TABLE ethcis_users RENAME TO ethcis_users_legacy"))

    conn.execute(text("DROP VIEW IF EXISTS mba_users CASCADE"))
    conn.execute(text("DROP VIEW IF EXISTS ethcis_users CASCADE"))

    conn.execute(
        text(
            """
            CREATE VIEW mba_users AS
            SELECT
                users.mba_role AS role,
                users.scholar_role,
                users.has_profile,
                users.has_signature,
                users.has_cv,
                users.integrated_id AS id,
                users.email,
                users.password AS password_hash,
                users.microsoft_subject,
                users.first_name,
                users.last_name,
                users.is_active,
                users.popia_confirmed_at,
                users.popia_notice_version,
                users.popia_confirmed_ip,
                users.popia_confirmed_user_agent,
                users.created_at,
                users.updated_at
            FROM users
            WHERE users.mba_access = TRUE
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE VIEW ethcis_users AS
            SELECT
                users.ethics_role AS role,
                CAST(users.student_number AS VARCHAR(40)) AS student_number,
                users.supervisor_integrated_id AS supervisor_id,
                users.staff_number,
                users.specialisation,
                users.authenticated_student,
                users.watched_demo,
                users.integrated_id AS id,
                users.email,
                users.password AS password_hash,
                users.microsoft_subject,
                users.first_name,
                users.last_name,
                users.is_active,
                users.popia_confirmed_at,
                users.popia_notice_version,
                users.popia_confirmed_ip,
                users.popia_confirmed_user_agent,
                users.created_at,
                users.updated_at
            FROM users
            WHERE users.ethics_access = TRUE
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION upsert_mba_user_view() RETURNS trigger AS $$
            DECLARE
                inserted_id BIGINT;
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    INSERT INTO users (
                        user_id, full_name, email, password, role, mba_role, scholar_role,
                        has_profile, has_signature, has_cv, microsoft_subject, first_name, last_name,
                        is_active, popia_confirmed_at, popia_notice_version, popia_confirmed_ip,
                        popia_confirmed_user_agent, created_at, updated_at, mba_access
                    ) VALUES (
                        md5(random()::text || clock_timestamp()::text || NEW.email),
                        trim(concat_ws(' ', NEW.first_name, NEW.last_name)),
                        lower(NEW.email),
                        NEW.password_hash,
                        CAST(
                            CASE
                                WHEN NEW.role = 'main_admin' THEN 'SUPER_ADMIN'
                                WHEN NEW.role = 'admin' THEN 'ADMIN'
                                WHEN NEW.role = 'student' THEN 'STUDENT'
                                WHEN NEW.scholar_role IN ('supervisor', 'both') THEN 'SUPERVISOR'
                                WHEN NEW.role = 'examiner' OR NEW.scholar_role = 'examiner' THEN 'REVIEWER'
                                WHEN NEW.role = 'hdc' THEN 'REC'
                                ELSE 'STUDENT'
                            END AS userrole
                        ),
                        NEW.role,
                        NEW.scholar_role,
                        COALESCE(NEW.has_profile, FALSE),
                        COALESCE(NEW.has_signature, FALSE),
                        COALESCE(NEW.has_cv, FALSE),
                        NEW.microsoft_subject,
                        NEW.first_name,
                        NEW.last_name,
                        COALESCE(NEW.is_active, TRUE),
                        NEW.popia_confirmed_at,
                        NEW.popia_notice_version,
                        NEW.popia_confirmed_ip,
                        NEW.popia_confirmed_user_agent,
                        COALESCE(NEW.created_at, CURRENT_TIMESTAMP),
                        COALESCE(NEW.updated_at, CURRENT_TIMESTAMP),
                        TRUE
                    )
                    RETURNING integrated_id INTO inserted_id;
                    NEW.id := inserted_id;
                    RETURN NEW;
                ELSIF TG_OP = 'UPDATE' THEN
                    UPDATE users
                    SET
                        email = lower(COALESCE(NEW.email, email)),
                        password = COALESCE(NEW.password_hash, password),
                        mba_role = COALESCE(NEW.role, mba_role),
                        scholar_role = COALESCE(NEW.scholar_role, scholar_role),
                        has_profile = COALESCE(NEW.has_profile, has_profile),
                        has_signature = COALESCE(NEW.has_signature, has_signature),
                        has_cv = COALESCE(NEW.has_cv, has_cv),
                        microsoft_subject = COALESCE(NEW.microsoft_subject, microsoft_subject),
                        first_name = COALESCE(NEW.first_name, first_name),
                        last_name = COALESCE(NEW.last_name, last_name),
                        full_name = trim(concat_ws(' ', COALESCE(NEW.first_name, first_name), COALESCE(NEW.last_name, last_name))),
                        is_active = COALESCE(NEW.is_active, is_active),
                        popia_confirmed_at = COALESCE(NEW.popia_confirmed_at, popia_confirmed_at),
                        popia_notice_version = COALESCE(NEW.popia_notice_version, popia_notice_version),
                        popia_confirmed_ip = COALESCE(NEW.popia_confirmed_ip, popia_confirmed_ip),
                        popia_confirmed_user_agent = COALESCE(NEW.popia_confirmed_user_agent, popia_confirmed_user_agent),
                        mba_access = TRUE,
                        updated_at = CURRENT_TIMESTAMP,
                        role = CAST(
                            CASE
                                WHEN COALESCE(NEW.role, mba_role) = 'main_admin' THEN 'SUPER_ADMIN'
                                WHEN COALESCE(NEW.role, mba_role) = 'admin' THEN 'ADMIN'
                                WHEN COALESCE(NEW.role, mba_role) = 'student' THEN 'STUDENT'
                                WHEN COALESCE(NEW.scholar_role, scholar_role) IN ('supervisor', 'both') THEN 'SUPERVISOR'
                                WHEN COALESCE(NEW.role, mba_role) = 'examiner' OR COALESCE(NEW.scholar_role, scholar_role) = 'examiner' THEN 'REVIEWER'
                                WHEN COALESCE(NEW.role, mba_role) = 'hdc' THEN 'REC'
                                ELSE role::text
                            END AS userrole
                        )
                    WHERE integrated_id = OLD.id;
                    RETURN NEW;
                ELSE
                    UPDATE users
                    SET mba_access = FALSE,
                        mba_role = NULL,
                        scholar_role = NULL,
                        has_profile = FALSE,
                        has_signature = FALSE,
                        has_cv = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE integrated_id = OLD.id;
                    DELETE FROM users WHERE integrated_id = OLD.id AND mba_access = FALSE AND ethics_access = FALSE;
                    RETURN OLD;
                END IF;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    conn.execute(text("DROP TRIGGER IF EXISTS mba_users_view_trigger ON mba_users"))
    conn.execute(
        text(
            """
            CREATE TRIGGER mba_users_view_trigger
            INSTEAD OF INSERT OR UPDATE OR DELETE ON mba_users
            FOR EACH ROW EXECUTE FUNCTION upsert_mba_user_view()
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION upsert_ethics_user_view() RETURNS trigger AS $$
            DECLARE
                inserted_id BIGINT;
                supervisor_legacy_id VARCHAR(255);
            BEGIN
                IF NEW.supervisor_id IS NOT NULL THEN
                    SELECT user_id INTO supervisor_legacy_id
                    FROM users
                    WHERE integrated_id = NEW.supervisor_id;
                ELSE
                    supervisor_legacy_id := NULL;
                END IF;

                IF TG_OP = 'INSERT' THEN
                    INSERT INTO users (
                        user_id, full_name, student_number, email, password, supervisor_id, staff_number, specialisation,
                        role, ethics_role, authenticate_student, authenticated_student, watched_demo, supervisor_integrated_id,
                        microsoft_subject, first_name, last_name, is_active, popia_confirmed_at, popia_notice_version,
                        popia_confirmed_ip, popia_confirmed_user_agent, created_at, updated_at, ethics_access
                    ) VALUES (
                        md5(random()::text || clock_timestamp()::text || NEW.email),
                        trim(concat_ws(' ', NEW.first_name, NEW.last_name)),
                        NULLIF(NEW.student_number, '')::INTEGER,
                        lower(NEW.email),
                        NEW.password_hash,
                        supervisor_legacy_id,
                        NEW.staff_number,
                        NEW.specialisation,
                        CAST(upper(COALESCE(NEW.role, 'student')) AS userrole),
                        NEW.role,
                        CASE WHEN COALESCE(NEW.authenticated_student, FALSE) THEN 'true' ELSE 'false' END,
                        COALESCE(NEW.authenticated_student, FALSE),
                        COALESCE(NEW.watched_demo, FALSE),
                        NEW.supervisor_id,
                        NEW.microsoft_subject,
                        NEW.first_name,
                        NEW.last_name,
                        COALESCE(NEW.is_active, TRUE),
                        NEW.popia_confirmed_at,
                        NEW.popia_notice_version,
                        NEW.popia_confirmed_ip,
                        NEW.popia_confirmed_user_agent,
                        COALESCE(NEW.created_at, CURRENT_TIMESTAMP),
                        COALESCE(NEW.updated_at, CURRENT_TIMESTAMP),
                        TRUE
                    )
                    RETURNING integrated_id INTO inserted_id;
                    NEW.id := inserted_id;
                    RETURN NEW;
                ELSIF TG_OP = 'UPDATE' THEN
                    UPDATE users
                    SET
                        email = lower(COALESCE(NEW.email, email)),
                        password = COALESCE(NEW.password_hash, password),
                        ethics_role = COALESCE(NEW.role, ethics_role),
                        student_number = COALESCE(NULLIF(NEW.student_number, '')::INTEGER, student_number),
                        supervisor_integrated_id = COALESCE(NEW.supervisor_id, supervisor_integrated_id),
                        supervisor_id = COALESCE(supervisor_legacy_id, supervisor_id),
                        staff_number = COALESCE(NEW.staff_number, staff_number),
                        specialisation = COALESCE(NEW.specialisation, specialisation),
                        authenticate_student = CASE WHEN COALESCE(NEW.authenticated_student, authenticated_student) THEN 'true' ELSE 'false' END,
                        authenticated_student = COALESCE(NEW.authenticated_student, authenticated_student),
                        watched_demo = COALESCE(NEW.watched_demo, watched_demo),
                        microsoft_subject = COALESCE(NEW.microsoft_subject, microsoft_subject),
                        first_name = COALESCE(NEW.first_name, first_name),
                        last_name = COALESCE(NEW.last_name, last_name),
                        full_name = trim(concat_ws(' ', COALESCE(NEW.first_name, first_name), COALESCE(NEW.last_name, last_name))),
                        is_active = COALESCE(NEW.is_active, is_active),
                        popia_confirmed_at = COALESCE(NEW.popia_confirmed_at, popia_confirmed_at),
                        popia_notice_version = COALESCE(NEW.popia_notice_version, popia_notice_version),
                        popia_confirmed_ip = COALESCE(NEW.popia_confirmed_ip, popia_confirmed_ip),
                        popia_confirmed_user_agent = COALESCE(NEW.popia_confirmed_user_agent, popia_confirmed_user_agent),
                        ethics_access = TRUE,
                        updated_at = CURRENT_TIMESTAMP,
                        role = CAST(upper(COALESCE(NEW.role, ethics_role, role::text)) AS userrole)
                    WHERE integrated_id = OLD.id;
                    RETURN NEW;
                ELSE
                    UPDATE users
                    SET ethics_access = FALSE,
                        ethics_role = NULL,
                        supervisor_integrated_id = NULL,
                        supervisor_id = NULL,
                        authenticated_student = FALSE,
                        watched_demo = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE integrated_id = OLD.id;
                    DELETE FROM users WHERE integrated_id = OLD.id AND mba_access = FALSE AND ethics_access = FALSE;
                    RETURN OLD;
                END IF;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    conn.execute(text("DROP TRIGGER IF EXISTS ethcis_users_view_trigger ON ethcis_users"))
    conn.execute(
        text(
            """
            CREATE TRIGGER ethcis_users_view_trigger
            INSTEAD OF INSERT OR UPDATE OR DELETE ON ethcis_users
            FOR EACH ROW EXECUTE FUNCTION upsert_ethics_user_view()
            """
        )
    )


def verify(conn: Connection) -> None:
    rows = conn.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM users) AS unified_users,
                (SELECT COUNT(*) FROM mba_users) AS mba_view_rows,
                (SELECT COUNT(*) FROM ethcis_users) AS ethics_view_rows
            """
        )
    ).one()
    print(f"users={rows[0]} mba_users={rows[1]} ethcis_users={rows[2]}")


def main() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required")

    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        inspector = inspect(conn)
        if "mba_users" not in inspector.get_table_names() or "ethcis_users" not in inspector.get_table_names():
            raise RuntimeError("Expected physical mba_users and ethcis_users tables before unification.")

        legacy_rows = fetch_rows(conn, "users")
        mba_rows = fetch_rows(conn, "mba_users")
        ethics_rows = fetch_rows(conn, "ethcis_users")

        ensure_unified_columns(conn)
        records, _mba_map, ethics_map = build_unified_records(mba_rows, ethics_rows, legacy_rows)
        truncate_users_if_legacy_empty(conn, legacy_rows)
        email_to_ids = insert_unified_records(conn, records)
        update_supervisors(conn, records, ethics_rows, email_to_ids, ethics_map)
        migrate_child_foreign_keys(conn)
        replace_integrated_tables_with_views(conn)
        verify(conn)


if __name__ == "__main__":
    main()
