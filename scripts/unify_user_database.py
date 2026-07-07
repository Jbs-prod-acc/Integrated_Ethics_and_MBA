from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DB = ROOT_DIR / "app.db"
ETHICS_DB = ROOT_DIR / "app" / "ethics_production_app" / "ethics.db"

ETHICS_TABLES_TO_COPY = [
    "form_a",
    "form_a_archive",
    "form_a_requirements",
    "form_b",
    "form_b_archive",
    "form_c",
    "form_c_archive",
    "form_d",
    "form_uploads",
    "login_logs",
    "logs",
    "rec",
    "user_activity_logs",
    "user_information",
    "watched",
]

ROLE_PRIORITY = {
    "main_admin": 100,
    "super_admin": 95,
    "admin": 90,
    "hdc": 80,
    "rec": 75,
    "dean": 70,
    "examiner": 65,
    "supervisor": 60,
    "reviewer": 55,
    "scholar": 50,
    "student": 10,
}


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower() or None


def normalize_bool(value) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(bool(value))
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "y"} else 0


def split_name(full_name: str | None) -> tuple[str | None, str | None]:
    clean = (full_name or "").strip()
    if not clean:
        return None, None
    parts = clean.split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def combine_name(first_name: str | None, last_name: str | None, fallback: str | None = None) -> str | None:
    merged = " ".join(part for part in [first_name, last_name] if part).strip()
    return merged or (fallback.strip() if fallback else None)


def choose_role(existing: str | None, candidate: str | None) -> str | None:
    if not candidate:
        return existing
    if not existing:
        return candidate
    return candidate if ROLE_PRIORITY.get(candidate, 0) > ROLE_PRIORITY.get(existing, 0) else existing


@dataclass
class UnifiedUserRecord:
    user_id: int
    email: str | None = None
    legacy_user_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    legacy_full_name: str | None = None
    staff_student_number: str | None = None
    role: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    password: str | None = None
    authenticated: int = 0
    is_active: int = 1
    mba_role: str | None = None
    ethics_role: str | None = None
    scholar_role: str | None = None
    microsoft_subject: str | None = None
    has_profile: int = 0
    has_signature: int = 0
    has_cv: int = 0
    supervisor_user_id: int | None = None
    supervisor_legacy_user_id: str | None = None
    student_number: str | None = None
    staff_number: str | None = None
    specialisation: str | None = None
    authenticated_student: int = 0
    watched_demo: int = 0
    reset_token: str | None = None
    reset_token_expiry: str | None = None
    popia_confirmed_at: str | None = None
    popia_notice_version: str | None = None
    popia_confirmed_ip: str | None = None
    popia_confirmed_user_agent: str | None = None
    mba_access: int = 0
    ethics_access: int = 0


@dataclass
class UnifiedProfileRecord:
    user_id: int
    title: str | None = None
    module: str | None = None
    degree: str | None = None
    secondary_email: str | None = None
    name: str | None = None
    surname: str | None = None
    contact: str | None = None
    student_number: str | None = None
    block_id: str | None = None
    address: str | None = None
    postal_code: str | None = None
    id_passport_number: str | None = None
    default_signing_location: str | None = None
    form_defaults: str | None = None
    skills: str | None = None
    department: str | None = None
    position: str | None = None
    staff_number: str | None = None
    students: int | None = None
    qualification: str | None = None
    affiliation: str | None = None
    research_themes: str | None = None
    research_interests: str | None = None
    research_disciplines: str | None = None
    academic_experience: int | None = None
    students_supervised_total: int | None = None
    students_assessed_total: int | None = None
    publication_count: int | None = None
    selected_publications: str | None = None
    scholarly_profile_links: str | None = None
    approved_before: int | None = None
    international_assessor: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


def backup_file(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    target = path.with_suffix(path.suffix + f".backup-{timestamp}")
    shutil.copy2(path, target)
    return target


def create_unified_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE IF NOT EXISTS "user_Registration" (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            legacy_user_id TEXT UNIQUE,
            first_name TEXT,
            last_name TEXT,
            email TEXT UNIQUE,
            staff_student_number TEXT,
            role TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            password TEXT,
            authenticated BOOLEAN NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            mba_role TEXT,
            ethics_role TEXT,
            scholar_role TEXT,
            microsoft_subject TEXT UNIQUE,
            has_profile BOOLEAN NOT NULL DEFAULT 0,
            has_signature BOOLEAN NOT NULL DEFAULT 0,
            has_cv BOOLEAN NOT NULL DEFAULT 0,
            supervisor_user_id INTEGER,
            supervisor_legacy_user_id TEXT,
            student_number TEXT,
            staff_number TEXT,
            specialisation TEXT,
            authenticated_student BOOLEAN NOT NULL DEFAULT 0,
            watched_demo BOOLEAN NOT NULL DEFAULT 0,
            reset_token TEXT,
            reset_token_expiry DATETIME,
            popia_confirmed_at DATETIME,
            popia_notice_version TEXT,
            popia_confirmed_ip TEXT,
            popia_confirmed_user_agent TEXT,
            mba_access BOOLEAN NOT NULL DEFAULT 0,
            ethics_access BOOLEAN NOT NULL DEFAULT 0,
            legacy_full_name TEXT
        );

        CREATE TABLE IF NOT EXISTS user_profile (
            user_id INTEGER PRIMARY KEY,
            title TEXT,
            module TEXT,
            degree TEXT,
            secondary_email TEXT,
            name TEXT,
            surname TEXT,
            contact TEXT,
            student_number TEXT,
            block_id TEXT,
            address TEXT,
            postal_code TEXT,
            id_passport_number TEXT,
            default_signing_location TEXT,
            form_defaults TEXT,
            skills TEXT,
            department TEXT,
            position TEXT,
            staff_number TEXT,
            students INTEGER,
            qualification TEXT,
            affiliation TEXT,
            research_themes TEXT,
            research_interests TEXT,
            research_disciplines TEXT,
            academic_experience INTEGER,
            students_supervised_total INTEGER,
            students_assessed_total INTEGER,
            publication_count INTEGER,
            selected_publications TEXT,
            scholarly_profile_links TEXT,
            approved_before BOOLEAN,
            international_assessor BOOLEAN,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY(user_id) REFERENCES "user_Registration"(user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_registration_email ON "user_Registration"(email);
        CREATE INDEX IF NOT EXISTS idx_user_registration_legacy_user_id ON "user_Registration"(legacy_user_id);
        CREATE INDEX IF NOT EXISTS idx_user_registration_mba_role ON "user_Registration"(mba_role);
        CREATE INDEX IF NOT EXISTS idx_user_registration_ethics_role ON "user_Registration"(ethics_role);
        CREATE INDEX IF NOT EXISTS idx_user_profile_student_number ON user_profile(student_number);
        """
    )


def copy_ethics_tables_into_app_db(app_conn: sqlite3.Connection, ethics_conn: sqlite3.Connection) -> list[str]:
    available_tables = {
        row["name"]
        for row in ethics_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    skipped_tables: list[str] = []
    for table_name in ETHICS_TABLES_TO_COPY:
        if table_name not in available_tables:
            skipped_tables.append(f"{table_name}:missing")
            continue
        source_sql = ethics_conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        if not source_sql or not source_sql["sql"]:
            skipped_tables.append(f"{table_name}:missing-sql")
            continue
        try:
            rows = ethics_conn.execute(f'SELECT * FROM "{table_name}"').fetchall()
        except sqlite3.OperationalError as exc:
            skipped_tables.append(f"{table_name}:unreadable:{exc}")
            continue

        app_conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        app_conn.execute(source_sql["sql"])
        if rows:
            placeholders = ", ".join("?" for _ in rows[0].keys())
            columns = ", ".join(f'"{column}"' for column in rows[0].keys())
            app_conn.executemany(
                f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})',
                [tuple(row) for row in rows],
            )
    return skipped_tables


def build_unified_records(
    app_conn: sqlite3.Connection,
    ethics_conn: sqlite3.Connection,
) -> tuple[list[UnifiedUserRecord], dict[int, UnifiedProfileRecord]]:
    mba_user_rows = app_conn.execute('SELECT * FROM "mba_users"').fetchall()
    ethics_user_rows = app_conn.execute('SELECT * FROM "ethcis_users"').fetchall()
    mba_student_rows = app_conn.execute('SELECT * FROM "mba_student_profiles"').fetchall()
    mba_scholar_rows = app_conn.execute('SELECT * FROM "mba_scholar_profiles"').fetchall()
    legacy_user_rows = ethics_conn.execute('SELECT * FROM "users"').fetchall()
    watched_rows = {
        row["user_id"]: row["watched"]
        for row in ethics_conn.execute('SELECT user_id, watched FROM "watched"').fetchall()
    }

    max_existing_id = 0
    for row in mba_user_rows + ethics_user_rows:
        current_id = row["id"] or 0
        if current_id > max_existing_id:
            max_existing_id = current_id
    next_id = max_existing_id + 1

    records_by_key: dict[str, UnifiedUserRecord] = {}
    records_by_id: dict[int, UnifiedUserRecord] = {}
    records_by_legacy_id: dict[str, UnifiedUserRecord] = {}
    profiles: dict[int, UnifiedProfileRecord] = {}

    def identity_key(email: str | None, fallback: str) -> str:
        return normalize_email(email) or fallback

    def get_or_create(email: str | None, preferred_id: int | None = None, legacy_user_id: str | None = None) -> UnifiedUserRecord:
        nonlocal next_id
        key = identity_key(email, f"legacy:{legacy_user_id or next_id}")
        existing = records_by_key.get(key)
        if existing:
            if legacy_user_id and not existing.legacy_user_id:
                existing.legacy_user_id = legacy_user_id
                records_by_legacy_id[legacy_user_id] = existing
            return existing

        assigned_id = preferred_id if preferred_id and preferred_id not in records_by_id else next_id
        if assigned_id == next_id:
            next_id += 1
        else:
            next_id = max(next_id, assigned_id + 1)

        record = UnifiedUserRecord(user_id=assigned_id, email=normalize_email(email))
        records_by_key[key] = record
        records_by_id[record.user_id] = record
        if legacy_user_id:
            record.legacy_user_id = legacy_user_id
            records_by_legacy_id[legacy_user_id] = record
        return record

    for row in mba_user_rows:
        record = get_or_create(row["email"], preferred_id=row["id"])
        record.first_name = record.first_name or row["first_name"]
        record.last_name = record.last_name or row["last_name"]
        record.email = normalize_email(row["email"]) or record.email
        record.password = row["password_hash"] or record.password
        record.is_active = normalize_bool(row["is_active"]) if row["is_active"] is not None else record.is_active
        record.created_at = record.created_at or row["created_at"]
        record.updated_at = row["updated_at"] or record.updated_at
        record.role = choose_role(record.role, row["role"])
        record.mba_role = row["role"] or record.mba_role
        record.scholar_role = row["scholar_role"] or record.scholar_role
        record.microsoft_subject = row["microsoft_subject"] or record.microsoft_subject
        record.has_profile = normalize_bool(row["has_profile"]) or record.has_profile
        record.has_signature = normalize_bool(row["has_signature"]) or record.has_signature
        record.has_cv = normalize_bool(row["has_cv"]) or record.has_cv
        record.popia_confirmed_at = row["popia_confirmed_at"] or record.popia_confirmed_at
        record.popia_notice_version = row["popia_notice_version"] or record.popia_notice_version
        record.popia_confirmed_ip = row["popia_confirmed_ip"] or record.popia_confirmed_ip
        record.popia_confirmed_user_agent = row["popia_confirmed_user_agent"] or record.popia_confirmed_user_agent
        record.mba_access = 1

    for row in ethics_user_rows:
        record = get_or_create(row["email"], preferred_id=row["id"])
        record.first_name = record.first_name or row["first_name"]
        record.last_name = record.last_name or row["last_name"]
        record.email = normalize_email(row["email"]) or record.email
        record.password = row["password_hash"] or record.password
        record.is_active = normalize_bool(row["is_active"]) if row["is_active"] is not None else record.is_active
        record.created_at = record.created_at or row["created_at"]
        record.updated_at = row["updated_at"] or record.updated_at
        record.role = choose_role(record.role, row["role"])
        record.ethics_role = row["role"] or record.ethics_role
        record.microsoft_subject = row["microsoft_subject"] or record.microsoft_subject
        record.student_number = record.student_number or row["student_number"]
        record.staff_number = record.staff_number or row["staff_number"]
        record.specialisation = record.specialisation or row["specialisation"]
        record.authenticated_student = max(record.authenticated_student, normalize_bool(row["authenticated_student"]))
        record.authenticated = max(record.authenticated, normalize_bool(row["authenticated_student"]))
        record.watched_demo = max(record.watched_demo, normalize_bool(row["watched_demo"]))
        record.popia_confirmed_at = row["popia_confirmed_at"] or record.popia_confirmed_at
        record.popia_notice_version = row["popia_notice_version"] or record.popia_notice_version
        record.popia_confirmed_ip = row["popia_confirmed_ip"] or record.popia_confirmed_ip
        record.popia_confirmed_user_agent = row["popia_confirmed_user_agent"] or record.popia_confirmed_user_agent
        record.ethics_access = 1
        if row["supervisor_id"]:
            record.supervisor_user_id = row["supervisor_id"]

    for row in legacy_user_rows:
        record = get_or_create(row["email"], legacy_user_id=row["user_id"])
        first_name, last_name = split_name(row["full_name"])
        record.first_name = record.first_name or first_name
        record.last_name = record.last_name or last_name
        record.legacy_full_name = record.legacy_full_name or row["full_name"]
        record.email = normalize_email(row["email"]) or record.email
        record.password = record.password or row["password"]
        legacy_role = (row["role"] or "").strip().lower() or None
        record.role = choose_role(record.role, legacy_role)
        record.ethics_role = record.ethics_role or legacy_role
        record.student_number = record.student_number or (str(row["student_number"]) if row["student_number"] is not None else None)
        record.staff_number = record.staff_number or row["staff_number"]
        record.specialisation = record.specialisation or row["specialisation"]
        record.reset_token = row["reset_token"] or record.reset_token
        record.reset_token_expiry = row["reset_token_expiry"] or record.reset_token_expiry
        record.authenticated_student = max(record.authenticated_student, normalize_bool(row["authenticate_student"]))
        record.authenticated = max(record.authenticated, normalize_bool(row["authenticate_student"]))
        record.watched_demo = max(record.watched_demo, normalize_bool(watched_rows.get(row["user_id"])))
        record.ethics_access = 1
        record.is_active = max(record.is_active, normalize_bool(row["authenticate_student"]))
        if row["supervisor_id"]:
            record.supervisor_legacy_user_id = row["supervisor_id"]

    for record in records_by_id.values():
        record.staff_student_number = (
            record.staff_student_number
            or record.student_number
            or record.staff_number
        )
        record.legacy_full_name = combine_name(record.first_name, record.last_name, record.legacy_full_name)
        record.created_at = record.created_at or datetime.utcnow().isoformat(sep=" ", timespec="seconds")
        record.updated_at = record.updated_at or record.created_at
        if record.ethics_access and not record.ethics_role and record.role:
            record.ethics_role = record.role
        if record.mba_access and not record.mba_role and record.role in {"student", "admin", "main_admin", "examiner", "hdc", "scholar"}:
            record.mba_role = record.role

    for row in mba_student_rows:
        profile = profiles.setdefault(row["user_id"], UnifiedProfileRecord(user_id=row["user_id"]))
        profile.name = profile.name or row["name"]
        profile.surname = profile.surname or row["surname"]
        profile.title = profile.title or row["title"]
        profile.contact = profile.contact or row["contact"]
        profile.student_number = profile.student_number or row["student_number"]
        profile.secondary_email = profile.secondary_email or row["secondary_email"]
        profile.module = profile.module or row["module"]
        profile.block_id = profile.block_id or row["block_id"]
        profile.degree = profile.degree or row["degree"]
        profile.address = profile.address or row["address"]
        profile.postal_code = profile.postal_code or row["postal_code"]
        profile.id_passport_number = profile.id_passport_number or row["id_passport_number"]
        profile.default_signing_location = profile.default_signing_location or row["default_signing_location"]
        profile.form_defaults = profile.form_defaults or row["form_defaults"]
        profile.created_at = profile.created_at or row["created_at"]
        profile.updated_at = profile.updated_at or row["created_at"]

    for row in mba_scholar_rows:
        profile = profiles.setdefault(row["user_id"], UnifiedProfileRecord(user_id=row["user_id"]))
        profile.name = profile.name or row["name"]
        profile.surname = profile.surname or row["surname"]
        profile.title = profile.title or row["title"]
        profile.skills = profile.skills or row["skills"]
        profile.address = profile.address or row["address"]
        profile.department = profile.department or row["department"]
        profile.position = profile.position or row["position"]
        profile.contact = profile.contact or row["contact"]
        profile.staff_number = profile.staff_number or row["staff_number"]
        profile.id_passport_number = profile.id_passport_number or row["id_passport_number"]
        profile.postal_code = profile.postal_code or row["postal_code"]
        profile.default_signing_location = profile.default_signing_location or row["default_signing_location"]
        profile.students = row["students"] if row["students"] is not None else profile.students
        profile.qualification = profile.qualification or row["qualification"]
        profile.affiliation = profile.affiliation or row["affiliation"]
        profile.research_themes = profile.research_themes or row["research_themes"]
        profile.research_interests = profile.research_interests or row["research_interests"]
        profile.research_disciplines = profile.research_disciplines or row["research_disciplines"]
        profile.academic_experience = row["academic_experience"] if row["academic_experience"] is not None else profile.academic_experience
        profile.students_supervised_total = row["students_supervised_total"] if row["students_supervised_total"] is not None else profile.students_supervised_total
        profile.students_assessed_total = row["students_assessed_total"] if row["students_assessed_total"] is not None else profile.students_assessed_total
        profile.publication_count = row["publication_count"] if row["publication_count"] is not None else profile.publication_count
        profile.selected_publications = profile.selected_publications or row["selected_publications"]
        profile.scholarly_profile_links = profile.scholarly_profile_links or row["scholarly_profile_links"]
        profile.approved_before = normalize_bool(row["approved_before"]) if row["approved_before"] is not None else profile.approved_before
        profile.international_assessor = normalize_bool(row["international_assessor"]) if row["international_assessor"] is not None else profile.international_assessor
        profile.form_defaults = profile.form_defaults or row["form_defaults"]
        profile.created_at = profile.created_at or row["created_at"]
        profile.updated_at = profile.updated_at or row["created_at"]

    for record in records_by_id.values():
        if record.supervisor_legacy_user_id and record.supervisor_legacy_user_id in records_by_legacy_id:
            record.supervisor_user_id = records_by_legacy_id[record.supervisor_legacy_user_id].user_id

    return list(sorted(records_by_id.values(), key=lambda item: item.user_id)), profiles


def replace_unified_data(conn: sqlite3.Connection, users: list[UnifiedUserRecord], profiles: dict[int, UnifiedProfileRecord]) -> None:
    conn.execute('DELETE FROM user_profile')
    conn.execute('DELETE FROM "user_Registration"')

    conn.executemany(
        """
        INSERT INTO "user_Registration" (
            user_id, legacy_user_id, first_name, last_name, email, staff_student_number, role,
            created_at, updated_at, password, authenticated, is_active, mba_role, ethics_role,
            scholar_role, microsoft_subject, has_profile, has_signature, has_cv, supervisor_user_id,
            supervisor_legacy_user_id, student_number, staff_number, specialisation, authenticated_student,
            watched_demo, reset_token, reset_token_expiry, popia_confirmed_at, popia_notice_version,
            popia_confirmed_ip, popia_confirmed_user_agent, mba_access, ethics_access, legacy_full_name
        ) VALUES (
            :user_id, :legacy_user_id, :first_name, :last_name, :email, :staff_student_number, :role,
            :created_at, :updated_at, :password, :authenticated, :is_active, :mba_role, :ethics_role,
            :scholar_role, :microsoft_subject, :has_profile, :has_signature, :has_cv, :supervisor_user_id,
            :supervisor_legacy_user_id, :student_number, :staff_number, :specialisation, :authenticated_student,
            :watched_demo, :reset_token, :reset_token_expiry, :popia_confirmed_at, :popia_notice_version,
            :popia_confirmed_ip, :popia_confirmed_user_agent, :mba_access, :ethics_access, :legacy_full_name
        )
        """,
        [record.__dict__ for record in users],
    )

    conn.executemany(
        """
        INSERT INTO user_profile (
            user_id, title, module, degree, secondary_email, name, surname, contact, student_number,
            block_id, address, postal_code, id_passport_number, default_signing_location, form_defaults,
            skills, department, position, staff_number, students, qualification, affiliation,
            research_themes, research_interests, research_disciplines, academic_experience,
            students_supervised_total, students_assessed_total, publication_count, selected_publications,
            scholarly_profile_links, approved_before, international_assessor, created_at, updated_at
        ) VALUES (
            :user_id, :title, :module, :degree, :secondary_email, :name, :surname, :contact, :student_number,
            :block_id, :address, :postal_code, :id_passport_number, :default_signing_location, :form_defaults,
            :skills, :department, :position, :staff_number, :students, :qualification, :affiliation,
            :research_themes, :research_interests, :research_disciplines, :academic_experience,
            :students_supervised_total, :students_assessed_total, :publication_count, :selected_publications,
            :scholarly_profile_links, :approved_before, :international_assessor, :created_at, :updated_at
        )
        """,
        [profile.__dict__ for profile in profiles.values()],
    )


def install_compatibility_views(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP VIEW IF EXISTS mba_users;
        DROP VIEW IF EXISTS mba_student_profiles;
        DROP VIEW IF EXISTS mba_scholar_profiles;
        DROP VIEW IF EXISTS ethcis_users;
        DROP VIEW IF EXISTS users;

        DROP TABLE IF EXISTS mba_users;
        DROP TABLE IF EXISTS mba_student_profiles;
        DROP TABLE IF EXISTS mba_scholar_profiles;
        DROP TABLE IF EXISTS ethcis_users;

        CREATE VIEW mba_users AS
        SELECT
            COALESCE(mba_role, role) AS role,
            scholar_role,
            has_profile,
            has_signature,
            has_cv,
            user_id AS id,
            email,
            password AS password_hash,
            microsoft_subject,
            first_name,
            last_name,
            is_active,
            popia_confirmed_at,
            popia_notice_version,
            popia_confirmed_ip,
            popia_confirmed_user_agent,
            created_at,
            updated_at
        FROM "user_Registration"
        WHERE mba_access = 1 OR mba_role IS NOT NULL;

        CREATE VIEW ethcis_users AS
        SELECT
            COALESCE(ethics_role, role) AS role,
            student_number,
            supervisor_user_id AS supervisor_id,
            staff_number,
            specialisation,
            authenticated_student,
            watched_demo,
            user_id AS id,
            email,
            password AS password_hash,
            microsoft_subject,
            first_name,
            last_name,
            is_active,
            popia_confirmed_at,
            popia_notice_version,
            popia_confirmed_ip,
            popia_confirmed_user_agent,
            created_at,
            updated_at
        FROM "user_Registration"
        WHERE ethics_access = 1 OR ethics_role IS NOT NULL;

        CREATE VIEW mba_student_profiles AS
        SELECT
            user_id AS id,
            user_id,
            name,
            surname,
            title,
            contact,
            student_number,
            secondary_email,
            module,
            block_id,
            degree,
            address,
            postal_code,
            id_passport_number,
            default_signing_location,
            form_defaults,
            created_at
        FROM user_profile;

        CREATE VIEW mba_scholar_profiles AS
        SELECT
            user_id AS id,
            user_id,
            name,
            surname,
            title,
            skills,
            address,
            department,
            position,
            contact,
            staff_number,
            id_passport_number,
            postal_code,
            default_signing_location,
            COALESCE(students, 0) AS students,
            qualification,
            affiliation,
            research_themes,
            research_interests,
            research_disciplines,
            COALESCE(academic_experience, 0) AS academic_experience,
            COALESCE(students_supervised_total, 0) AS students_supervised_total,
            COALESCE(students_assessed_total, 0) AS students_assessed_total,
            COALESCE(publication_count, 0) AS publication_count,
            selected_publications,
            scholarly_profile_links,
            COALESCE(approved_before, 0) AS approved_before,
            COALESCE(international_assessor, 0) AS international_assessor,
            form_defaults,
            created_at
        FROM user_profile;

        CREATE VIEW users AS
        SELECT
            COALESCE(legacy_user_id, 'app-' || user_id) AS user_id,
            COALESCE(legacy_full_name, trim(COALESCE(first_name, '') || ' ' || COALESCE(last_name, ''))) AS full_name,
            student_number,
            email,
            password,
            COALESCE(
                (SELECT supervisor.legacy_user_id FROM "user_Registration" supervisor WHERE supervisor.user_id = current_users.supervisor_user_id),
                supervisor_legacy_user_id
            ) AS supervisor_id,
            staff_number,
            specialisation,
            UPPER(COALESCE(ethics_role, role, 'student')) AS role,
            reset_token,
            reset_token_expiry,
            CASE WHEN authenticated_student = 1 THEN 'true' ELSE 'false' END AS authenticate_student
        FROM "user_Registration" AS current_users
        WHERE ethics_access = 1 OR ethics_role IS NOT NULL OR legacy_user_id IS NOT NULL;
        """
    )

    conn.executescript(
        """
        CREATE TRIGGER mba_users_insert
        INSTEAD OF INSERT ON mba_users
        BEGIN
            INSERT INTO "user_Registration" (
                user_id, email, password, first_name, last_name, is_active, created_at, updated_at,
                mba_role, role, scholar_role, microsoft_subject, has_profile, has_signature, has_cv,
                popia_confirmed_at, popia_notice_version, popia_confirmed_ip, popia_confirmed_user_agent, mba_access
            ) VALUES (
                NEW.id, lower(NEW.email), NEW.password_hash, NEW.first_name, NEW.last_name, COALESCE(NEW.is_active, 1),
                COALESCE(NEW.created_at, CURRENT_TIMESTAMP), COALESCE(NEW.updated_at, CURRENT_TIMESTAMP),
                NEW.role, COALESCE(NEW.role, 'student'), NEW.scholar_role, NEW.microsoft_subject,
                COALESCE(NEW.has_profile, 0), COALESCE(NEW.has_signature, 0), COALESCE(NEW.has_cv, 0),
                NEW.popia_confirmed_at, NEW.popia_notice_version, NEW.popia_confirmed_ip, NEW.popia_confirmed_user_agent, 1
            )
            ON CONFLICT(email) DO UPDATE SET
                password = COALESCE(excluded.password, "user_Registration".password),
                first_name = COALESCE(excluded.first_name, "user_Registration".first_name),
                last_name = COALESCE(excluded.last_name, "user_Registration".last_name),
                is_active = COALESCE(excluded.is_active, "user_Registration".is_active),
                updated_at = COALESCE(excluded.updated_at, CURRENT_TIMESTAMP),
                mba_role = COALESCE(excluded.mba_role, "user_Registration".mba_role),
                role = COALESCE(excluded.role, "user_Registration".role),
                scholar_role = COALESCE(excluded.scholar_role, "user_Registration".scholar_role),
                microsoft_subject = COALESCE(excluded.microsoft_subject, "user_Registration".microsoft_subject),
                has_profile = COALESCE(excluded.has_profile, "user_Registration".has_profile),
                has_signature = COALESCE(excluded.has_signature, "user_Registration".has_signature),
                has_cv = COALESCE(excluded.has_cv, "user_Registration".has_cv),
                popia_confirmed_at = COALESCE(excluded.popia_confirmed_at, "user_Registration".popia_confirmed_at),
                popia_notice_version = COALESCE(excluded.popia_notice_version, "user_Registration".popia_notice_version),
                popia_confirmed_ip = COALESCE(excluded.popia_confirmed_ip, "user_Registration".popia_confirmed_ip),
                popia_confirmed_user_agent = COALESCE(excluded.popia_confirmed_user_agent, "user_Registration".popia_confirmed_user_agent),
                mba_access = 1;
        END;

        CREATE TRIGGER mba_users_update
        INSTEAD OF UPDATE ON mba_users
        BEGIN
            UPDATE "user_Registration"
            SET
                email = lower(COALESCE(NEW.email, email)),
                password = COALESCE(NEW.password_hash, password),
                first_name = COALESCE(NEW.first_name, first_name),
                last_name = COALESCE(NEW.last_name, last_name),
                is_active = COALESCE(NEW.is_active, is_active),
                updated_at = COALESCE(NEW.updated_at, CURRENT_TIMESTAMP),
                mba_role = COALESCE(NEW.role, mba_role),
                role = COALESCE(NEW.role, role),
                scholar_role = COALESCE(NEW.scholar_role, scholar_role),
                microsoft_subject = COALESCE(NEW.microsoft_subject, microsoft_subject),
                has_profile = COALESCE(NEW.has_profile, has_profile),
                has_signature = COALESCE(NEW.has_signature, has_signature),
                has_cv = COALESCE(NEW.has_cv, has_cv),
                popia_confirmed_at = COALESCE(NEW.popia_confirmed_at, popia_confirmed_at),
                popia_notice_version = COALESCE(NEW.popia_notice_version, popia_notice_version),
                popia_confirmed_ip = COALESCE(NEW.popia_confirmed_ip, popia_confirmed_ip),
                popia_confirmed_user_agent = COALESCE(NEW.popia_confirmed_user_agent, popia_confirmed_user_agent),
                mba_access = 1
            WHERE user_id = OLD.id;
        END;

        CREATE TRIGGER mba_users_delete
        INSTEAD OF DELETE ON mba_users
        BEGIN
            UPDATE "user_Registration"
            SET mba_access = 0, mba_role = NULL, scholar_role = NULL
            WHERE user_id = OLD.id;
        END;

        CREATE TRIGGER ethcis_users_insert
        INSTEAD OF INSERT ON ethcis_users
        BEGIN
            INSERT INTO "user_Registration" (
                user_id, email, password, first_name, last_name, is_active, created_at, updated_at,
                ethics_role, role, student_number, staff_number, specialisation, authenticated_student,
                watched_demo, microsoft_subject, supervisor_user_id, popia_confirmed_at, popia_notice_version,
                popia_confirmed_ip, popia_confirmed_user_agent, ethics_access, authenticated
            ) VALUES (
                NEW.id, lower(NEW.email), NEW.password_hash, NEW.first_name, NEW.last_name, COALESCE(NEW.is_active, 1),
                COALESCE(NEW.created_at, CURRENT_TIMESTAMP), COALESCE(NEW.updated_at, CURRENT_TIMESTAMP),
                NEW.role, COALESCE(NEW.role, 'student'), NEW.student_number, NEW.staff_number, NEW.specialisation,
                COALESCE(NEW.authenticated_student, 0), COALESCE(NEW.watched_demo, 0), NEW.microsoft_subject,
                NEW.supervisor_id, NEW.popia_confirmed_at, NEW.popia_notice_version, NEW.popia_confirmed_ip,
                NEW.popia_confirmed_user_agent, 1, COALESCE(NEW.authenticated_student, 0)
            )
            ON CONFLICT(email) DO UPDATE SET
                password = COALESCE(excluded.password, "user_Registration".password),
                first_name = COALESCE(excluded.first_name, "user_Registration".first_name),
                last_name = COALESCE(excluded.last_name, "user_Registration".last_name),
                is_active = COALESCE(excluded.is_active, "user_Registration".is_active),
                updated_at = COALESCE(excluded.updated_at, CURRENT_TIMESTAMP),
                ethics_role = COALESCE(excluded.ethics_role, "user_Registration".ethics_role),
                role = COALESCE(excluded.role, "user_Registration".role),
                student_number = COALESCE(excluded.student_number, "user_Registration".student_number),
                staff_number = COALESCE(excluded.staff_number, "user_Registration".staff_number),
                specialisation = COALESCE(excluded.specialisation, "user_Registration".specialisation),
                authenticated_student = COALESCE(excluded.authenticated_student, "user_Registration".authenticated_student),
                watched_demo = COALESCE(excluded.watched_demo, "user_Registration".watched_demo),
                microsoft_subject = COALESCE(excluded.microsoft_subject, "user_Registration".microsoft_subject),
                supervisor_user_id = COALESCE(excluded.supervisor_user_id, "user_Registration".supervisor_user_id),
                popia_confirmed_at = COALESCE(excluded.popia_confirmed_at, "user_Registration".popia_confirmed_at),
                popia_notice_version = COALESCE(excluded.popia_notice_version, "user_Registration".popia_notice_version),
                popia_confirmed_ip = COALESCE(excluded.popia_confirmed_ip, "user_Registration".popia_confirmed_ip),
                popia_confirmed_user_agent = COALESCE(excluded.popia_confirmed_user_agent, "user_Registration".popia_confirmed_user_agent),
                ethics_access = 1,
                authenticated = MAX("user_Registration".authenticated, COALESCE(excluded.authenticated, 0));
        END;

        CREATE TRIGGER ethcis_users_update
        INSTEAD OF UPDATE ON ethcis_users
        BEGIN
            UPDATE "user_Registration"
            SET
                email = lower(COALESCE(NEW.email, email)),
                password = COALESCE(NEW.password_hash, password),
                first_name = COALESCE(NEW.first_name, first_name),
                last_name = COALESCE(NEW.last_name, last_name),
                is_active = COALESCE(NEW.is_active, is_active),
                updated_at = COALESCE(NEW.updated_at, CURRENT_TIMESTAMP),
                ethics_role = COALESCE(NEW.role, ethics_role),
                role = COALESCE(NEW.role, role),
                student_number = COALESCE(NEW.student_number, student_number),
                staff_number = COALESCE(NEW.staff_number, staff_number),
                specialisation = COALESCE(NEW.specialisation, specialisation),
                authenticated_student = COALESCE(NEW.authenticated_student, authenticated_student),
                watched_demo = COALESCE(NEW.watched_demo, watched_demo),
                microsoft_subject = COALESCE(NEW.microsoft_subject, microsoft_subject),
                supervisor_user_id = COALESCE(NEW.supervisor_id, supervisor_user_id),
                popia_confirmed_at = COALESCE(NEW.popia_confirmed_at, popia_confirmed_at),
                popia_notice_version = COALESCE(NEW.popia_notice_version, popia_notice_version),
                popia_confirmed_ip = COALESCE(NEW.popia_confirmed_ip, popia_confirmed_ip),
                popia_confirmed_user_agent = COALESCE(NEW.popia_confirmed_user_agent, popia_confirmed_user_agent),
                ethics_access = 1,
                authenticated = MAX(authenticated, COALESCE(NEW.authenticated_student, 0))
            WHERE user_id = OLD.id;
        END;

        CREATE TRIGGER ethcis_users_delete
        INSTEAD OF DELETE ON ethcis_users
        BEGIN
            UPDATE "user_Registration"
            SET ethics_access = 0, ethics_role = NULL, authenticated_student = 0
            WHERE user_id = OLD.id;
        END;

        CREATE TRIGGER mba_student_profiles_insert
        INSTEAD OF INSERT ON mba_student_profiles
        BEGIN
            INSERT INTO user_profile (
                user_id, name, surname, title, contact, student_number, secondary_email, module, block_id,
                degree, address, postal_code, id_passport_number, default_signing_location, form_defaults, created_at, updated_at
            ) VALUES (
                NEW.user_id, NEW.name, NEW.surname, NEW.title, NEW.contact, NEW.student_number, NEW.secondary_email, NEW.module, NEW.block_id,
                NEW.degree, NEW.address, NEW.postal_code, NEW.id_passport_number, NEW.default_signing_location, NEW.form_defaults,
                COALESCE(NEW.created_at, CURRENT_TIMESTAMP), COALESCE(NEW.created_at, CURRENT_TIMESTAMP)
            )
            ON CONFLICT(user_id) DO UPDATE SET
                name = COALESCE(excluded.name, user_profile.name),
                surname = COALESCE(excluded.surname, user_profile.surname),
                title = COALESCE(excluded.title, user_profile.title),
                contact = COALESCE(excluded.contact, user_profile.contact),
                student_number = COALESCE(excluded.student_number, user_profile.student_number),
                secondary_email = COALESCE(excluded.secondary_email, user_profile.secondary_email),
                module = COALESCE(excluded.module, user_profile.module),
                block_id = COALESCE(excluded.block_id, user_profile.block_id),
                degree = COALESCE(excluded.degree, user_profile.degree),
                address = COALESCE(excluded.address, user_profile.address),
                postal_code = COALESCE(excluded.postal_code, user_profile.postal_code),
                id_passport_number = COALESCE(excluded.id_passport_number, user_profile.id_passport_number),
                default_signing_location = COALESCE(excluded.default_signing_location, user_profile.default_signing_location),
                form_defaults = COALESCE(excluded.form_defaults, user_profile.form_defaults),
                updated_at = CURRENT_TIMESTAMP;

            UPDATE "user_Registration"
            SET has_profile = 1,
                student_number = COALESCE(NEW.student_number, student_number),
                staff_student_number = COALESCE(NEW.student_number, staff_student_number)
            WHERE user_id = NEW.user_id;
        END;

        CREATE TRIGGER mba_student_profiles_update
        INSTEAD OF UPDATE ON mba_student_profiles
        BEGIN
            UPDATE user_profile
            SET
                name = COALESCE(NEW.name, name),
                surname = COALESCE(NEW.surname, surname),
                title = COALESCE(NEW.title, title),
                contact = COALESCE(NEW.contact, contact),
                student_number = COALESCE(NEW.student_number, student_number),
                secondary_email = COALESCE(NEW.secondary_email, secondary_email),
                module = COALESCE(NEW.module, module),
                block_id = COALESCE(NEW.block_id, block_id),
                degree = COALESCE(NEW.degree, degree),
                address = COALESCE(NEW.address, address),
                postal_code = COALESCE(NEW.postal_code, postal_code),
                id_passport_number = COALESCE(NEW.id_passport_number, id_passport_number),
                default_signing_location = COALESCE(NEW.default_signing_location, default_signing_location),
                form_defaults = COALESCE(NEW.form_defaults, form_defaults),
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = OLD.user_id;

            UPDATE "user_Registration"
            SET has_profile = 1,
                student_number = COALESCE(NEW.student_number, student_number),
                staff_student_number = COALESCE(NEW.student_number, staff_student_number)
            WHERE user_id = OLD.user_id;
        END;

        CREATE TRIGGER mba_student_profiles_delete
        INSTEAD OF DELETE ON mba_student_profiles
        BEGIN
            DELETE FROM user_profile WHERE user_id = OLD.user_id;
        END;

        CREATE TRIGGER mba_scholar_profiles_insert
        INSTEAD OF INSERT ON mba_scholar_profiles
        BEGIN
            INSERT INTO user_profile (
                user_id, name, surname, title, skills, address, department, position, contact, staff_number,
                id_passport_number, postal_code, default_signing_location, students, qualification, affiliation,
                research_themes, research_interests, research_disciplines, academic_experience, students_supervised_total,
                students_assessed_total, publication_count, selected_publications, scholarly_profile_links,
                approved_before, international_assessor, form_defaults, created_at, updated_at
            ) VALUES (
                NEW.user_id, NEW.name, NEW.surname, NEW.title, NEW.skills, NEW.address, NEW.department, NEW.position, NEW.contact, NEW.staff_number,
                NEW.id_passport_number, NEW.postal_code, NEW.default_signing_location, NEW.students, NEW.qualification, NEW.affiliation,
                NEW.research_themes, NEW.research_interests, NEW.research_disciplines, NEW.academic_experience, NEW.students_supervised_total,
                NEW.students_assessed_total, NEW.publication_count, NEW.selected_publications, NEW.scholarly_profile_links,
                NEW.approved_before, NEW.international_assessor, NEW.form_defaults, COALESCE(NEW.created_at, CURRENT_TIMESTAMP), COALESCE(NEW.created_at, CURRENT_TIMESTAMP)
            )
            ON CONFLICT(user_id) DO UPDATE SET
                name = COALESCE(excluded.name, user_profile.name),
                surname = COALESCE(excluded.surname, user_profile.surname),
                title = COALESCE(excluded.title, user_profile.title),
                skills = COALESCE(excluded.skills, user_profile.skills),
                address = COALESCE(excluded.address, user_profile.address),
                department = COALESCE(excluded.department, user_profile.department),
                position = COALESCE(excluded.position, user_profile.position),
                contact = COALESCE(excluded.contact, user_profile.contact),
                staff_number = COALESCE(excluded.staff_number, user_profile.staff_number),
                id_passport_number = COALESCE(excluded.id_passport_number, user_profile.id_passport_number),
                postal_code = COALESCE(excluded.postal_code, user_profile.postal_code),
                default_signing_location = COALESCE(excluded.default_signing_location, user_profile.default_signing_location),
                students = COALESCE(excluded.students, user_profile.students),
                qualification = COALESCE(excluded.qualification, user_profile.qualification),
                affiliation = COALESCE(excluded.affiliation, user_profile.affiliation),
                research_themes = COALESCE(excluded.research_themes, user_profile.research_themes),
                research_interests = COALESCE(excluded.research_interests, user_profile.research_interests),
                research_disciplines = COALESCE(excluded.research_disciplines, user_profile.research_disciplines),
                academic_experience = COALESCE(excluded.academic_experience, user_profile.academic_experience),
                students_supervised_total = COALESCE(excluded.students_supervised_total, user_profile.students_supervised_total),
                students_assessed_total = COALESCE(excluded.students_assessed_total, user_profile.students_assessed_total),
                publication_count = COALESCE(excluded.publication_count, user_profile.publication_count),
                selected_publications = COALESCE(excluded.selected_publications, user_profile.selected_publications),
                scholarly_profile_links = COALESCE(excluded.scholarly_profile_links, user_profile.scholarly_profile_links),
                approved_before = COALESCE(excluded.approved_before, user_profile.approved_before),
                international_assessor = COALESCE(excluded.international_assessor, user_profile.international_assessor),
                form_defaults = COALESCE(excluded.form_defaults, user_profile.form_defaults),
                updated_at = CURRENT_TIMESTAMP;

            UPDATE "user_Registration"
            SET has_profile = 1,
                staff_number = COALESCE(NEW.staff_number, staff_number),
                staff_student_number = COALESCE(NEW.staff_number, staff_student_number)
            WHERE user_id = NEW.user_id;
        END;

        CREATE TRIGGER mba_scholar_profiles_update
        INSTEAD OF UPDATE ON mba_scholar_profiles
        BEGIN
            UPDATE user_profile
            SET
                name = COALESCE(NEW.name, name),
                surname = COALESCE(NEW.surname, surname),
                title = COALESCE(NEW.title, title),
                skills = COALESCE(NEW.skills, skills),
                address = COALESCE(NEW.address, address),
                department = COALESCE(NEW.department, department),
                position = COALESCE(NEW.position, position),
                contact = COALESCE(NEW.contact, contact),
                staff_number = COALESCE(NEW.staff_number, staff_number),
                id_passport_number = COALESCE(NEW.id_passport_number, id_passport_number),
                postal_code = COALESCE(NEW.postal_code, postal_code),
                default_signing_location = COALESCE(NEW.default_signing_location, default_signing_location),
                students = COALESCE(NEW.students, students),
                qualification = COALESCE(NEW.qualification, qualification),
                affiliation = COALESCE(NEW.affiliation, affiliation),
                research_themes = COALESCE(NEW.research_themes, research_themes),
                research_interests = COALESCE(NEW.research_interests, research_interests),
                research_disciplines = COALESCE(NEW.research_disciplines, research_disciplines),
                academic_experience = COALESCE(NEW.academic_experience, academic_experience),
                students_supervised_total = COALESCE(NEW.students_supervised_total, students_supervised_total),
                students_assessed_total = COALESCE(NEW.students_assessed_total, students_assessed_total),
                publication_count = COALESCE(NEW.publication_count, publication_count),
                selected_publications = COALESCE(NEW.selected_publications, selected_publications),
                scholarly_profile_links = COALESCE(NEW.scholarly_profile_links, scholarly_profile_links),
                approved_before = COALESCE(NEW.approved_before, approved_before),
                international_assessor = COALESCE(NEW.international_assessor, international_assessor),
                form_defaults = COALESCE(NEW.form_defaults, form_defaults),
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = OLD.user_id;

            UPDATE "user_Registration"
            SET has_profile = 1,
                staff_number = COALESCE(NEW.staff_number, staff_number),
                staff_student_number = COALESCE(NEW.staff_number, staff_student_number)
            WHERE user_id = OLD.user_id;
        END;

        CREATE TRIGGER mba_scholar_profiles_delete
        INSTEAD OF DELETE ON mba_scholar_profiles
        BEGIN
            DELETE FROM user_profile WHERE user_id = OLD.user_id;
        END;

        CREATE TRIGGER users_insert
        INSTEAD OF INSERT ON users
        BEGIN
            INSERT INTO "user_Registration" (
                legacy_user_id, email, password, first_name, last_name, legacy_full_name,
                student_number, staff_number, specialisation, ethics_role, role, supervisor_legacy_user_id,
                reset_token, reset_token_expiry, authenticated_student, authenticated, ethics_access, is_active,
                staff_student_number, created_at, updated_at
            ) VALUES (
                NEW.user_id, lower(NEW.email), NEW.password,
                substr(trim(NEW.full_name), 1, CASE WHEN instr(trim(NEW.full_name), ' ') = 0 THEN length(trim(NEW.full_name)) ELSE instr(trim(NEW.full_name), ' ') - 1 END),
                CASE WHEN instr(trim(NEW.full_name), ' ') = 0 THEN NULL ELSE substr(trim(NEW.full_name), instr(trim(NEW.full_name), ' ') + 1) END,
                NEW.full_name, CAST(NEW.student_number AS TEXT), NEW.staff_number, NEW.specialisation,
                lower(NEW.role), lower(NEW.role), NEW.supervisor_id, NEW.reset_token, NEW.reset_token_expiry,
                CASE WHEN lower(COALESCE(NEW.authenticate_student, 'false')) IN ('true', '1') THEN 1 ELSE 0 END,
                CASE WHEN lower(COALESCE(NEW.authenticate_student, 'false')) IN ('true', '1') THEN 1 ELSE 0 END,
                1, CASE WHEN lower(COALESCE(NEW.authenticate_student, 'false')) IN ('true', '1') THEN 1 ELSE 0 END,
                COALESCE(CAST(NEW.student_number AS TEXT), NEW.staff_number), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT(email) DO UPDATE SET
                legacy_user_id = COALESCE(excluded.legacy_user_id, "user_Registration".legacy_user_id),
                password = COALESCE(excluded.password, "user_Registration".password),
                first_name = COALESCE(excluded.first_name, "user_Registration".first_name),
                last_name = COALESCE(excluded.last_name, "user_Registration".last_name),
                legacy_full_name = COALESCE(excluded.legacy_full_name, "user_Registration".legacy_full_name),
                student_number = COALESCE(excluded.student_number, "user_Registration".student_number),
                staff_number = COALESCE(excluded.staff_number, "user_Registration".staff_number),
                specialisation = COALESCE(excluded.specialisation, "user_Registration".specialisation),
                ethics_role = COALESCE(excluded.ethics_role, "user_Registration".ethics_role),
                role = COALESCE(excluded.role, "user_Registration".role),
                supervisor_legacy_user_id = COALESCE(excluded.supervisor_legacy_user_id, "user_Registration".supervisor_legacy_user_id),
                reset_token = COALESCE(excluded.reset_token, "user_Registration".reset_token),
                reset_token_expiry = COALESCE(excluded.reset_token_expiry, "user_Registration".reset_token_expiry),
                authenticated_student = COALESCE(excluded.authenticated_student, "user_Registration".authenticated_student),
                authenticated = MAX("user_Registration".authenticated, COALESCE(excluded.authenticated, 0)),
                ethics_access = 1,
                is_active = COALESCE(excluded.is_active, "user_Registration".is_active),
                staff_student_number = COALESCE(excluded.staff_student_number, "user_Registration".staff_student_number),
                updated_at = CURRENT_TIMESTAMP;
        END;

        CREATE TRIGGER users_update
        INSTEAD OF UPDATE ON users
        BEGIN
            UPDATE "user_Registration"
            SET
                legacy_user_id = COALESCE(NEW.user_id, legacy_user_id),
                email = lower(COALESCE(NEW.email, email)),
                password = COALESCE(NEW.password, password),
                legacy_full_name = COALESCE(NEW.full_name, legacy_full_name),
                first_name = COALESCE(
                    substr(trim(NEW.full_name), 1, CASE WHEN instr(trim(NEW.full_name), ' ') = 0 THEN length(trim(NEW.full_name)) ELSE instr(trim(NEW.full_name), ' ') - 1 END),
                    first_name
                ),
                last_name = COALESCE(
                    CASE WHEN instr(trim(NEW.full_name), ' ') = 0 THEN NULL ELSE substr(trim(NEW.full_name), instr(trim(NEW.full_name), ' ') + 1) END,
                    last_name
                ),
                student_number = COALESCE(CAST(NEW.student_number AS TEXT), student_number),
                staff_number = COALESCE(NEW.staff_number, staff_number),
                specialisation = COALESCE(NEW.specialisation, specialisation),
                ethics_role = COALESCE(lower(NEW.role), ethics_role),
                role = COALESCE(lower(NEW.role), role),
                supervisor_legacy_user_id = COALESCE(NEW.supervisor_id, supervisor_legacy_user_id),
                reset_token = COALESCE(NEW.reset_token, reset_token),
                reset_token_expiry = COALESCE(NEW.reset_token_expiry, reset_token_expiry),
                authenticated_student = CASE WHEN lower(COALESCE(NEW.authenticate_student, 'false')) IN ('true', '1') THEN 1 ELSE 0 END,
                authenticated = CASE WHEN lower(COALESCE(NEW.authenticate_student, 'false')) IN ('true', '1') THEN 1 ELSE authenticated END,
                ethics_access = 1,
                staff_student_number = COALESCE(CAST(NEW.student_number AS TEXT), NEW.staff_number, staff_student_number),
                updated_at = CURRENT_TIMESTAMP
            WHERE legacy_user_id = OLD.user_id OR email = lower(OLD.email);
        END;

        CREATE TRIGGER users_delete
        INSTEAD OF DELETE ON users
        BEGIN
            UPDATE "user_Registration"
            SET ethics_access = 0, legacy_user_id = NULL
            WHERE legacy_user_id = OLD.user_id OR email = lower(OLD.email);
        END;
        """
    )


def verify_state(conn: sqlite3.Connection) -> dict[str, int]:
    metrics = {
        "user_registration_rows": conn.execute('SELECT COUNT(*) FROM "user_Registration"').fetchone()[0],
        "user_profile_rows": conn.execute('SELECT COUNT(*) FROM user_profile').fetchone()[0],
        "legacy_users_view_rows": conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        "mba_users_view_rows": conn.execute('SELECT COUNT(*) FROM mba_users').fetchone()[0],
        "ethics_users_view_rows": conn.execute('SELECT COUNT(*) FROM ethcis_users').fetchone()[0],
        "form_a_rows": conn.execute('SELECT COUNT(*) FROM form_a').fetchone()[0],
        "form_b_rows": conn.execute('SELECT COUNT(*) FROM form_b').fetchone()[0],
        "form_c_rows": conn.execute('SELECT COUNT(*) FROM form_c').fetchone()[0],
        "activity_log_rows": conn.execute('SELECT COUNT(*) FROM user_activity_logs').fetchone()[0],
    }
    return metrics


def main() -> None:
    if not APP_DB.exists():
        raise FileNotFoundError(f"Missing app database: {APP_DB}")
    if not ETHICS_DB.exists():
        raise FileNotFoundError(f"Missing ethics database: {ETHICS_DB}")

    app_backup = backup_file(APP_DB)
    ethics_backup = backup_file(ETHICS_DB)
    print(f"Backed up app.db to {app_backup.name}")
    print(f"Backed up ethics.db to {ethics_backup.name}")

    app_conn = sqlite3.connect(APP_DB)
    app_conn.row_factory = sqlite3.Row
    ethics_conn = sqlite3.connect(ETHICS_DB)
    ethics_conn.row_factory = sqlite3.Row
    try:
        create_unified_tables(app_conn)
        skipped_tables = copy_ethics_tables_into_app_db(app_conn, ethics_conn)
        users, profiles = build_unified_records(app_conn, ethics_conn)
        replace_unified_data(app_conn, users, profiles)
        install_compatibility_views(app_conn)
        app_conn.commit()
        metrics = verify_state(app_conn)
    finally:
        ethics_conn.close()
        app_conn.close()

    print("Unified database migration completed.")
    for key, value in metrics.items():
        print(f"{key}: {value}")
    if skipped_tables:
        print("Skipped ethics tables:")
        for entry in skipped_tables:
            print(f" - {entry}")


if __name__ == "__main__":
    main()
