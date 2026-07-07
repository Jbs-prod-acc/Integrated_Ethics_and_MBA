import importlib.util
import secrets
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .extensions import db, oauth
from .models import (
    EthicsActivityLog,
    EthicsRole,
    EthicsUser,
    MbaScholarProfile,
    MbaStudentProfile,
    MbaRole,
    MbaScholarRole,
    MbaUser,
    UJ_STUDENT_EMAIL_RE,
    is_uj_student_email,
    normalize_email,
    student_email_for,
)
from .mail import send_email
from .supervisor_sync import sync_ethics_supervisor_from_mba

auth_bp = Blueprint("auth", __name__)
POPIA_NOTICE_VERSION = "2026-05-12"
ETHICS_SSO_SALT = "mba-to-ethics-sso"
PASSWORD_RESET_SALT = "shared-password-reset"
PASSWORD_RESET_MAX_AGE_SECONDS = 3600
_RATE_LIMIT_EVENTS = defaultdict(deque)


def find_registered_user(email, system=None):
    clean_email = normalize_email(email)
    if system == "mba":
        return MbaUser.find_by_email(clean_email)
    if system == "ethics":
        return EthicsUser.find_by_email(clean_email)
    return MbaUser.find_by_email(clean_email) or EthicsUser.find_by_email(clean_email)


def _split_name_parts(*, first_name=None, last_name=None, full_name=None, email=None):
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if (not first or not last) and full_name:
        parts = [part for part in str(full_name).strip().split() if part]
        if parts:
            if not first:
                first = parts[0]
            if not last and len(parts) > 1:
                last = " ".join(parts[1:])
    if not first:
        local = (email or "").split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
        first = local.split()[0].title() if local else "User"
    return first, last


def _full_name(first_name, last_name, email=None):
    full = " ".join(part for part in [first_name, last_name] if part).strip()
    if full:
        return full
    return (email or "User").split("@", 1)[0]


def _mba_student_number_from_email(email):
    clean_email = normalize_email(email)
    if is_uj_student_email(clean_email):
        return clean_email.split("@", 1)[0]
    return None


def _ethics_role_for_mba_user(user):
    if not user:
        return None
    if user.role == MbaRole.STUDENT.value:
        return EthicsRole.STUDENT.value
    if user.is_supervisor_role():
        return EthicsRole.SUPERVISOR.value
    if user.role == MbaRole.ADMIN.value:
        return EthicsRole.ADMIN.value
    if user.role == MbaRole.MAIN_ADMIN.value:
        return EthicsRole.SUPER_ADMIN.value
    return None


def _mba_access_descriptor_for_ethics_role(role):
    if role == EthicsRole.STUDENT.value:
        return {"role": MbaRole.STUDENT.value}
    if role == EthicsRole.SUPERVISOR.value:
        return {"role": MbaRole.SCHOLAR.value, "scholar_role": MbaScholarRole.SUPERVISOR.value}
    if role == EthicsRole.ADMIN.value:
        return {"role": MbaRole.ADMIN.value}
    if role == EthicsRole.SUPER_ADMIN.value:
        return {"role": MbaRole.MAIN_ADMIN.value}
    return None


def _can_reuse_ethics_role(existing_role, target_role):
    if target_role == EthicsRole.SUPER_ADMIN.value:
        return existing_role in {EthicsRole.ADMIN.value, EthicsRole.SUPER_ADMIN.value}
    if target_role == EthicsRole.ADMIN.value:
        return existing_role in {EthicsRole.ADMIN.value, EthicsRole.SUPER_ADMIN.value}
    return existing_role == target_role


def _can_reuse_mba_role(user, descriptor):
    if not user or not descriptor:
        return False
    target_role = descriptor["role"]
    if target_role == MbaRole.MAIN_ADMIN.value:
        return user.role in {MbaRole.ADMIN.value, MbaRole.MAIN_ADMIN.value}
    if target_role == MbaRole.ADMIN.value:
        return user.role in {MbaRole.ADMIN.value, MbaRole.MAIN_ADMIN.value}
    if target_role == MbaRole.STUDENT.value:
        return user.role == MbaRole.STUDENT.value
    if target_role == MbaRole.SCHOLAR.value:
        return user.role == MbaRole.SCHOLAR.value
    return user.role == target_role


def _legacy_role_for_unified_user(*, ethics_role=None, mba_role=None, scholar_role=None, current_role=None):
    if ethics_role == EthicsRole.SUPER_ADMIN.value:
        return "SUPER_ADMIN"
    if ethics_role == EthicsRole.ADMIN.value:
        return "ADMIN"
    if ethics_role == EthicsRole.REC.value:
        return "REC"
    if ethics_role == EthicsRole.DEAN.value:
        return "DEAN"
    if ethics_role == EthicsRole.REVIEWER.value:
        return "REVIEWER"
    if ethics_role == EthicsRole.SUPERVISOR.value:
        return "SUPERVISOR"
    if ethics_role == EthicsRole.STUDENT.value:
        return "STUDENT"
    if scholar_role in {MbaScholarRole.SUPERVISOR.value, MbaScholarRole.BOTH.value}:
        return "SUPERVISOR"
    if scholar_role == MbaScholarRole.EXAMINER.value or mba_role == MbaRole.EXAMINER.value:
        return "REVIEWER"
    if mba_role == MbaRole.MAIN_ADMIN.value:
        return "SUPER_ADMIN"
    if mba_role == MbaRole.ADMIN.value:
        return "ADMIN"
    if mba_role == MbaRole.HDC.value:
        return "REC"
    if mba_role == MbaRole.STUDENT.value:
        return "STUDENT"
    return (current_role or "STUDENT").upper()


def _find_shared_user_row(email):
    clean_email = normalize_email(email)
    if not clean_email:
        return None
    return db.session.execute(
        text(
            """
            SELECT
                integrated_id,
                email,
                role::text AS role,
                mba_role,
                scholar_role,
                ethics_role,
                first_name,
                last_name,
                student_number,
                staff_number,
                mba_access,
                ethics_access
            FROM users
            WHERE lower(email) = :email
            LIMIT 1
            """
        ),
        {"email": clean_email},
    ).mappings().first()


def _enable_ethics_access_for_shared_user(shared_user, *, target_role, first_name=None, last_name=None, student_number=None, staff_number=None):
    resolved_first_name, resolved_last_name = _split_name_parts(
        first_name=first_name or shared_user.get("first_name"),
        last_name=last_name or shared_user.get("last_name"),
        email=shared_user.get("email"),
    )
    resolved_student_number = student_number if str(student_number or "").isdigit() else None
    resolved_staff_number = staff_number or shared_user.get("staff_number")
    legacy_role = _legacy_role_for_unified_user(
        ethics_role=target_role,
        mba_role=shared_user.get("mba_role"),
        scholar_role=shared_user.get("scholar_role"),
        current_role=shared_user.get("role"),
    )
    authenticated_student = target_role == EthicsRole.STUDENT.value

    db.session.execute(
        text(
            """
            UPDATE users
            SET
                ethics_access = TRUE,
                ethics_role = :ethics_role,
                first_name = COALESCE(NULLIF(:first_name, ''), first_name),
                last_name = COALESCE(NULLIF(:last_name, ''), last_name),
                full_name = trim(
                    concat_ws(
                        ' ',
                        COALESCE(NULLIF(:first_name, ''), first_name),
                        COALESCE(NULLIF(:last_name, ''), last_name)
                    )
                ),
                student_number = COALESCE(:student_number, student_number),
                staff_number = COALESCE(:staff_number, staff_number),
                authenticate_student = CASE WHEN :authenticated_student THEN 'true' ELSE authenticate_student END,
                authenticated_student = CASE WHEN :authenticated_student THEN TRUE ELSE authenticated_student END,
                is_active = TRUE,
                updated_at = CURRENT_TIMESTAMP,
                role = CAST(:legacy_role AS userrole)
            WHERE integrated_id = :integrated_id
            """
        ),
        {
            "integrated_id": shared_user["integrated_id"],
            "ethics_role": target_role,
            "first_name": resolved_first_name,
            "last_name": resolved_last_name,
            "student_number": resolved_student_number,
            "staff_number": resolved_staff_number,
            "authenticated_student": authenticated_student,
            "legacy_role": legacy_role,
        },
    )
    db.session.expire_all()
    return EthicsUser.find_by_email(shared_user["email"])


def _enable_mba_access_for_shared_user(shared_user, *, descriptor, first_name=None, last_name=None, student_number=None, staff_number=None):
    resolved_first_name, resolved_last_name = _split_name_parts(
        first_name=first_name or shared_user.get("first_name"),
        last_name=last_name or shared_user.get("last_name"),
        email=shared_user.get("email"),
    )
    current_scholar_role = shared_user.get("scholar_role")
    resolved_scholar_role = current_scholar_role
    if descriptor["role"] == MbaRole.SCHOLAR.value:
        if current_scholar_role == MbaScholarRole.EXAMINER.value:
            resolved_scholar_role = MbaScholarRole.BOTH.value
        elif not current_scholar_role:
            resolved_scholar_role = descriptor.get("scholar_role")
    elif descriptor["role"] != MbaRole.SCHOLAR.value:
        resolved_scholar_role = current_scholar_role

    resolved_student_number = student_number if str(student_number or "").isdigit() else None
    resolved_staff_number = staff_number or shared_user.get("staff_number")
    legacy_role = _legacy_role_for_unified_user(
        ethics_role=shared_user.get("ethics_role"),
        mba_role=descriptor["role"],
        scholar_role=resolved_scholar_role,
        current_role=shared_user.get("role"),
    )

    db.session.execute(
        text(
            """
            UPDATE users
            SET
                mba_access = TRUE,
                mba_role = :mba_role,
                scholar_role = :scholar_role,
                first_name = COALESCE(NULLIF(:first_name, ''), first_name),
                last_name = COALESCE(NULLIF(:last_name, ''), last_name),
                full_name = trim(
                    concat_ws(
                        ' ',
                        COALESCE(NULLIF(:first_name, ''), first_name),
                        COALESCE(NULLIF(:last_name, ''), last_name)
                    )
                ),
                student_number = COALESCE(:student_number, student_number),
                staff_number = COALESCE(:staff_number, staff_number),
                is_active = TRUE,
                updated_at = CURRENT_TIMESTAMP,
                role = CAST(:legacy_role AS userrole)
            WHERE integrated_id = :integrated_id
            """
        ),
        {
            "integrated_id": shared_user["integrated_id"],
            "mba_role": descriptor["role"],
            "scholar_role": resolved_scholar_role,
            "first_name": resolved_first_name,
            "last_name": resolved_last_name,
            "student_number": resolved_student_number,
            "staff_number": resolved_staff_number,
            "legacy_role": legacy_role,
        },
    )
    db.session.expire_all()
    return MbaUser.find_by_email(shared_user["email"])


def _ensure_integrated_ethics_user_for_mba_user(mba_user):
    target_role = _ethics_role_for_mba_user(mba_user)
    if not target_role:
        return None

    first_name, last_name = _split_name_parts(
        first_name=mba_user.first_name,
        last_name=mba_user.last_name,
        email=mba_user.email,
    )
    student_number = getattr(getattr(mba_user, "student_profile", None), "student_number", None) or _mba_student_number_from_email(mba_user.email)

    ethics_user = EthicsUser.find_by_email(mba_user.email)
    if ethics_user:
        if not _can_reuse_ethics_role(ethics_user.role, target_role):
            return None
        if target_role == EthicsRole.SUPER_ADMIN.value:
            ethics_user.role = EthicsRole.SUPER_ADMIN.value
        elif target_role == EthicsRole.ADMIN.value and ethics_user.role != EthicsRole.SUPER_ADMIN.value:
            ethics_user.role = EthicsRole.ADMIN.value
    else:
        shared_user = _find_shared_user_row(mba_user.email)
        if shared_user:
            return _enable_ethics_access_for_shared_user(
                shared_user,
                target_role=target_role,
                first_name=first_name,
                last_name=last_name,
                student_number=student_number,
                staff_number=getattr(getattr(mba_user, "scholar_profile", None), "staff_number", None),
            )
        ethics_user = EthicsUser(email=mba_user.email, role=target_role)
        db.session.add(ethics_user)
        db.session.flush()

    ethics_user.first_name = first_name or ethics_user.first_name
    ethics_user.last_name = last_name or ethics_user.last_name
    ethics_user.is_active = True
    if target_role == EthicsRole.STUDENT.value:
        ethics_user.student_number = str(student_number or "") or ethics_user.student_number
        ethics_user.authenticated_student = True
    return ethics_user


def _ensure_legacy_ethics_user(email, *, ethics_role, first_name=None, last_name=None, student_number=None, staff_number=None):
    module = _load_production_ethics_models()
    db_session = module.Session()
    try:
        user = db_session.query(module.User).filter(module.func.lower(module.User.email) == normalize_email(email)).first()
        full_name = _full_name(first_name, last_name, email=email)
        legacy_role = module.UserRole(ethics_role.upper())
        legacy_student_number = int(student_number) if str(student_number or "").isdigit() else None

        if user:
            existing_role = getattr(getattr(user, "role", None), "value", getattr(user, "role", None))
            if not _can_reuse_ethics_role(existing_role, ethics_role):
                return None
            if ethics_role == EthicsRole.SUPER_ADMIN.value:
                user.role = module.UserRole.SUPER_ADMIN
            elif ethics_role == EthicsRole.ADMIN.value and getattr(user.role, "value", user.role) != module.UserRole.SUPER_ADMIN.value:
                user.role = module.UserRole.ADMIN
        else:
            user = module.User(
                full_name=full_name,
                student_number=legacy_student_number,
                email=normalize_email(email),
                staff_number=staff_number,
                password=_temporary_password(),
                role=legacy_role,
            )
            db_session.add(user)
            db_session.flush()

        user.full_name = full_name
        if legacy_student_number is not None:
            user.student_number = legacy_student_number
        if staff_number:
            user.staff_number = staff_number
        user.authenticate_student = "true"

        db_session.commit()
        return user
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def _ensure_mba_user_for_ethics_identity(email, *, ethics_role, first_name=None, last_name=None, student_number=None, staff_number=None):
    descriptor = _mba_access_descriptor_for_ethics_role(ethics_role)
    if not descriptor:
        return None

    first_name, last_name = _split_name_parts(
        first_name=first_name,
        last_name=last_name,
        email=email,
    )
    mba_user = MbaUser.find_by_email(email)
    if mba_user:
        if not _can_reuse_mba_role(mba_user, descriptor):
            return None
        if descriptor["role"] == MbaRole.MAIN_ADMIN.value:
            mba_user.role = MbaRole.MAIN_ADMIN.value
        elif descriptor["role"] == MbaRole.ADMIN.value and mba_user.role != MbaRole.MAIN_ADMIN.value:
            mba_user.role = MbaRole.ADMIN.value
        elif descriptor["role"] == MbaRole.SCHOLAR.value:
            mba_user.role = MbaRole.SCHOLAR.value
            current_scholar_role = mba_user.scholar_role
            if current_scholar_role == MbaScholarRole.EXAMINER.value:
                mba_user.scholar_role = MbaScholarRole.BOTH.value
            elif not current_scholar_role:
                mba_user.scholar_role = descriptor["scholar_role"]
        elif descriptor["role"] == MbaRole.STUDENT.value:
            mba_user.role = MbaRole.STUDENT.value
    else:
        shared_user = _find_shared_user_row(email)
        if shared_user:
            return _enable_mba_access_for_shared_user(
                shared_user,
                descriptor=descriptor,
                first_name=first_name,
                last_name=last_name,
                student_number=student_number,
                staff_number=staff_number,
            )
        mba_user = MbaUser(
            email=normalize_email(email),
            role=descriptor["role"],
            scholar_role=descriptor.get("scholar_role"),
            first_name=first_name,
            last_name=last_name,
            has_profile=False,
            is_active=True,
        )
        mba_user.set_password(_temporary_password())
        db.session.add(mba_user)
        db.session.flush()

    mba_user.first_name = first_name or mba_user.first_name
    mba_user.last_name = last_name or mba_user.last_name
    mba_user.is_active = True

    if descriptor["role"] == MbaRole.STUDENT.value:
        profile = mba_user.student_profile or MbaStudentProfile(user_id=mba_user.id)
        if not mba_user.student_profile:
            db.session.add(profile)
        resolved_student_number = (student_number or _mba_student_number_from_email(email) or "").strip() if isinstance(student_number, str) or student_number is None else str(student_number)
        profile.student_number = resolved_student_number or profile.student_number
        profile.name = first_name or profile.name
        profile.surname = last_name or profile.surname
        profile.degree = profile.degree or "MBA"
        mba_user.has_profile = False
    elif descriptor["role"] == MbaRole.SCHOLAR.value:
        profile = mba_user.scholar_profile or MbaScholarProfile(user_id=mba_user.id)
        if not mba_user.scholar_profile:
            db.session.add(profile)
        profile.name = first_name or profile.name
        profile.surname = last_name or profile.surname
        profile.staff_number = staff_number or profile.staff_number
        mba_user.has_profile = False

    return mba_user


def _ensure_ethics_access_for_mba_user(mba_user):
    ethics_user = _ensure_integrated_ethics_user_for_mba_user(mba_user)
    if not ethics_user:
        return None
    _ensure_legacy_ethics_user(
        mba_user.email,
        ethics_role=ethics_user.role,
        first_name=ethics_user.first_name,
        last_name=ethics_user.last_name,
        student_number=ethics_user.student_number,
        staff_number=getattr(getattr(mba_user, "scholar_profile", None), "staff_number", None),
    )
    return ethics_user


def _ensure_mba_access_for_ethics_user(ethics_user):
    return _ensure_mba_user_for_ethics_identity(
        ethics_user.email,
        ethics_role=ethics_user.role,
        first_name=ethics_user.first_name,
        last_name=ethics_user.last_name,
        student_number=ethics_user.student_number,
        staff_number=getattr(ethics_user, "staff_number", None),
    )


def _find_production_ethics_user_by_email(email):
    module = _load_production_ethics_models()
    db_session = module.Session()
    try:
        user = db_session.query(module.User).filter(module.func.lower(module.User.email) == normalize_email(email)).first()
        if not user:
            return None
        return {
            "email": normalize_email(user.email),
            "full_name": user.full_name,
            "student_number": str(user.student_number) if user.student_number is not None else None,
            "staff_number": user.staff_number,
            "role": getattr(user.role, "value", user.role).lower(),
        }
    finally:
        db_session.close()


def _ensure_mba_access_for_production_ethics_identity(identity):
    if not identity:
        return None
    first_name, last_name = _split_name_parts(full_name=identity.get("full_name"), email=identity.get("email"))
    return _ensure_mba_user_for_ethics_identity(
        identity.get("email"),
        ethics_role=identity.get("role"),
        first_name=first_name,
        last_name=last_name,
        student_number=identity.get("student_number"),
        staff_number=identity.get("staff_number"),
    )


def _ensure_shared_access_for_registered_user(user):
    """Provision the counterpart access record so both login flows resolve the same person."""
    if isinstance(user, MbaUser):
        return _ensure_ethics_access_for_mba_user(user)
    if isinstance(user, EthicsUser):
        return _ensure_mba_access_for_ethics_user(user)
    return None


@lru_cache(maxsize=1)
def _load_production_ethics_models():
    module_path = Path(__file__).resolve().parent / "ethics_production_app" / "models.py"
    spec = importlib.util.spec_from_file_location("integrated_ethics_production_models", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load ethics models from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def authenticate_production_ethics_user(email, password):
    clean_email = normalize_email(email)
    module = _load_production_ethics_models()
    db_session = module.Session()
    try:
        user = db_session.query(module.User).filter(module.func.lower(module.User.email) == clean_email).first()
        if not user or not user.verify_password(password):
            return None, "Invalid email or password."

        if not user.authenticate_student or str(user.authenticate_student).lower() in {"false", "0", "none"}:
            return None, "Access denied."

        return user, None
    finally:
        db_session.close()


def find_mba_profile_by_student_number(student_number):
    clean_number = (student_number or "").strip()
    if not clean_number:
        return None
    return MbaStudentProfile.query.filter_by(student_number=clean_number).first()


def looks_like_email(email):
    return bool(email and "@" in email and "." in email.rsplit("@", 1)[-1])


def _temporary_password():
    return secrets.token_urlsafe(12)


def _client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    return (forwarded_for.split(",", 1)[0].strip() or request.remote_addr or "unknown")[:64]


def _consume_rate_limit(bucket, key, *, limit, window_seconds):
    now = time.monotonic()
    events = _RATE_LIMIT_EVENTS[(bucket, key)]
    while events and (now - events[0]) > window_seconds:
        events.popleft()
    if len(events) >= limit:
        return False
    events.append(now)
    return True


def _check_auth_attempt_limits(action, email=""):
    ip_key = f"{action}:ip:{_client_ip()}"
    email_key = f"{action}:email:{normalize_email(email or '')}" if email else ""
    ip_allowed = _consume_rate_limit("auth", ip_key, limit=12, window_seconds=300)
    email_allowed = True
    if email_key:
        email_allowed = _consume_rate_limit("auth", email_key, limit=6, window_seconds=900)
    return ip_allowed and email_allowed


def _password_reset_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _password_reset_label_for_user(user):
    if user.system_name == "mba":
        return "MBA Portal"
    return "Ethics Portal"


def _build_password_reset_token(user):
    serializer = _password_reset_serializer()
    return serializer.dumps(
        {
            "email": normalize_email(user.email),
            "system": user.system_name,
            "issued_at": datetime.utcnow().isoformat(),
        },
        salt=PASSWORD_RESET_SALT,
    )


def _find_password_reset_user(system_name, email):
    system_name = (system_name or "").strip().lower()
    if system_name == "mba":
        user = MbaUser.find_by_email(email)
        return user if _eligible_mba_password_reset_user(user) else None
    if system_name == "ethics":
        user = EthicsUser.find_by_email(email)
        return user if _eligible_ethics_password_reset_user(user) else None
    return None


def _load_password_reset_user(token):
    serializer = _password_reset_serializer()
    payload = serializer.loads(token, salt=PASSWORD_RESET_SALT, max_age=PASSWORD_RESET_MAX_AGE_SECONDS)
    email = normalize_email(payload.get("email"))
    system_name = payload.get("system")
    user = _find_password_reset_user(system_name, email)
    if not user:
        raise ValueError("Reset target is invalid.")
    return user


def _password_reset_email_body(reset_links):
    login_url = url_for("auth.login", _external=True)
    lines = [
        "Hello,",
        "",
        "You requested a password reset.",
        "Use one of the secure links below to set a new password:",
        "",
    ]
    for item in reset_links:
        lines.append(f"{item['label']}: {item['url']}")
    lines.extend(
        [
            "",
            f"Login link: {login_url}",
            "",
            "These links expire in 60 minutes.",
            "If you did not request this, please ignore this email or contact support.",
        ]
    )
    return "\n".join(lines)


def _eligible_mba_password_reset_user(user):
    if not user or not user.is_active:
        return False
    if user.role in {
        MbaRole.STUDENT.value,
        MbaRole.EXAMINER.value,
        MbaRole.HDC.value,
        MbaRole.ADMIN.value,
        MbaRole.MAIN_ADMIN.value,
    }:
        return True
    return user.role == MbaRole.SCHOLAR.value and user.scholar_role in {
        MbaScholarRole.EXAMINER.value,
        MbaScholarRole.SUPERVISOR.value,
        MbaScholarRole.BOTH.value,
    }


def _eligible_ethics_password_reset_user(user):
    if not user or not user.is_active:
        return False
    return user.role in {
        EthicsRole.STUDENT.value,
        EthicsRole.SUPERVISOR.value,
        EthicsRole.ADMIN.value,
        EthicsRole.SUPER_ADMIN.value,
    }


def _password_reset_users(email):
    clean_email = normalize_email(email)
    users = []

    mba_user = MbaUser.find_by_email(clean_email)
    if _eligible_mba_password_reset_user(mba_user):
        users.append(mba_user)

    ethics_user = EthicsUser.find_by_email(clean_email)
    if _eligible_ethics_password_reset_user(ethics_user):
        users.append(ethics_user)

    return users


def user_has_popia_confirmation(user):
    return bool(getattr(user, "popia_confirmed_at", None))


def _safe_internal_next_url(target):
    if not target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return None
    if target.startswith(url_for("auth.popia_notice")) or target.startswith(url_for("auth.logout")):
        return None
    return target


def post_login_url(user):
    if user.system_name == "ethics":
        return url_for("auth.switch_to_ethics")
    return url_for("mba.dashboard")


def post_login_redirect(user):
    if not user_has_popia_confirmation(user):
        return redirect(url_for("auth.popia_notice"))
    return redirect(post_login_url(user))


def log_ethics_auth_activity(user, action, details=None):
    if user and user.system_name == "ethics":
        db.session.add(EthicsActivityLog(user_id=user.id, action=action, details=details))


def build_ethics_sso_token(user):
    return build_ethics_sso_token_for_email(user.email, source_system=getattr(user, "system_name", ""))


def build_ethics_sso_token_for_email(email, source_system=""):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps(
        {
            "email": normalize_email(email),
            "source_system": source_system,
            "issued_at": datetime.utcnow().isoformat(),
        },
        salt=ETHICS_SSO_SALT,
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return post_login_redirect(current_user)

    if request.method == "POST":
        system = request.form.get("system", "mba").lower()
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password") or ""
        if not _check_auth_attempt_limits("login", email):
            flash("Too many sign-in attempts. Please wait a few minutes and try again.", "error")
            return render_template("auth/login.html", email=email, system=system)

        if system == "ethics":
            _, error = authenticate_production_ethics_user(email, password)
            if error:
                ethics_user = EthicsUser.find_by_email(email)
                if not ethics_user or not ethics_user.check_password(password):
                    flash(error, "error")
                    return render_template("auth/login.html", email=email, system=system)

            token = build_ethics_sso_token_for_email(email, source_system="ethics")
            return redirect(url_for("ethics_sso_bridge", token=token))

        user = MbaUser.find_by_email(email)
        if not user:
            flash("This account does not have MBA access.", "error")
            return render_template("auth/login.html", email=email, system=system)
        if not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email, system=system)

        if not user.is_active:
            flash("This account is inactive. Contact an administrator.", "error")
            return render_template("auth/login.html", email=email, system=system)

        login_user(user)
        log_ethics_auth_activity(user, "login", "Email and password sign-in")
        db.session.commit()
        return post_login_redirect(user)

    return render_template("auth/login.html")


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return post_login_redirect(current_user)

    generic_message = "If an account with that email exists, you will receive a password reset email."
    email = normalize_email(request.form.get("reset_email") or "")

    if looks_like_email(email) and _check_auth_attempt_limits("forgot-password", email):
        users = _password_reset_users(email)
        if users:
            reset_links = [
                {
                    "label": _password_reset_label_for_user(user),
                    "url": url_for("auth.reset_password", token=_build_password_reset_token(user), _external=True),
                }
                for user in users
            ]
            try:
                for user in users:
                    log_ethics_auth_activity(user, "password_reset_requested", "Password reset link requested")
                sent = send_email(email, "Reset Your Password", _password_reset_email_body(reset_links))
                if not sent:
                    raise RuntimeError("Mail delivery is not configured.")
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Password reset email failed for %s", email)

    flash(generic_message, "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if current_user.is_authenticated:
        return post_login_redirect(current_user)

    token = (request.values.get("token") or "").strip()
    if not token:
        flash("Invalid or expired password reset link.", "error")
        return redirect(url_for("auth.login"))

    try:
        reset_user = _load_password_reset_user(token)
    except Exception:
        flash("Invalid or expired password reset link.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        if len(password) < 12:
            return render_template(
                "auth/reset_password.html",
                token=token,
                reset_system=reset_user.system_name,
                reset_email=reset_user.email,
                error_message="Use a password with at least 12 characters.",
            )
        if password != confirm_password:
            return render_template(
                "auth/reset_password.html",
                token=token,
                reset_system=reset_user.system_name,
                reset_email=reset_user.email,
                error_message="Passwords do not match.",
            )

        reset_user.set_password(password)
        log_ethics_auth_activity(reset_user, "password_reset_completed", "Password reset completed from secure link")
        db.session.commit()
        flash("Your password has been updated. You can sign in now.", "success")
        return redirect(url_for("auth.login"))

    return render_template(
        "auth/reset_password.html",
        token=token,
        reset_system=reset_user.system_name,
        reset_email=reset_user.email,
    )


@auth_bp.route("/popia-notice", methods=["GET", "POST"])
@login_required
def popia_notice():
    next_url = _safe_internal_next_url(request.values.get("next"))
    if user_has_popia_confirmation(current_user):
        return redirect(next_url or post_login_url(current_user))

    if request.method == "POST":
        if request.form.get("popia_confirmed") != "yes":
            flash("Please confirm the POPIA notice before continuing.", "error")
            return render_template(
                "auth/popia_notice.html",
                notice_version=POPIA_NOTICE_VERSION,
                next_url=next_url,
            )

        forwarded_for = request.headers.get("X-Forwarded-For", "")
        remote_ip = (forwarded_for.split(",", 1)[0].strip() or request.remote_addr or "")[:64]
        current_user.popia_confirmed_at = datetime.utcnow()
        current_user.popia_notice_version = POPIA_NOTICE_VERSION
        current_user.popia_confirmed_ip = remote_ip
        current_user.popia_confirmed_user_agent = (request.headers.get("User-Agent") or "")[:255]
        log_ethics_auth_activity(current_user, "popia_confirmed", f"POPIA notice {POPIA_NOTICE_VERSION} confirmed")
        db.session.commit()
        flash("POPIA notice confirmed. Thank you.", "success")
        return redirect(next_url or post_login_url(current_user))

    return render_template(
        "auth/popia_notice.html",
        notice_version=POPIA_NOTICE_VERSION,
        next_url=next_url,
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return post_login_redirect(current_user)

    system = "mba"

    if request.method == "POST":
        submitted_student_email = normalize_email(request.form.get("student_email") or "")
        legacy_student_number = request.form.get("student_number", "").strip()
        if submitted_student_email:
            email = submitted_student_email
            match = UJ_STUDENT_EMAIL_RE.match(email)
            student_number = match.group("number") if match else ""
        else:
            student_number = legacy_student_number
            email = student_email_for(student_number)
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not email:
            flash("Student email address is required.", "error")
            return render_template("auth/register.html", system=system)

        if not looks_like_email(email):
            flash("Enter a valid student email address.", "error")
            return render_template("auth/register.html", system=system, student_email=submitted_student_email)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("auth/register.html", system=system, student_email=email)

        if find_registered_user(email, system):
            flash("An account already exists for that student email.", "error")
            return render_template("auth/register.html", system=system, student_email=email)

        if system == "mba" and find_mba_profile_by_student_number(student_number):
            flash("An MBA account already exists for that student email address.", "error")
            return render_template("auth/register.html", system=system, student_email=email)

        user = (
            MbaUser(email=email)
            if system == "mba"
            else EthicsUser(email=email, student_number=student_number or None, authenticated_student=True)
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        if system == "mba":
            db.session.add(MbaStudentProfile(user_id=user.id, student_number=student_number or None))

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("An account already exists for that student email address.", "error")
            return render_template("auth/register.html", system=system, student_email=email)
        login_user(user)
        log_ethics_auth_activity(user, "register", "Student registered an Ethics account")
        db.session.commit()
        return post_login_redirect(user)

    return render_template("auth/register.html", system=system)


@auth_bp.route("/auth/microsoft")
def microsoft_login():
    if "microsoft" not in oauth._clients:
        flash("Microsoft sign-in is currently unavailable. Use email and password to sign in.", "error")
        return redirect(url_for("auth.login"))

    system = request.args.get("system", "mba")
    session["microsoft_login_system"] = system if system in {"mba", "ethics"} else "mba"
    redirect_uri = current_app.config["MICROSOFT_REDIRECT_URI"] or url_for("auth.microsoft_callback", _external=True)
    return oauth.microsoft.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/microsoft/callback")
def microsoft_callback():
    if "microsoft" not in oauth._clients:
        flash("Microsoft login is not configured.", "error")
        return redirect(url_for("auth.login"))

    token = oauth.microsoft.authorize_access_token()
    userinfo = token.get("userinfo") or oauth.microsoft.userinfo(token=token)
    email = normalize_email(userinfo.get("email") or userinfo.get("preferred_username") or userinfo.get("upn"))
    subject = userinfo.get("sub") or userinfo.get("oid")

    if not email:
        flash("Microsoft did not return an email address.", "error")
        return redirect(url_for("auth.login"))

    requested_system = session.pop("microsoft_login_system", "mba")
    user = find_registered_user(email, requested_system)
    if not user and requested_system == "mba" and is_uj_student_email(email):
        student_number = email.split("@", 1)[0]
        if find_mba_profile_by_student_number(student_number):
            flash("An MBA account already exists for that student email address.", "error")
            return redirect(url_for("auth.login"))
        user = MbaUser(
            email=email,
            microsoft_subject=subject,
            role=MbaRole.STUDENT.value,
            has_profile=True,
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(MbaStudentProfile(user_id=user.id, student_number=student_number))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("An MBA account already exists for that student email address.", "error")
            return redirect(url_for("auth.login"))

    if not user:
        flash("Your Microsoft account email is not registered in this system.", "error")
        return redirect(url_for("auth.login"))

    if not user.is_active:
        flash("This account is inactive. Contact an administrator.", "error")
        return redirect(url_for("auth.login"))

    user.microsoft_subject = subject
    log_ethics_auth_activity(user, "login", "Microsoft sign-in")
    db.session.commit()
    login_user(user)
    return post_login_redirect(user)


@auth_bp.route("/switch/ethics")
@login_required
def switch_to_ethics():
    if current_user.system_name == "mba" and not EthicsUser.find_by_email(current_user.email):
        flash("This account does not have Ethics access.", "error")
        return redirect(url_for("mba.dashboard"))
    token = build_ethics_sso_token(current_user)
    return redirect(url_for("ethics_sso_bridge", token=token))


@auth_bp.route("/logout")
def logout():
    if current_user.is_authenticated and current_user.system_name == "ethics":
        log_ethics_auth_activity(current_user, "logout", "User signed out")
        db.session.commit()
    session.clear()
    logout_user()
    return redirect(url_for("auth.login"))
