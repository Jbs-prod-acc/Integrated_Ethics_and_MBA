from threading import Thread
from dotenv import load_dotenv
from flask_mail import Mail, Message
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
        msg = Message(
            subject='ETHICS NOTIFICATION',
            recipients=recipients,
            body=message
        )
        mail.send(msg)


def send_email(app, mail, message, recipient):
    # Email delivery should not block the request/response cycle for form submission.
    worker = Thread(
        target=_send_email_sync,
        args=(app, message, recipient),
        daemon=True
    )
    worker.start()
    
