import secrets
import os
import smtplib
import re
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

def generate_reset_token():
    return secrets.token_urlsafe(32)

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

def send_email(to_address, subject, body):
    msg = EmailMessage()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.set_content(body)
    html_content = f"""\
    <html>
    <body>
        <h1>Hello!</h1>

        <p>Here is your password reset token:</p>
        <h3><b>{body}</b></h3>
        <p>Please note it wil expire in 15 minutes.</p>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype='html')

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)
        print("Email sent!")

# send_email("motsie.atg@gmail.com", "UJ Ethics System: Password Resset", "96345")



def validate_password(password):
    if len(password) < 6:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"
    
    return True, "Password is valid,must be at least length of 6 charecters,special charecter, and a number"