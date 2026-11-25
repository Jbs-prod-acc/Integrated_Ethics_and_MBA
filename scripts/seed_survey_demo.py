"""Seed an isolated local database with accounts for Survey Builder testing."""

from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Base, FormB, User, UserRole, db_session, engine


PASSWORD = "TestSurvey123!"


def create_user(name, email, student_number=None, role=UserRole.STUDENT):
    user = db_session.query(User).filter_by(email=email).first()
    if user is None:
        user = User(
            full_name=name,
            email=email,
            student_number=student_number,
            password=PASSWORD,
            role=role,
        )
        user.authenticate_student = "true"
        user.authenticated_student = role == UserRole.STUDENT
        db_session.add(user)
        db_session.flush()
    return user


def main():
    Base.metadata.create_all(engine)
    admin = create_user("Survey Test Admin", "survey.admin@uj.test", role=UserRole.SUPER_ADMIN)
    all_students = create_user("Amina All Students", "amina.all@uj.test", 300100001)
    certificate = create_user("Bongani Certificate", "bongani.certificate@uj.test", 300100002)
    delayed = create_user("Chipo Delayed", "chipo.delayed@uj.test", 300100003)
    selected = create_user("Dineo Selected", "dineo.selected@uj.test", 300100004)

    if not db_session.query(FormB).filter_by(user_id=certificate.user_id).first():
        db_session.add(FormB(
            user_id=certificate.user_id, applicant_name=certificate.full_name,
            submitted_at=datetime.utcnow() - timedelta(days=45),
            certificate_issued=datetime.utcnow() - timedelta(days=10),
            certificate_received=True,
        ))
    if not db_session.query(FormB).filter_by(user_id=delayed.user_id).first():
        db_session.add(FormB(
            user_id=delayed.user_id, applicant_name=delayed.full_name,
            submitted_at=datetime.utcnow() - timedelta(days=45),
            certificate_received=False,
        ))
    db_session.commit()
    print("Survey demo users created. Password for every account: TestSurvey123!")
    print("Admin: survey.admin@uj.test")
    print("All students: amina.all@uj.test")
    print("Certificate recipient: bongani.certificate@uj.test")
    print("Delayed application: chipo.delayed@uj.test")
    print("Selected-student test: dineo.selected@uj.test")


if __name__ == "__main__":
    main()
