import threading

from flask import Flask, abort, redirect, request, url_for
from flask_login import current_user
from sqlalchemy import create_engine, inspect, text
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from config import Config

from .auth import auth_bp, user_has_popia_confirmation
from .cli_commands import register_cli
from .context_processors import inject_auth_flags_factory
from .extensions import db, login_manager, migrate, oauth
from .mba.routes import mba_bp
from .oauth_config import configure_microsoft_oauth
from .security import init_csrf
from .seeds import seed_mba_disciplines


def _bootstrap_sqlite_dev_database(app):
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if not database_uri.startswith("sqlite:///"):
        return

    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        required_tables = {"user_Registration", "user_profile"}
        if required_tables.issubset(existing_tables):
            return

        db.create_all()
        seed_mba_disciplines()
        db.session.commit()
        app.logger.info("Initialized local SQLite database schema automatically.")


class _LazyEthicsApplication:
    """Load the legacy ethics application only when it is first requested."""

    def __init__(self, app):
        self._parent_app = app
        self._application = None
        self._lock = threading.Lock()

    def __call__(self, environ, start_response):
        if self._application is None:
            with self._lock:
                if self._application is None:
                    from .ethics_production_app import get_mounted_app

                    self._application = get_mounted_app()
                    self._parent_app.logger.info("Loaded production ethics app")
        return self._application(environ, start_response)


def _mount_production_ethics_app(app):
    app.wsgi_app = DispatcherMiddleware(
        app.wsgi_app,
        {"/ethics": _LazyEthicsApplication(app)},
    )
    app.logger.info("Configured production ethics app at /ethics")


def _ensure_postgres_support_tables(app):
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if not database_uri.startswith("postgresql"):
        return

    with app.app_context():
        statements = [
            """
            CREATE TABLE IF NOT EXISTS mba_reminder_states (
                id SERIAL PRIMARY KEY,
                reminder_key VARCHAR(255) NOT NULL UNIQUE,
                last_sent_at TIMESTAMP WITHOUT TIME ZONE,
                last_sent_by_id BIGINT REFERENCES users(integrated_id),
                dismissed_at TIMESTAMP WITHOUT TIME ZONE,
                dismissed_by_id BIGINT REFERENCES users(integrated_id),
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mba_user_signatures (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(integrated_id),
                file_data BYTEA NOT NULL,
                mime_type VARCHAR(120) NOT NULL,
                file_size INTEGER NOT NULL,
                sha256 VARCHAR(64) NOT NULL,
                source VARCHAR(40),
                signature_type VARCHAR(40) NOT NULL DEFAULT 'primary',
                printed_name VARCHAR(255),
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_mba_user_signatures_user_id ON mba_user_signatures (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_mba_user_signatures_sha256 ON mba_user_signatures (sha256)",
            "CREATE INDEX IF NOT EXISTS ix_mba_user_signatures_signature_type ON mba_user_signatures (signature_type)",
            "CREATE INDEX IF NOT EXISTS ix_mba_user_signatures_is_active ON mba_user_signatures (is_active)",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_1_invited_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_1_reminder_sent_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_1_hdc_decision VARCHAR(20)",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_1_hdc_decision_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_1_hdc_decision_assessor_id INTEGER",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_2_invited_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_2_reminder_sent_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_2_hdc_decision VARCHAR(20)",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_2_hdc_decision_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_2_hdc_decision_assessor_id INTEGER",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_3_invited_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessor_3_reminder_sent_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS jbs5_hdc_comments TEXT",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS dissertation_released_to_assessors BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS dissertation_released_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS supervisor_pool_released_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS supervisor_pool_released_by_id BIGINT",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS dissertation_moodle_request_sent_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS dissertation_resubmission_requested_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS dissertation_resubmission_open BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS dissertation_resubmission_opened_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS additional_assessment_requested_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS corrections_requested_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS corrections_student_resubmitted_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS corrections_supervisor_approved_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS corrections_supervisor_comments TEXT",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS corrections_supervisor_rejected_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS corrections_supervisor_rejection_comments TEXT",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS assessment_results_forwarded_to_supervisor_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS corrections_released_to_student_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS module_completion_status VARCHAR(60) NOT NULL DEFAULT 'not_checked'",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS module_completion_marks_email VARCHAR(255)",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS module_completion_verification_token VARCHAR(128)",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS module_completion_requested_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS module_completion_responded_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS module_completion_response VARCHAR(10)",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS jbs5_hdc_approved_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS results_hdc_approved_mark DOUBLE PRECISION",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS results_hdc_approved_classification VARCHAR(40)",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS results_released_to_supervisor_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS supervisor_title_change_requested_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS supervisor_title_change_request TEXT",
            "ALTER TABLE IF EXISTS mba_projects ADD COLUMN IF NOT EXISTS supervisor_title_change_resolved_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_project_supervisor_invitations ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE IF EXISTS mba_project_documents ADD COLUMN IF NOT EXISTS file_data BYTEA",
            "ALTER TABLE IF EXISTS mba_project_documents ADD COLUMN IF NOT EXISTS mime_type VARCHAR(120)",
            "ALTER TABLE IF EXISTS mba_project_documents ADD COLUMN IF NOT EXISTS file_size INTEGER",
            "ALTER TABLE IF EXISTS mba_student_profiles ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)",
            "ALTER TABLE IF EXISTS mba_student_profiles ADD COLUMN IF NOT EXISTS id_passport_number VARCHAR(80)",
            "ALTER TABLE IF EXISTS mba_student_profiles ADD COLUMN IF NOT EXISTS default_signing_location VARCHAR(255)",
            "ALTER TABLE IF EXISTS mba_student_profiles ADD COLUMN IF NOT EXISTS form_defaults JSON",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS staff_number VARCHAR(80)",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS id_passport_number VARCHAR(80)",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS default_signing_location VARCHAR(255)",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS form_defaults JSON",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS students_supervised_total INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS students_assessed_total INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS publication_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS selected_publications TEXT",
            "ALTER TABLE IF EXISTS mba_scholar_profiles ADD COLUMN IF NOT EXISTS scholarly_profile_links TEXT",
        ]
        for statement in statements:
            db.session.execute(text(statement))
        db.session.commit()
        db.session.remove()
        app.logger.info("Ensured required Postgres support tables exist.")


def _ensure_postgres_model_tables(app):
    """Create missing model tables through psycopg2's stable reflection path."""
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if not database_uri.startswith("postgresql"):
        return

    if database_uri.startswith("postgresql+psycopg://"):
        schema_uri = database_uri.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    elif database_uri.startswith("postgresql://"):
        schema_uri = database_uri.replace("postgresql://", "postgresql+psycopg2://", 1)
    else:
        schema_uri = database_uri

    schema_engine = create_engine(schema_uri, pool_pre_ping=True)
    try:
        db.metadata.create_all(bind=schema_engine, checkfirst=True)
    finally:
        schema_engine.dispose()
    app.logger.info("Ensured model-backed Postgres tables exist.")


def _ensure_ethics_postgres_columns(app):
    """Keep the mounted legacy ORM compatible before its first request."""
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if not database_uri.startswith("postgresql"):
        return

    with app.app_context():
        db.session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS archived_ethics_forms (
                    archive_id VARCHAR(255) PRIMARY KEY,
                    form_type VARCHAR(20) NOT NULL,
                    original_form_id VARCHAR(255) NOT NULL,
                    student_user_id VARCHAR(255) NOT NULL,
                    student_name VARCHAR(255),
                    student_email VARCHAR(255),
                    original_created_at TIMESTAMP WITH TIME ZONE,
                    original_submitted_at TIMESTAMP WITH TIME ZONE,
                    archived_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_by_user_id VARCHAR(255) NOT NULL,
                    archive_reason TEXT,
                    snapshot_json TEXT NOT NULL
                )
                """
            )
        )
        for index_statement in (
            "CREATE INDEX IF NOT EXISTS ix_archived_ethics_forms_form_type ON archived_ethics_forms (form_type)",
            "CREATE INDEX IF NOT EXISTS ix_archived_ethics_forms_original_form_id ON archived_ethics_forms (original_form_id)",
            "CREATE INDEX IF NOT EXISTS ix_archived_ethics_forms_student_user_id ON archived_ethics_forms (student_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_archived_ethics_forms_archived_at ON archived_ethics_forms (archived_at)",
        ):
            db.session.execute(text(index_statement))

        db.session.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'form_c'
                          AND column_name = 'submission_date'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'form_c'
                          AND column_name = 'submitted_at'
                    ) THEN
                        ALTER TABLE form_c RENAME COLUMN submission_date TO submitted_at;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'form_c'
                          AND column_name = 'signature_date'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'form_c'
                          AND column_name = 'supervisor_signature_date'
                    ) THEN
                        ALTER TABLE form_c RENAME COLUMN signature_date TO supervisor_signature_date;
                    END IF;
                END $$
                """
            )
        )
        for table_name in ("form_a", "form_b", "form_c"):
            for column_name, column_type in (
                ("form_supervisor_status", "TEXT"),
                ("ethics_status", "TEXT"),
                ("ethics_form_status", "TEXT"),
                ("ethics_signature", "TEXT"),
                ("ethics_signature_date", "TIMESTAMP WITH TIME ZONE"),
            ):
                db.session.execute(
                    text(
                        f'ALTER TABLE IF EXISTS "{table_name}" '
                        f'ADD COLUMN IF NOT EXISTS "{column_name}" {column_type}'
                    )
                )
        db.session.commit()
        db.session.remove()
        app.logger.info("Ensured required ethics workflow tables and columns exist.")


def _ensure_unified_user_columns(app):
    """Upgrade a legacy shared users table before ORM-backed login queries run."""
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if not database_uri.startswith("postgresql"):
        return

    with app.app_context():
        users_exists = db.session.execute(
            text("SELECT to_regclass('public.users') IS NOT NULL")
        ).scalar()
        if not users_exists:
            return

        has_integrated_id = db.session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'users'
                      AND column_name = 'integrated_id'
                )
                """
            )
        ).scalar()
        legacy_schema = not has_integrated_id

        statements = (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS integrated_id BIGINT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS mba_role VARCHAR(40)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS scholar_role VARCHAR(40)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ethics_role VARCHAR(40)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS has_profile BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS has_signature BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS has_cv BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS mba_access BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ethics_access BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS authenticated_student BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS supervisor_integrated_id BIGINT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS watched_demo BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS microsoft_subject VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(120)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR(120)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS popia_confirmed_at TIMESTAMP",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS popia_notice_version VARCHAR(40)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS popia_confirmed_ip VARCHAR(64)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS popia_confirmed_user_agent VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "CREATE SEQUENCE IF NOT EXISTS users_integrated_id_seq",
            "ALTER TABLE users ALTER COLUMN integrated_id SET DEFAULT nextval('users_integrated_id_seq')",
            "UPDATE users SET integrated_id = nextval('users_integrated_id_seq') WHERE integrated_id IS NULL",
            "ALTER TABLE users ALTER COLUMN integrated_id SET NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_integrated_id ON users(integrated_id)",
        )
        for statement in statements:
            db.session.execute(text(statement))

        if legacy_schema:
            db.session.execute(text("UPDATE users SET ethics_access = TRUE"))
            db.session.execute(text("""
            UPDATE users
            SET mba_role = COALESCE(
                    mba_role,
                    CASE upper(role::text)
                        WHEN 'SUPER_ADMIN' THEN 'main_admin'
                        WHEN 'ADMIN' THEN 'admin'
                        WHEN 'SUPERVISOR' THEN 'scholar'
                        WHEN 'REVIEWER' THEN 'examiner'
                        WHEN 'REC' THEN 'hdc'
                        ELSE 'student'
                    END
                ),
                scholar_role = COALESCE(
                    scholar_role,
                    CASE upper(role::text)
                        WHEN 'SUPERVISOR' THEN 'supervisor'
                        WHEN 'REVIEWER' THEN 'examiner'
                        ELSE NULL
                    END
                ),
                ethics_role = COALESCE(ethics_role, lower(role::text)),
                mba_access = CASE
                    WHEN upper(role::text) IN ('SUPER_ADMIN', 'ADMIN') THEN TRUE
                    ELSE FALSE
                END
            """))
        db.session.commit()
        db.session.remove()
        db.engine.dispose()
        app.logger.info("Ensured unified user columns exist.")


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    oauth.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    init_csrf(app)

    configure_microsoft_oauth(app)
    register_cli(app)

    _ensure_unified_user_columns(app)
    _ensure_postgres_model_tables(app)
    _ensure_postgres_support_tables(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(mba_bp, url_prefix="/mba")

    app.context_processor(inject_auth_flags_factory(app))

    @app.before_request
    def require_popia_confirmation_before_system_access():
        if not current_user.is_authenticated:
            return None
        endpoint = request.endpoint or ""
        if endpoint == "static" or endpoint in {"auth.popia_notice", "auth.logout"}:
            return None
        if user_has_popia_confirmation(current_user):
            return None
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("auth.popia_notice", next=next_url))

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    @app.route("/")
    def index():
        return redirect(url_for("mba.dashboard"))

    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    @app.route("/switch/ethics-sso")
    def ethics_sso_bridge():
        token = request.args.get("token", "")
        if not token:
            abort(400)
        return redirect(f"/ethics/sso-login?token={token}")

    _bootstrap_sqlite_dev_database(app)
    _ensure_ethics_postgres_columns(app)
    _mount_production_ethics_app(app)

    return app
