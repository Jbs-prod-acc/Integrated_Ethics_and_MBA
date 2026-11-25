"""Capture a seeded SQLite student's dashboard and JBS5 form for local E2E verification."""

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "e2e_test_screenshots"
BASE_URL = "http://127.0.0.1:5001"
EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(EDGE_PATH) if EDGE_PATH.exists() else None,
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(f"{BASE_URL}/login?next=/mba/", wait_until="networkidle")
        page.locator("input[name='email']").fill("219001001@student.uj.ac.za")
        page.locator("input[name='password']").fill("E2E-Test-Only-2026!")
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url("**/mba/**")
        page.screenshot(path=str(OUTPUT_DIR / "01_student_dashboard.png"), full_page=True)

        page.goto(f"{BASE_URL}/mba/projects/1/fill-form/jbs5", wait_until="networkidle")
        if "JBS 5" not in page.locator("body").inner_text():
            raise RuntimeError("The JBS5 form did not render.")
        page.screenshot(path=str(OUTPUT_DIR / "02_jbs5_form.png"), full_page=True)
        print("Captured authenticated dashboard and JBS5 form screenshots.")
        browser.close()


if __name__ == "__main__":
    main()
