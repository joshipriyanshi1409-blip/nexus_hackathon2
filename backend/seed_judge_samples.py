"""Seed optional synthetic complaints and approved facts for judge demonstrations.
Run after normal setup and CEO creation: python -m backend.seed_judge_samples
This script does not create accounts, alter roles, or assign permissions.
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
from backend.demo_fixtures import COMPLAINTS, APPROVED_FACTS

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

def main():
    from supabase import create_client
    url = os.getenv('SUPABASE_URL', '').strip()
    key = os.getenv('SUPABASE_SERVICE_KEY', '').strip()
    if not url or not key:
        raise SystemExit('Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env first.')
    if os.getenv('APP_ENV', '').strip().lower() == 'production' and os.getenv('ALLOW_DEMO_SEED', '') != '1':
        raise SystemExit('Refusing to seed sample complaints/facts in production. Set ALLOW_DEMO_SEED=1 only for a dedicated judge deployment.')
    sb = create_client(url, key)
    ceo_name = os.getenv('ADMIN_USERNAME', 'itz_ceo').strip().lower()
    profiles = sb.table('profiles').select('id').eq('username', ceo_name).execute().data or []
    if not profiles:
        raise SystemExit('CEO profile not found. Run python -m backend.create_ceo first.')
    ceo_id = profiles[0]['id']

    # Use the production cleaning/deduplication pipeline. Every authorized voice account
    # can inspect these sample rows because demo markers are metadata, not access controls.
    from backend.app.main import save_feedback
    today = datetime.now(timezone.utc).date()
    rows = []
    for idx, (group, source, text, rating, days_ago) in enumerate(COMPLAINTS, start=1):
        rows.append({'source': source, 'text': text, 'rating': rating,
                     'date': (today - timedelta(days=days_ago)).isoformat(),
                     'external_id': f'demo:{group}:{idx:02d}'})
    result = save_feedback(rows, use_llm=False, return_details=True)

    facts = [dict(f, created_by=ceo_id, is_demo=True) for f in APPROVED_FACTS]
    sb.table('approved_facts').upsert(facts, on_conflict='name,is_demo').execute()
    print('Shared judge samples are ready; no account was created or changed.')
    print(f"  Complaints imported: {result['imported']}; duplicates skipped: {result['duplicates']}; PII items masked: {result['pii_redactions']}")
    print(f'  Approved facts upserted: {len(facts)}')
    print('  Any existing account with customer-voice access can inspect them, subject to its normal role permissions.')

if __name__ == '__main__':
    main()
