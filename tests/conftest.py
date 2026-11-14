"""pytest plumbing.

Tests marked `live` talk to the real Supabase project, a real LLM, or a real browser and server. They are skipped
unless you opt in:

    RUN_LIVE_TESTS=1 python -m pytest tests -m live

The default run (`python -m pytest tests`, also what CI runs) is fully offline.
"""
import os, sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LIVE_FILES = ['test_ai_governance.py', 'test_api_real.py', 'test_browser_e2e.py']
LIVE_ENABLED = os.getenv('RUN_LIVE_TESTS', '').strip() == '1'

# Live files import fastapi/playwright/dotenv at module level, so when live tests are off we do not even import them.
collect_ignore = [] if LIVE_ENABLED else list(LIVE_FILES)


def pytest_configure(config):
    config.addinivalue_line('markers', 'live: needs real services (Supabase, LLM key, browser); run with RUN_LIVE_TESTS=1')


def pytest_collection_modifyitems(config, items):
    if LIVE_ENABLED:
        return
    skip = pytest.mark.skip(reason='live test: set RUN_LIVE_TESTS=1 to run')
    for item in items:
        if 'live' in item.keywords:
            item.add_marker(skip)
