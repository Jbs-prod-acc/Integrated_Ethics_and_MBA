
from datetime import datetime
from app.models import db_session, User, Rec, UserRole, UserInfo, FormA, FormB, FormC, FormD, FormUploads, Documents, FormARequirements, Watched
from app.models import db_session, User, Rec, UserRole, UserInfo, FormA, FormB, FormC, FormD, FormUploads, Documents, FormARequirements, Watched, UserActivityLog, LoginLog
from flask import jsonify
from flask import Flask, abort, flash, g, make_response, render_template, request, redirect, url_for, session, jsonify, send_from_directory, send_file
from app.models import db_session, User, Rec, UserRole, UserInfo, FormA, FormB, FormC, FormD, FormUploads, Documents, FormARequirements, Watched
from utils.helpers import generate_reset_token, send_email, validate_password
from utils.activity_logger import log_user_activity
import json
import mimetypes
from db_queries import getFormAData, getSupervisorsList
import os
import zipfile
import pandas as pd
from werkzeug.utils import secure_filename
import os, traceback
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import extract
import io
import pdfkit
from werkzeug.utils import secure_filename
import secrets
from dotenv import load_dotenv
import uuid
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
import pytz
from flask_cors import CORS
# Import CSRFProtect if available; provide a no-op fallback for environments
# where flask-wtf or its dependencies are incompatible (allows test client to run).
try:
    from flask_wtf.csrf import CSRFProtect
except Exception:
    class CSRFProtect:
        def __init__(self, app=None):
            self._app = app
        def init_app(self, app):
            return None
        def exempt(self, view):
            return view
from datetime import date
from sqlalchemy import desc,asc,cast ,Date,func,union_all,and_, not_, or_, extract, String
from sqlalchemy.orm import joinedload, defer
from collections import defaultdict
from mailtrap import configure_mail, send_email, mail
from flask_mail import Mail, Message
from flask import current_app
from sqlalchemy import create_engine
import time
from functools import wraps
from sqlalchemy.exc import OperationalError
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import traceback
from sqlalchemy import text

import sqlalchemy
# Load environment variables from .env file
load_dotenv()

app = Flask(__name__,static_folder='static')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

# Apply Config (includes session security settings)

# Add robust DB connection option for Flask-SQLAlchemy
app.config.from_object('config.Config')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

# Configure CORS with restrictions from config
CORS(app, origins=app.config.get('CORS_ORIGINS', ['https://jbs-ethics.onrender.com']))

csrf = CSRFProtect(app)
configure_mail(app)

# --- Robust SQLAlchemy DB engine with pool_pre_ping ---
if hasattr(sqlalchemy, 'create_engine'):
    # If you use a custom engine, set pool_pre_ping=True
    import os
    db_url = os.getenv('DATABASE_URL') or app.config.get('SQLALCHEMY_DATABASE_URI')
    if db_url:
        try:
            engine = create_engine(db_url, pool_pre_ping=True)
        except Exception:
            pass

# Expose a `csrf_token()` helper to Jinja templates.
# If `flask_wtf` is installed we use `generate_csrf()` to produce a token,
# otherwise we provide a safe no-op that returns an empty string so templates
# calling `{{ csrf_token() }}` don't raise `UndefinedError` in test/dev envs.
try:
    from flask_wtf.csrf import generate_csrf
    app.jinja_env.globals['csrf_token'] = lambda: generate_csrf()
except Exception:
    app.jinja_env.globals['csrf_token'] = lambda: ''

# Add a Jinja filter to load JSON strings safely in templates (used for certificate conditions)
def _from_json_filter(s):
    try:
        return json.loads(s) if s else []
    except Exception:
        return []

app.jinja_env.filters['from_json'] = _from_json_filter

# Timezone helper - South African Standard Time (SAST) is UTC+2
def get_local_time():
    """Get current time in South African timezone (SAST - UTC+2)"""
    sa_tz = pytz.timezone('Africa/Johannesburg')
    return datetime.now(sa_tz)


def parse_admin_log_date(date_text):
    date_text = (date_text or '').strip()
    if not date_text:
        return None

    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            continue
    raise ValueError("Invalid date format")


def create_user_activity_entry(user_id, action, page=None, target_user_id=None, details=None, duration_seconds=None, timestamp=None):
    if not user_id:
        return

    serialized_details = details
    if isinstance(details, (dict, list, tuple)):
        serialized_details = json.dumps(details, default=str)
    elif details is not None:
        serialized_details = str(details)

    entry = UserActivityLog(
        user_id=user_id,
        action=action,
        page=page,
        target_user_id=target_user_id,
        timestamp=timestamp or datetime.utcnow(),
        user_agent=request.user_agent.string if request else None,
        details=serialized_details,
        duration_seconds=duration_seconds
    )
    db_session.add(entry)
    db_session.commit()

# Generate strong secret key with: python -c "import secrets; print(secrets.token_hex(32))"
app.secret_key = os.getenv('SECRET_KEY')
if not app.secret_key:
    raise ValueError("SECRET_KEY environment variable is required!")

mail = Mail(app)

# =====================================================================================================
# DATABASE SESSION TEARDOWN - Clean up scoped_session after each request
# =====================================================================================================
@app.teardown_appcontext
def shutdown_session(exception=None):
    """Remove scoped_session at the end of each request to prevent connection issues"""
    from app.models import db_session
    db_session.remove()


AUTH_SESSION_KEYS = (
    'loggedin',
    'id',
    'name',
    'last_active',
    'role',
    'supervisor_role',
    'admin_role',
    'rec_role',
    'reviewer_role',
    'super_role',
    'active_forma_id',
)


def clear_auth_session():
    """Remove authentication-related session state without wiping flash messages."""
    for key in AUTH_SESSION_KEYS:
        session.pop(key, None)


def get_current_user():
    """Return the authenticated user for the current session, if any."""
    user_id = session.get('id')
    if not user_id:
        return None
    return db_session.query(User).filter_by(user_id=user_id).first()


def role_value(user):
    role = getattr(user, 'role', None)
    return getattr(role, 'value', role)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get('id'):
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for('login_page'))
        return view(*args, **kwargs)
    return wrapper


def role_required(*allowed_roles):
    allowed = {role.upper() for role in allowed_roles}

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                flash("Your session has expired. Please log in again.", "warning")
                return redirect(url_for('login_page'))
            if str(role_value(user) or '').upper() not in allowed:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def _find_latest_form_for_user(model, user_id):
    query = db_session.query(model).filter_by(user_id=user_id)
    if hasattr(model, 'submitted_at'):
        query = query.order_by(model.submitted_at.desc().nullslast(), model.created_at.desc().nullslast())
    elif hasattr(model, 'submission_date'):
        query = query.order_by(model.submission_date.desc().nullslast(), model.created_at.desc().nullslast())
    return query.first()


def _find_all_forms_for_user(model, user_id, *, options=None):
    query = db_session.query(model)
    if options:
        query = query.options(*options)
    query = query.filter_by(user_id=user_id)
    if hasattr(model, 'submitted_at'):
        query = query.order_by(model.submitted_at.desc().nullslast(), model.created_at.desc().nullslast())
    elif hasattr(model, 'submission_date'):
        query = query.order_by(model.submission_date.desc().nullslast(), model.created_at.desc().nullslast())
    else:
        query = query.order_by(model.created_at.desc().nullslast())
    return query.all()


def has_reviewer_feedback(form):
    if not form:
        return False

    feedback_fields = (
        'review_date',
        'review_date1',
        'review_recommendation',
        'review_recommendation1',
        'review_form_comments',
        'review_form_comments1',
        'review_additional_comments',
        'review_additional_comments1',
        'form_review_comment',
        'form_review_comment1',
        'form_reviewed_by',
        'form_reviewed_by1',
    )
    return any(getattr(form, field_name, None) for field_name in feedback_fields)


def _copy_missing_review_slot_fields(source_form, target_form, source_suffix, target_suffix):
    slot_field_bases = (
        'review_date',
        'review_org_permission_status',
        'review_org_permission_comments',
        'review_waiver_status',
        'review_waiver_comments',
        'form_status',
        'review_form_status',
        'review_form_comments',
        'review_questions_status',
        'review_questions_comments',
        'review_consent_status',
        'review_consent_comments',
        'review_proposal_status',
        'review_proposal_comments',
        'review_additional_comments',
        'review_recommendation',
        'review_supervisor_signature',
        'review_signature_date',
        'form_review_comment',
        'form_reviewed_by',
        'review_status',
    )

    copied_any = False
    for base_name in slot_field_bases:
        source_field = f"{base_name}{source_suffix}"
        target_field = f"{base_name}{target_suffix}"
        if not hasattr(source_form, source_field) or not hasattr(target_form, target_field):
            continue

        source_value = getattr(source_form, source_field, None)
        target_value = getattr(target_form, target_field, None)
        if not source_value:
            continue

        if isinstance(source_value, bool):
            should_copy = bool(source_value) and not bool(target_value)
        else:
            should_copy = target_value in (None, '')

        if should_copy:
            setattr(target_form, target_field, source_value)
            copied_any = True

    return copied_any


def merge_reviewer_feedback_from_related_draft(form):
    if not form or not getattr(form, 'user_id', None):
        return form

    timestamp_field_name = None
    if hasattr(type(form), 'submitted_at'):
        timestamp_field_name = 'submitted_at'
    elif hasattr(type(form), 'submission_date'):
        timestamp_field_name = 'submission_date'

    if not timestamp_field_name or getattr(form, timestamp_field_name, None) is None:
        return form

    model = type(form)
    timestamp_column = getattr(model, timestamp_field_name)
    draft_candidates = (
        db_session.query(model)
        .filter(
            model.user_id == form.user_id,
            model.form_id != form.form_id,
            timestamp_column.is_(None),
        )
        .order_by(model.created_at.desc().nullslast())
        .all()
    )

    source_draft = next((draft for draft in draft_candidates if has_reviewer_feedback(draft)), None)
    if not source_draft:
        return form

    copied_any = False
    slot_configs = (
        ('', 'reviewer_name1', 'form_reviewed_by'),
        ('1', 'reviewer_name2', 'form_reviewed_by1'),
    )

    for source_suffix, source_reviewer_attr, source_reviewed_by_attr in slot_configs:
        reviewer_id = (
            getattr(source_draft, source_reviewed_by_attr, None)
            or getattr(source_draft, source_reviewer_attr, None)
        )
        if not reviewer_id:
            continue

        target_suffix = None
        if reviewer_id == getattr(form, 'reviewer_name1', None):
            target_suffix = ''
        elif reviewer_id == getattr(form, 'reviewer_name2', None):
            target_suffix = '1'
        elif reviewer_id == getattr(source_draft, source_reviewer_attr, None):
            target_suffix = source_suffix

        if target_suffix is None:
            continue

        if _copy_missing_review_slot_fields(source_draft, form, source_suffix, target_suffix):
            copied_any = True

    if copied_any and getattr(form, 'rejected_or_accepted', None) is False:
        form.rejected_or_accepted = True

    return form


STUDENT_CORRECTION_STATUSES = {
    'Corrections Required',
    'Submitted to Student for Corrections',
}


def is_student_correction_state(form):
    if not form:
        return False

    if getattr(form, 'status', None) in STUDENT_CORRECTION_STATUSES:
        return True

    if bool(getattr(form, 'visible_to_student', False)):
        return True

    normalized_review_comments = {
        (getattr(form, 'form_review_comment', None) or '').strip().lower(),
        (getattr(form, 'form_review_comment1', None) or '').strip().lower(),
        (getattr(form, 'review_recommendation', None) or '').strip().lower(),
        (getattr(form, 'review_recommendation1', None) or '').strip().lower(),
    }
    if any(
        status == 'resubmission required' or 'approved with minor changes' in status
        for status in normalized_review_comments
    ):
        return True

    normalized_return_statuses = {
        (getattr(form, 'recommendation', None) or '').strip().lower(),
        (getattr(form, 'ethics_status', None) or '').strip().lower(),
        (getattr(form, 'form_supervisor_status', None) or '').strip().lower(),
    }
    return any(status in {'revisions required', 'revision required'} for status in normalized_return_statuses)


def is_student_form_locked(form):
    if not form:
        return False

    submission_timestamp = getattr(form, 'submitted_at', None) or getattr(form, 'submission_date', None)
    if not submission_timestamp:
        return False

    return not is_student_correction_state(form)


def get_student_submission_timestamp(form):
    if not form:
        return None
    return getattr(form, 'submitted_at', None) or getattr(form, 'submission_date', None)


def get_student_dashboard_status(form):
    if not form:
        return ''

    if getattr(form, 'status', None) == 'Submitted to Student for Corrections':
        return 'Form Was Returned. Please Review The Feedback and Resubmit'

    if getattr(form, 'status', None) == 'Corrections Required':
        return 'Corrections Required'

    if getattr(form, 'rec_status', None) == 'Approved':
        return 'Approved'

    if getattr(form, 'certificate_issued', None) and getattr(form, 'certificate_received', None):
        return 'Certificate Issued'

    if is_student_correction_state(form):
        return 'Form Was Returned. Please Review The Feedback and Resubmit'

    if getattr(form, 'submitted_to_rec', False):
        return 'Form Submitted To REC'

    if getattr(form, 'reviewer_name1', None) or getattr(form, 'reviewer_name2', None):
        return 'Form Submitted To Ethics Admin'

    if getattr(form, 'rejected_or_accepted', False) and getattr(form, 'supervisor_date', None):
        return 'Form Submitted To Ethics Admin'

    if getattr(form, 'supervisor_date', None):
        return 'Form Submitted To Ethics Admin'

    if get_student_submission_timestamp(form):
        return 'Form Submitted To Supervisor'

    return 'Draft saved - not yet submitted'


def redirect_if_student_form_locked(form, form_label='This form'):
    if is_student_form_locked(form):
        flash(
            f"{form_label} has already been submitted to the supervisor and is locked until it is sent back to the student.",
            "warning",
        )
        return redirect(url_for("student_dashboard"))
    return None


def reset_form_review_feedback(form):
    if not form:
        return

    fields_to_clear = [
        'supervisor_feedback',
        'recommendation',
        'supervisor_signature',
        'supervisor_date',
        'ethics_signature_date',
        'signature_date',
        'review_form_status',
        'review_form_comments',
        'review_form_status1',
        'review_form_comments1',
        'review_org_permission_status',
        'review_org_permission_comments',
        'review_org_permission_status1',
        'review_org_permission_comments1',
        'review_waiver_status',
        'review_waiver_comments',
        'review_waiver_status1',
        'review_waiver_comments1',
        'review_questions_status',
        'review_questions_comments',
        'review_questions_status1',
        'review_questions_comments1',
        'review_consent_status',
        'review_consent_comments',
        'review_consent_status1',
        'review_consent_comments1',
        'review_proposal_status',
        'review_proposal_comments',
        'review_proposal_status1',
        'review_proposal_comments1',
        'review_additional_comments',
        'review_additional_comments1',
        'review_recommendation',
        'review_recommendation1',
        'review_supervisor_signature',
        'review_supervisor_signature1',
        'review_date',
        'review_date1',
        'review_signature_date',
        'review_signature_date1',
        'form_review_comment',
        'form_review_comment1',
        'form_reviewed_by',
        'form_reviewed_by1',
        'form_a_comment',
        'questions_comment',
        'consent_comment',
        'proposal_comment',
        'org_permission_comment',
        'waiver_comment',
    ]

    for field_name in fields_to_clear:
        if hasattr(form, field_name):
            setattr(form, field_name, None)

    for field_name in ('review_status', 'review_status1'):
        if hasattr(form, field_name):
            setattr(form, field_name, False)

    for field_name in (
        'reviewer_name1',
        'reviewer_name2',
        'submitted_to_admin',
        'submitted_to_reviewers',
        'submitted_to_rec',
        'rejected_or_accepted',
    ):
        if hasattr(form, field_name):
            setattr(form, field_name, False if field_name.startswith('submitted_to_') or field_name == 'rejected_or_accepted' else None)

    if hasattr(form, 'rec_status'):
        form.rec_status = None

    if hasattr(form, 'certificate_issued'):
        form.certificate_issued = None

    if hasattr(form, 'certificate_received'):
        form.certificate_received = False


def get_assigned_reviewer_ids(form):
    if not form:
        return []
    return [
        reviewer_id for reviewer_id in
        [getattr(form, 'reviewer_name1', None), getattr(form, 'reviewer_name2', None)]
        if reviewer_id
    ]


def get_completed_reviewer_ids(form):
    if not form:
        return []

    assigned_ids = set(get_assigned_reviewer_ids(form))
    completed_ids = []
    for reviewer_id in [getattr(form, 'form_reviewed_by', None), getattr(form, 'form_reviewed_by1', None)]:
        if reviewer_id and reviewer_id in assigned_ids and reviewer_id not in completed_ids:
            completed_ids.append(reviewer_id)
    return completed_ids


def assigned_reviewer_count(form):
    return len(get_assigned_reviewer_ids(form))


def completed_reviewer_count(form):
    return len(get_completed_reviewer_ids(form))


def has_all_required_reviews(form):
    assigned_count = assigned_reviewer_count(form)
    if assigned_count == 0:
        return False
    return completed_reviewer_count(form) >= assigned_count


def is_waiting_for_additional_reviewer(form):
    return assigned_reviewer_count(form) > 1 and completed_reviewer_count(form) < assigned_reviewer_count(form)


app.jinja_env.globals['assigned_reviewer_count'] = assigned_reviewer_count
app.jinja_env.globals['completed_reviewer_count'] = completed_reviewer_count
app.jinja_env.globals['has_all_required_reviews'] = has_all_required_reviews
app.jinja_env.globals['is_waiting_for_additional_reviewer'] = is_waiting_for_additional_reviewer
app.jinja_env.globals['is_student_form_locked'] = is_student_form_locked
app.jinja_env.globals['is_student_correction_state'] = is_student_correction_state
app.jinja_env.globals['get_student_submission_timestamp'] = get_student_submission_timestamp
app.jinja_env.globals['get_student_dashboard_status'] = get_student_dashboard_status
app.jinja_env.globals['has_reviewer_feedback'] = has_reviewer_feedback


def can_access_form(user, form):
    """Object-level access for student forms and their uploaded documents."""
    if not user or not form:
        return False

    current_role = str(role_value(user) or '').upper()
    if current_role in {'ADMIN', 'SUPER_ADMIN', 'DEAN'}:
        return True

    if getattr(form, 'user_id', None) == user.user_id:
        return True

    form_owner = db_session.query(User).filter_by(user_id=getattr(form, 'user_id', None)).first()
    if form_owner and getattr(form_owner, 'supervisor_id', None) == user.user_id:
        return True

    if getattr(form, 'supervisor_email', None) and getattr(form, 'supervisor_email', None) == user.email:
        return True
    if getattr(form, 'supervisor_name', None) and current_role == 'SUPERVISOR' and getattr(form_owner, 'supervisor_id', None) == user.user_id:
        return True

    if getattr(form, 'reviewer_name1', None) == user.user_id:
        return True
    if getattr(form, 'reviewer_name2', None) == user.user_id:
        return True

    if current_role == 'REC' and getattr(form, 'submitted_to_rec', False):
        return True

    return False


def can_access_requirements(user, req):
    """Access control for FormARequirements documents shared by dashboards."""
    if not user or not req:
        return False

    current_role = str(role_value(user) or '').upper()
    if current_role in {'ADMIN', 'SUPER_ADMIN', 'DEAN'}:
        return True

    if getattr(req, 'user_id', None) == user.user_id:
        return True

    student = db_session.query(User).filter_by(user_id=getattr(req, 'user_id', None)).first()
    if student and getattr(student, 'supervisor_id', None) == user.user_id:
        return True

    for model in (FormA, FormB, FormC):
        form = _find_latest_form_for_user(model, getattr(req, 'user_id', None))
        if form and can_access_form(user, form):
            return True

    return False


FORM_FILE_FIELDS = {
    'A': {
        'private_permission_file', 'proposal_path', 'proposal', 'permission_letter',
        'prior_clearance', 'ethics_evidence', 'pending_note'
    },
    'FORMA': {
        'private_permission_file', 'proposal_path', 'proposal', 'permission_letter',
        'prior_clearance', 'ethics_evidence', 'pending_note'
    },
    'B': {
        'permission_letter', 'prior_clearance', 'ethics_evidence', 'proposal_path',
        'pending_note', 'private_permission_file', 'private_permission', 'pdf_file_path',
    },
    'FORMB': {
        'permission_letter', 'prior_clearance', 'ethics_evidence', 'proposal_path',
        'pending_note', 'private_permission_file', 'private_permission', 'pdf_file_path',
    },
    'C': {'files', 'proposal_path', 'pending_note'},
    'FORMC': {'files', 'proposal_path', 'pending_note'},
}


REQUIREMENT_FILE_FIELDS = {
    'proposal_path', 'proposal', 'permission_letter', 'ethics_evidence',
    'ethics_evidence_path', 'prior_clearance_path', 'prior_clearance',
    'prior_clearance1', 'need_jbs_clearance', 'need_jbs_clearance1',
    'research_tools_path', 'impact_assessment_path', 'participation_info_sheet',
    'pending_note', 'needs_permission_pending', 'files'
}


@app.after_request
def add_no_cache_headers(response):
    """Prevent browsers from reusing cached auth pages after logout/history navigation."""
    if request.endpoint != 'static' and (
        request.endpoint in {'login_page', 'logout'} or session.get('id')
    ):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    response.headers.setdefault(
        'Content-Security-Policy-Report-Only',
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https://cdnjs.cloudflare.com; "
        "connect-src 'self'; "
        "frame-ancestors 'self';"
    )
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response

# =====================================================================================================
# HELPER FUNCTION: Safe FormB Query (avoids binary column deserialization issues)
# =====================================================================================================
def safe_query_formb(query_builder):
    """
    Safely query FormB without triggering binary column deserialization errors.
    Converts query results to proxy objects with only necessary attributes.
    
    Args:
        query_builder: A callable that takes FormB and returns a query 
                      (e.g., lambda fb: db_session.query(fb).filter(...))
    Returns:
        List of FormBProxy objects with safe attributes
    """
    # Define only the columns we need (excluding problematic LargeBinary columns)
    safe_columns = [
        FormB.form_id,
        FormB.user_id,
        FormB.applicant_name,
        FormB.student_number,
        FormB.email,
        FormB.supervisor,
        FormB.supervisor_email,
        FormB.submitted_at,
        FormB.recommendation,
        FormB.supervisor_date,
        FormB.ethics_status,
        FormB.signature_date,
        FormB.review_supervisor_signature,
        FormB.review_date,
        FormB.review_supervisor_signature1,
        FormB.review_date1,
        FormB.created_at,
        FormB.declaration_date
    ]
    
    # Build the query with safe columns
    query = db_session.query(*safe_columns)
    
    # Apply the additional filters/ordering from the query_builder if provided
    if query_builder:
        # Get the original query to extract filters/ordering
        original_query = query_builder(FormB)
        # Copy statement attributes (whereami, order_by, etc.)
        if hasattr(original_query, 'statement'):
            stmt = original_query.statement
            if hasattr(stmt, '_where_criteria') and stmt._where_criteria:
                for criterion in stmt._where_criteria:
                    query = query.filter(criterion)
            if hasattr(stmt, '_order_by') and stmt._order_by:
                query = query.order_by(*stmt._order_by)
    
    results = query.all()
    
    # Convert tuples to proxy objects
    form_b_records = []
    for result in results:
        class FormBProxy:
            pass
        proxy = FormBProxy()
        proxy.form_id = result.form_id
        proxy.user_id = result.user_id
        proxy.applicant_name = result.applicant_name
        proxy.student_number = result.student_number
        proxy.email = result.email
        proxy.supervisor = result.supervisor
        proxy.supervisor_email = result.supervisor_email
        proxy.submitted_at = result.submitted_at
        proxy.recommendation = result.recommendation
        proxy.supervisor_date = result.supervisor_date
        proxy.ethics_status = result.ethics_status
        proxy.signature_date = result.signature_date
        proxy.review_supervisor_signature = result.review_supervisor_signature
        proxy.review_date = result.review_date
        proxy.review_supervisor_signature1 = result.review_supervisor_signature1
        proxy.review_date1 = result.review_date1
        proxy.created_at = result.created_at
        proxy.declaration_date = result.declaration_date
        form_b_records.append(proxy)
    
    return form_b_records

