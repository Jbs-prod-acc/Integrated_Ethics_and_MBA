from models import db_session, User, UserRole, FormB, FormC, FormA, FormUploads, Documents

def getFormAData(id):
    db_session.query(FormA).filter_by(id=id).all()

def getSupervisorsList():
    supervisors = db_session.query(User).filter(User.role == UserRole.SUPERVISOR).all()
    
    # Convert to list of dicts
    result = [
        {
            "user_id": sup.user_id,
            "full_name": sup.full_name,
            "email": sup.email
        }
        for sup in supervisors
    ]
    return result