import enum
import re
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

UJ_STUDENT_EMAIL_RE = re.compile(r"^(?P<number>\d+)@student\.uj\.ac\.za$", re.IGNORECASE)


class MbaRole(enum.Enum):
    MAIN_ADMIN = "main_admin"
    ADMIN = "admin"
    SCHOLAR = "scholar"
    STUDENT = "student"
    EXAMINER = "examiner"
    HDC = "hdc"


class MbaScholarRole(enum.Enum):
    EXAMINER = "examiner"
    SUPERVISOR = "supervisor"
    BOTH = "both"


class EthicsRole(enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    REVIEWER = "reviewer"
    SUPERVISOR = "supervisor"
    STUDENT = "student"
    REC = "rec"
    DEAN = "dean"


class EthicsFormType(enum.Enum):
    FORM_A = "A"
    FORM_B = "B"
    FORM_C = "C"


class EthicsSubmissionStatus(enum.Enum):
    DRAFT = "draft"
    AWAITING_SUPERVISOR = "awaiting_supervisor"
    SENT_BACK_BY_SUPERVISOR = "sent_back_by_supervisor"
    AWAITING_ADMIN = "awaiting_admin"
    AWAITING_REVIEWERS = "awaiting_reviewers"
    REVIEW_IN_PROGRESS = "review_in_progress"
    SENT_BACK_BY_REVIEWER = "sent_back_by_reviewer"
    AWAITING_REC = "awaiting_rec"
    APPROVED = "approved"
    APPROVED_WITH_MINOR_CHANGES = "approved_with_minor_changes"
    RESUBMISSION_REQUIRED = "resubmission_required"
    REJECTED = "rejected"
    CERTIFICATE_ISSUED = "certificate_issued"


class ProjectStatus(enum.Enum):
    CREATED = "created"
    ADMIN_SUBMITTED = "admin_submitted"
    ADMIN_APPROVED = "admin_approved"
    ADMIN_DECLINED = "admin_declined"
    HDC_VERIFIED = "hdc_verified"
    HDC_DECLINED = "hdc_declined"
    GRADUATED = "graduated"


def normalize_email(email):
    return (email or "").strip().lower()


def student_email_for(student_number):
    clean_number = re.sub(r"\D", "", student_number or "")
    return f"{clean_number}@student.uj.ac.za"


def is_uj_student_email(email):
    return bool(UJ_STUDENT_EMAIL_RE.match(normalize_email(email)))


class UserAuthMixin(UserMixin):
    system_name = None

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    microsoft_subject = db.Column(db.String(255), nullable=True, unique=True)
    first_name = db.Column(db.String(120), nullable=True)
    last_name = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_id(self):
        return f"{self.system_name}:{self.id}"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    @classmethod
    def find_by_email(cls, email):
        return cls.query.filter(db.func.lower(cls.email) == normalize_email(email)).first()


class MbaUser(UserAuthMixin, db.Model):
    __tablename__ = "mba_users"
    __table_args__ = (
        CheckConstraint("role in ('main_admin','admin','scholar','student','examiner','hdc')", name="mba_user_role_check"),
        CheckConstraint("scholar_role is null or scholar_role in ('examiner','supervisor','both')", name="mba_scholar_role_check"),
    )

    system_name = "mba"
    role = db.Column(db.String(40), nullable=False, default=MbaRole.STUDENT.value)
    scholar_role = db.Column(db.String(40), nullable=True)
    has_profile = db.Column(db.Boolean, nullable=False, default=False)
    has_signature = db.Column(db.Boolean, nullable=False, default=False)
    has_cv = db.Column(db.Boolean, nullable=False, default=False)

    def is_admin_role(self):
        return self.role in {MbaRole.MAIN_ADMIN.value, MbaRole.ADMIN.value}

    def is_student_role(self):
        return self.role == MbaRole.STUDENT.value

    def is_supervisor_role(self):
        return self.scholar_role in {MbaScholarRole.SUPERVISOR.value, MbaScholarRole.BOTH.value}

    def is_examiner_role(self):
        return self.role == MbaRole.EXAMINER.value or self.scholar_role in {
            MbaScholarRole.EXAMINER.value,
            MbaScholarRole.BOTH.value,
        }


class EthicsUser(UserAuthMixin, db.Model):
    __tablename__ = "ethcis_users"
    __table_args__ = (
        CheckConstraint(
            "role in ('super_admin','admin','reviewer','supervisor','student','rec','dean')",
            name="ethcis_user_role_check",
        ),
    )

    system_name = "ethics"
    role = db.Column(db.String(40), nullable=False, default=EthicsRole.STUDENT.value)
    student_number = db.Column(db.String(40), nullable=True, index=True)
    supervisor_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=True)
    supervisor = db.relationship("EthicsUser", remote_side="EthicsUser.id", foreign_keys=[supervisor_id])
    staff_number = db.Column(db.String(80), nullable=True)
    specialisation = db.Column(db.String(180), nullable=True)
    authenticated_student = db.Column(db.Boolean, nullable=False, default=False)
    watched_demo = db.Column(db.Boolean, nullable=False, default=False)

    def is_admin_role(self):
        return self.role in {EthicsRole.SUPER_ADMIN.value, EthicsRole.ADMIN.value}

    def is_committee_role(self):
        return self.role in {EthicsRole.REC.value, EthicsRole.DEAN.value}


class MbaStudentProfile(db.Model):
    __tablename__ = "mba_student_profiles"
    __table_args__ = (UniqueConstraint("student_number", name="uq_mba_student_number"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("mba_users.id"), nullable=False, unique=True)
    user = db.relationship("MbaUser", backref=db.backref("student_profile", uselist=False))
    name = db.Column(db.String(120))
    surname = db.Column(db.String(120))
    title = db.Column(db.String(40))
    contact = db.Column(db.String(80))
    student_number = db.Column(db.String(40), nullable=False)
    secondary_email = db.Column(db.String(255))
    module = db.Column(db.String(120))
    block_id = db.Column(db.String(120))
    degree = db.Column(db.String(80), nullable=False, default="MBA")
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class MbaScholarProfile(db.Model):
    __tablename__ = "mba_scholar_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("mba_users.id"), nullable=False, unique=True)
    user = db.relationship("MbaUser", backref=db.backref("scholar_profile", uselist=False))
    name = db.Column(db.String(120))
    surname = db.Column(db.String(120))
    title = db.Column(db.String(40))
    skills = db.Column(db.Text)
    address = db.Column(db.Text)
    department = db.Column(db.String(160))
    position = db.Column(db.String(160))
    contact = db.Column(db.String(80))
    students = db.Column(db.Integer, nullable=False, default=0)
    qualification = db.Column(db.String(180))
    affiliation = db.Column(db.String(180))
    academic_experience = db.Column(db.Integer, nullable=False, default=0)
    approved_before = db.Column(db.Boolean, nullable=False, default=False)
    international_assessor = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class MbaResearchInterest(db.Model):
    __tablename__ = "mba_research_interests"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    created_by = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class MbaProject(db.Model):
    __tablename__ = "mba_projects"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("mba_users.id"), nullable=False)
    student = db.relationship("MbaUser", foreign_keys=[student_id], backref="projects")
    project_title = db.Column(db.String(220), nullable=False)
    project_description = db.Column(db.Text, nullable=False)
    discipline = db.Column(db.Text, nullable=False)
    qualification = db.Column(db.String(120))
    project_status = db.Column(db.String(60), nullable=False, default=ProjectStatus.CREATED.value)
    title_approved = db.Column(db.Boolean, nullable=False, default=False)
    nomination_form_approved = db.Column(db.Boolean, nullable=False, default=False)
    nomination_form_submitted = db.Column(db.Boolean, nullable=False, default=False)
    intent_form_approved = db.Column(db.Boolean, nullable=False, default=False)
    intent_form_submitted = db.Column(db.Boolean, nullable=False, default=False)
    primary_supervisor_id = db.Column(db.Integer, db.ForeignKey("mba_users.id"))
    assessor_1_id = db.Column(db.Integer, db.ForeignKey("mba_users.id"))
    assessor_2_id = db.Column(db.Integer, db.ForeignKey("mba_users.id"))
    assessor_3_id = db.Column(db.Integer, db.ForeignKey("mba_users.id"))
    comments = db.Column(db.Text)
    hdc_comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MbaForm(db.Model):
    __tablename__ = "mba_forms"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("mba_projects.id"), nullable=False)
    project = db.relationship("MbaProject", backref="forms")
    form_type = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    student_signed = db.Column(db.Boolean, nullable=False, default=False)
    supervisor_signed = db.Column(db.Boolean, nullable=False, default=False)
    submitted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class EthicsApplication(db.Model):
    __tablename__ = "ethcis_applications"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=False)
    student = db.relationship("EthicsUser", foreign_keys=[student_id], backref="applications")
    supervisor_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"))
    title = db.Column(db.String(220), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    risk_level = db.Column(db.String(40), nullable=False, default="low")
    status = db.Column(db.String(60), nullable=False, default="draft")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class EthicsReview(db.Model):
    __tablename__ = "ethcis_reviews"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("ethcis_applications.id"), nullable=False)
    application = db.relationship("EthicsApplication", backref="reviews")
    reviewer_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=False)
    reviewer = db.relationship("EthicsUser", backref="reviews")
    recommendation = db.Column(db.String(80), nullable=False)
    comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class EthicsFormRequirement(db.Model):
    __tablename__ = "ethcis_form_requirements"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=False)
    student = db.relationship("EthicsUser", backref="form_requirements", foreign_keys=[student_id])
    form_type = db.Column(db.String(1), nullable=False)
    needs_permission = db.Column(db.Boolean, nullable=False, default=False)
    has_clearance = db.Column(db.Boolean, nullable=False, default=False)
    company_requires_jbs = db.Column(db.Boolean, nullable=False, default=False)
    has_ethics_evidence = db.Column(db.Boolean, nullable=False, default=False)
    proposal_filename = db.Column(db.String(255), nullable=True)
    permission_letter_filename = db.Column(db.String(255), nullable=True)
    research_tools_filename = db.Column(db.String(255), nullable=True)
    impact_assessment_filename = db.Column(db.String(255), nullable=True)
    participation_info_filename = db.Column(db.String(255), nullable=True)
    pending_note_filename = db.Column(db.String(255), nullable=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class EthicsFormSubmission(db.Model):
    __tablename__ = "ethcis_form_submissions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=False)
    student = db.relationship("EthicsUser", backref="form_submissions", foreign_keys=[student_id])
    supervisor_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=True)
    supervisor = db.relationship("EthicsUser", foreign_keys=[supervisor_id])
    requirement_id = db.Column(db.Integer, db.ForeignKey("ethcis_form_requirements.id"), nullable=True)
    requirement = db.relationship("EthicsFormRequirement", backref="submissions")
    form_type = db.Column(db.String(1), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    department = db.Column(db.String(160), nullable=True)
    degree = db.Column(db.String(120), nullable=True)
    risk_level = db.Column(db.String(40), nullable=False, default="low")
    status = db.Column(db.String(80), nullable=False, default=EthicsSubmissionStatus.DRAFT.value, index=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    submitted_at = db.Column(db.DateTime, nullable=True)
    supervisor_decision = db.Column(db.String(80), nullable=True)
    supervisor_comments = db.Column(db.Text, nullable=True)
    supervisor_reviewed_at = db.Column(db.DateTime, nullable=True)
    submitted_to_admin = db.Column(db.Boolean, nullable=False, default=False)
    submitted_to_reviewers = db.Column(db.Boolean, nullable=False, default=False)
    submitted_to_rec = db.Column(db.Boolean, nullable=False, default=False)
    rec_status = db.Column(db.String(80), nullable=True)
    rec_comments = db.Column(db.Text, nullable=True)
    rec_decided_at = db.Column(db.DateTime, nullable=True)
    certificate_code = db.Column(db.String(120), nullable=True)
    certificate_issued_at = db.Column(db.DateTime, nullable=True)
    certificate_valid_years = db.Column(db.Integer, nullable=True)
    certificate_end_date = db.Column(db.DateTime, nullable=True)
    certificate_issuer = db.Column(db.String(255), nullable=True)
    certificate_heading = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class EthicsFormDraft(db.Model):
    __tablename__ = "ethcis_form_drafts"
    __table_args__ = (UniqueConstraint("student_id", "form_type", name="uq_ethcis_student_form_draft"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=False)
    student = db.relationship("EthicsUser", backref="form_drafts", foreign_keys=[student_id])
    form_type = db.Column(db.String(1), nullable=False)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class EthicsReviewerAssignment(db.Model):
    __tablename__ = "ethcis_reviewer_assignments"
    __table_args__ = (UniqueConstraint("submission_id", "reviewer_id", name="uq_ethcis_submission_reviewer"),)

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("ethcis_form_submissions.id"), nullable=False)
    submission = db.relationship("EthicsFormSubmission", backref="reviewer_assignments")
    reviewer_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=False)
    reviewer = db.relationship(
        "EthicsUser",
        backref="ethics_review_assignments",
        foreign_keys=[reviewer_id],
    )
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=True)
    assigned_by = db.relationship("EthicsUser", foreign_keys=[assigned_by_id])
    recommendation = db.Column(db.String(80), nullable=True)
    comments = db.Column(db.Text, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class EthicsActivityLog(db.Model):
    __tablename__ = "ethcis_activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("ethcis_users.id"), nullable=False)
    user = db.relationship("EthicsUser", backref="activity_logs")
    action = db.Column(db.String(120), nullable=False)
    target_type = db.Column(db.String(80), nullable=True)
    target_id = db.Column(db.String(80), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
