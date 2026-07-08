import json
from app.models import db_session, UserActivityLog
from flask import request, session
from datetime import datetime

def log_user_activity(action, page=None, target_user_id=None, details=None, duration_seconds=None):
    user_id = session.get('id')
    if not user_id:
        return  # Not logged in
    try:
        serialized_details = details
        if isinstance(details, (dict, list, tuple)):
            serialized_details = json.dumps(details, default=str)
        elif details is not None:
            serialized_details = str(details)

        log = UserActivityLog(
            user_id=user_id,
            action=action,
            page=page,
            target_user_id=target_user_id,
            timestamp=datetime.utcnow(),
            user_agent=request.user_agent.string,
            details=serialized_details,
            duration_seconds=duration_seconds
        )
        db_session.add(log)
        db_session.commit()
    except Exception:
        try:
            db_session.rollback()
        except Exception:
            pass
