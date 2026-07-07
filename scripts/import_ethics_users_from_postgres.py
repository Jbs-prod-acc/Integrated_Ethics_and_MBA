from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()


ROLE_PRIORITY = {
    "STUDENT": 10,
    "SUPERVISOR": 60,
    "REVIEWER": 55,
    "REC": 75,
    "DEAN": 70,
    "ADMIN": 90,
    "SUPER_ADMIN": 95,
}


@dataclass
class SourceUser:
    user_id: str
    full_name: str
    student_number: int | None
    email: str
    password: str
    supervisor_id: str | None
    staff_number: str | None
    specialisation: str | None
    role: str
    reset_token: str | None
    reset_token_expiry: Any
    authenticate_student: str | None


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


def choose_role(existing: str | None, incoming: str | None) -> str:
    if not incoming:
        return existing or "STUDENT"
    if not existing:
        return incoming
    return incoming if ROLE_PRIORITY.get(incoming, 0) >= ROLE_PRIORITY.get(existing, 0) else existing


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

    server = os.getenv("SOURCE_DB_SERVER")
    port = os.getenv("SOURCE_DB_PORT")
    name = os.getenv("SOURCE_DB_NAME")
    user = quote_plus(os.getenv("SOURCE_DB_USER"))
    password = quote_plus(os.getenv("SOURCE_DB_PASSWORD"))
    return f"postgresql+psycopg://{user}:{password}@{server}:{port}/{name}"


def fetch_source_users(source_engine) -> list[SourceUser]:
    query = text(
        """
        SELECT
            user_id,
            full_name,
            student_number,
            email,
            password,
            supervisor_id,
            staff_number,
            specialisation,
            role::text AS role,
            reset_token,
            reset_token_expiry,
            authenticate_student
        FROM users
        ORDER BY lower(email)
        """
    )
    with source_engine.connect() as conn:
        return [SourceUser(**dict(row)) for row in conn.execute(query).mappings()]


def upsert_users(target_engine, source_users: list[SourceUser]) -> None:
    email_to_target = {}
    with target_engine.begin() as conn:
        existing_rows = conn.execute(
            text(
                """
                SELECT
                    integrated_id,
                    user_id,
                    lower(email) AS email,
                    role::text AS role,
                    mba_access,
                    ethics_access
                FROM users
                """
            )
        ).mappings()
        for row in existing_rows:
            email_to_target[row["email"]] = dict(row)

        for user in source_users:
            email = normalize_email(user.email)
            if not email:
                continue

            first_name, last_name = split_name(user.full_name)
            authenticate_student = str(user.authenticate_student or "").strip().lower() in {"1", "true", "yes"}
            existing = email_to_target.get(email)

            if existing:
                conn.execute(
                    text(
                        """
                        UPDATE users
                        SET
                            full_name = COALESCE(:full_name, full_name),
                            student_number = COALESCE(:student_number, student_number),
                            password = COALESCE(:password, password),
                            staff_number = COALESCE(:staff_number, staff_number),
                            specialisation = COALESCE(:specialisation, specialisation),
                            role = CAST(:role AS userrole),
                            reset_token = COALESCE(:reset_token, reset_token),
                            reset_token_expiry = COALESCE(:reset_token_expiry, reset_token_expiry),
                            authenticate_student = CASE WHEN :authenticate_student THEN 'true' ELSE authenticate_student END,
                            ethics_role = lower(:ethics_role),
                            authenticated_student = authenticated_student OR :authenticate_student,
                            ethics_access = TRUE,
                            is_active = TRUE,
                            first_name = COALESCE(:first_name, first_name),
                            last_name = COALESCE(:last_name, last_name),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE integrated_id = :integrated_id
                        """
                    ),
                    {
                        "integrated_id": existing["integrated_id"],
                        "full_name": user.full_name,
                        "student_number": user.student_number,
                        "password": user.password,
                        "staff_number": user.staff_number,
                        "specialisation": user.specialisation,
                        "role": choose_role(existing["role"], user.role),
                        "reset_token": user.reset_token,
                        "reset_token_expiry": user.reset_token_expiry,
                        "authenticate_student": authenticate_student,
                        "ethics_role": user.role.lower(),
                        "first_name": first_name,
                        "last_name": last_name,
                    },
                )
            else:
                row = conn.execute(
                    text(
                        """
                        INSERT INTO users (
                            user_id,
                            full_name,
                            student_number,
                            email,
                            password,
                            supervisor_id,
                            staff_number,
                            specialisation,
                            role,
                            reset_token,
                            reset_token_expiry,
                            authenticate_student,
                            ethics_role,
                            authenticated_student,
                            ethics_access,
                            mba_access,
                            is_active,
                            created_at,
                            updated_at,
                            first_name,
                            last_name
                        ) VALUES (
                            :user_id,
                            :full_name,
                            :student_number,
                            :email,
                            :password,
                            NULL,
                            :staff_number,
                            :specialisation,
                            CAST(:role AS userrole),
                            :reset_token,
                            :reset_token_expiry,
                            :authenticate_student_text,
                            :ethics_role,
                            :authenticate_student,
                            TRUE,
                            FALSE,
                            TRUE,
                            :created_at,
                            :updated_at,
                            :first_name,
                            :last_name
                        )
                        RETURNING integrated_id, user_id
                        """
                    ),
                    {
                        "user_id": user.user_id,
                        "full_name": user.full_name,
                        "student_number": user.student_number,
                        "email": email,
                        "password": user.password,
                        "staff_number": user.staff_number,
                        "specialisation": user.specialisation,
                        "role": user.role,
                        "reset_token": user.reset_token,
                        "reset_token_expiry": user.reset_token_expiry,
                        "authenticate_student_text": "true" if authenticate_student else "false",
                        "ethics_role": user.role.lower(),
                        "authenticate_student": authenticate_student,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                        "first_name": first_name,
                        "last_name": last_name,
                    },
                ).mappings().one()
                existing = {
                    "integrated_id": row["integrated_id"],
                    "user_id": row["user_id"],
                    "email": email,
                    "role": user.role,
                    "mba_access": False,
                    "ethics_access": True,
                }

            email_to_target[email] = existing

        source_id_to_target = {
            user.user_id: email_to_target[normalize_email(user.email)]
            for user in source_users
            if normalize_email(user.email) in email_to_target
        }

        for user in source_users:
            if not user.supervisor_id:
                continue
            email = normalize_email(user.email)
            target_user = email_to_target.get(email)
            target_supervisor = source_id_to_target.get(user.supervisor_id)
            if not target_user or not target_supervisor:
                continue
            conn.execute(
                text(
                    """
                    UPDATE users
                    SET
                        supervisor_id = :supervisor_user_id,
                        supervisor_integrated_id = :supervisor_integrated_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE integrated_id = :integrated_id
                    """
                ),
                {
                    "integrated_id": target_user["integrated_id"],
                    "supervisor_user_id": target_supervisor["user_id"],
                    "supervisor_integrated_id": target_supervisor["integrated_id"],
                },
            )


def main() -> None:
    target_url = os.getenv("DATABASE_URL")
    if not target_url:
        raise RuntimeError("DATABASE_URL is required for the target database.")

    source_engine = create_engine(build_source_url())
    target_engine = create_engine(target_url)

    source_users = fetch_source_users(source_engine)
    upsert_users(target_engine, source_users)

    with target_engine.connect() as conn:
        shared_count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        ethics_count = conn.execute(text("SELECT COUNT(*) FROM ethcis_users")).scalar_one()
        print(f"Imported {len(source_users)} source ethics users.")
        print(f"Target shared users count: {shared_count}")
        print(f"Target ethics view count: {ethics_count}")


if __name__ == "__main__":
    main()
