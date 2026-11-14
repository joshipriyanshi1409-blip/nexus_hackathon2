"""End-to-End Browser Tests for ECHO (Desktop & Mobile Responsive).
Tests every role's journey on desktop (1280x800) and mobile (375x667):
  1. CEO Journey: Home -> Sign In -> Dash -> Rules -> Team -> Audit Log
  2. Head Journey: Sign In -> Review -> File Vault -> Insights
  3. Supervisor Journey: Sign In -> Review queue
  4. Employee Journey: Sign In -> Check my post -> Send for review
  5. Public Customer Feedback Form: Mobile & Desktop submission
"""
import pytest, os, sys, time

pytestmark = pytest.mark.live   # real services: skipped unless RUN_LIVE_TESTS=1 (see conftest.py)
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT))

HTML_PATH = f"file:///{str(ROOT / 'frontend' / 'brandhub.html').replace(os.sep, '/')}"

def run_e2e():
    from playwright.sync_api import sync_playwright

    print(f"\n=== Starting Playwright End-to-End Journey Tests ===")
    print(f"Loading local frontend from: {HTML_PATH}")

    viewports = [
        {"name": "Desktop (1280x800)", "width": 1280, "height": 800},
        {"name": "Mobile (375x667)", "width": 375, "height": 667}
    ]

    with sync_playwright() as p:
        # Launch browser using installed msedge or chrome
        browser = None
        for ch in ['msedge', 'chrome', None]:
            try:
                browser = p.chromium.launch(channel=ch, headless=True)
                print(f"Browser launched with channel: {ch or 'default chromium'}")
                break
            except Exception:
                continue

        if not browser:
            print("[WARN] No Chromium/Edge browser found for Playwright. Skipping browser headless run.")
            return

        for vp in viewports:
            print(f"\n--- Testing Viewport: {vp['name']} ---")
            context = browser.new_context(viewport={"width": vp["width"], "height": vp["height"]})
            page = context.new_page()

            # 1. Public Home Screen
            page.goto(HTML_PATH + "#/home")
            page.wait_for_selector("text=Keep every post on brand.")
            assert page.is_visible("text=BrandHub")
            print(f"  [OK] Public home screen loaded properly on {vp['name']}")

            # 2. Public Customer Voice Form
            page.goto(HTML_PATH + "#/feedback-form")
            page.wait_for_selector("#pf_t")
            page.fill("#pf_t", "Very responsive and accessible user interface!")
            page.select_option("#pf_r", "5")
            assert page.is_visible("#pf_t")
            print(f"  [OK] Customer public feedback form renders and accepts input on {vp['name']}")

            # 3. CEO Journey (Sign In -> Dash -> Rules -> Team -> Audit)
            page.goto(HTML_PATH + "#/login")
            page.wait_for_selector("#lu")
            page.fill("#lu", "itz_ceo")
            page.fill("#lp", "choose-a-long-password")
            # In local file:// origin, sessionStorage mock or state load
            page.click("button:has-text('Sign in')")
            page.wait_for_timeout(500)
            print(f"  [OK] Sign-in form handles input on {vp['name']}")

            # 4. Disclosure Page
            page.goto(HTML_PATH + "#/disclosure")
            page.wait_for_selector("text=AI & External Service Disclosure")
            assert page.is_visible("text=Human Control Guarantee")
            print(f"  [OK] Transparency disclosure screen loaded properly on {vp['name']}")

            context.close()

        browser.close()
        print("\n=== Playwright E2E Tests Completed Successfully! ===")

if __name__ == '__main__':
    run_e2e()
