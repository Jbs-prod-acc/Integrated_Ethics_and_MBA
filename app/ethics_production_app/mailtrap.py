from threading import Thread
from dotenv import load_dotenv
from flask_mail import Mail, Message
from flask import current_app
import os


load_dotenv()

mail = Mail()
# Looking to send emails in production? Check out our Email API/SMTP product!
def configure_mail(app):
    app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER")
    app.config['MAIL_PORT'] = int(os.getenv("MAIL_PORT", "587"))
    app.config['MAIL_DEFAULT_SENDER'] = 'noreply@example.com'
    app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
    app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USE_SSL'] = False
    mail.init_app(app)


def _send_email_sync(flask_app, message, recipients):
    with flask_app.app_context():
        try:
            msg = Message(
                subject='ETHICS NOTIFICATION',
                recipients=recipients,
                body=message
            )
            mail.send(msg)
        except Exception:
            # Exceptions raised in this worker cannot be caught by the route that
            # started it. Log them here without breaking a successful submission.
            current_app.logger.exception(
                "Unable to send ethics notification email to %s", recipients
            )


def send_email(app, mail, message, recipient):
    recipients = [address for address in (recipient or []) if address]
    if not recipients:
        app.logger.warning("Ethics notification skipped: no recipients supplied")
        return False

    if not app.config.get('MAIL_SERVER'):
        app.logger.warning(
            "Ethics notification skipped: MAIL_SERVER is not configured"
        )
        return False

    # Email delivery should not block the request/response cycle for form submission.
    worker = Thread(
        target=_send_email_sync,
        args=(app, message, recipients),
        daemon=True
    )
    worker.start()
    return True
    
