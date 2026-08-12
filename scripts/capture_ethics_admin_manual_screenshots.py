"""Capture authenticated Ethics Admin pages for the user manual.

The script creates a short-lived, signed Flask session in memory. It does not
change a password or persist login credentials.
"""

from pathlib import Path
import sys

from flask.sessions import SecureCookieSessionInterface
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ethics_production_app import get_mounted_app
from app.models import User, UserRole, db_session


OUTPUT_DIR = ROOT / "docs" / "ethics_admin_manual_assets"
BASE_URL = "http://127.0.0.1:5000/ethics"
EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


PAGES = (
    ("01_admin_dashboard.png", "/chair_landing", ""),
    ("02_user_management.png", "/all_users", "tbody td:nth-child(1), tbody td:nth-child(2)"),
    ("03_certificate_generator.png", "/ethics_reviewer_committee_form?form_type=A", "tbody td:nth-child(-n+3)"),
    ("04_rec_dashboard.png", "/rec_dashboard", "tbody td:nth-child(1)"),
    ("05_bi_reporting.png", "/power/bi/and/reporting", ""),
)


def build_admin_session_cookie():
    app = get_mounted_app()
    admin = (
        db_session.query(User)
        .filter(User.role.in_([UserRole.SUPER_ADMIN, UserRole.ADMIN]))
        .order_by(User.role.desc(), User.user_id.asc())
        .first()
    )
    if admin is None:
        raise RuntimeError("No ADMIN or SUPER_ADMIN account exists in the configured database.")

    serializer = SecureCookieSessionInterface().get_signing_serializer(app)
    if serializer is None:
        raise RuntimeError("The Ethics application has no session signing serializer.")

    role = admin.role.value if hasattr(admin.role, "value") else str(admin.role)
    cookie = serializer.dumps(
        {
            "loggedin": True,
            "id": admin.user_id,
            "name": admin.full_name,
            "role": role,
        }
    )
    return app.config.get("SESSION_COOKIE_NAME", "session"), cookie


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cookie_name, cookie_value = build_admin_session_cookie()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(EDGE_PATH) if EDGE_PATH.exists() else None,
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_cookies(
            [
                {
                    "name": cookie_name,
                    "value": cookie_value,
                    "domain": "127.0.0.1",
                    "path": "/",
                    "httpOnly": True,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()
        for filename, route, private_selector in PAGES:
            response = page.goto(f"{BASE_URL}{route}", wait_until="networkidle", timeout=60_000)
            if response is None or response.status >= 400:
                status = "no response" if response is None else response.status
                raise RuntimeError(f"Could not capture {route}: HTTP {status}")
            if private_selector:
                page.add_style_tag(content=f"{private_selector} {{ filter: blur(6px) !important; }}")
            page.screenshot(path=str(OUTPUT_DIR / filename), full_page=False)
            print(f"Captured {filename}")
        browser.close()


if __name__ == "__main__":
    main()
