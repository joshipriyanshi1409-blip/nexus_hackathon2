"""Optional Demo Company Seeder for ECHO.
Seeds a complete demo brand with users across all four roles,
guidelines, workflow posts, customer feedback, and file vault folders.
Clearly labelled as [SAMPLE DATA] throughout.
Usage: python -m backend.seed_demo
"""
import os, sys, uuid, secrets
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT))

from supabase import create_client
from backend.app import logic as L

DEMO_TAG = "[SAMPLE DATA]"
# Demo passwords are random per run (printed once at the end). Set DEMO_PASSWORD to choose your own for all demo users.
_FIXED = os.getenv('DEMO_PASSWORD', '').strip()
DEMO_PASSWORDS = {u: (_FIXED or secrets.token_urlsafe(12)) for u in ('sarah_head', 'marcus_sup', 'elena_creator')}
CREATED_USERS = set()

def seed():
    print(f"\n=== Seeding Demo Company {DEMO_TAG} ===")
    if os.getenv('APP_ENV', '').strip().lower() == 'production' and os.getenv('ALLOW_DEMO_SEED', '') != '1':
        sys.exit("Refusing to seed demo accounts when APP_ENV=production (set ALLOW_DEMO_SEED=1 to override).")
    url = os.getenv('SUPABASE_URL', '').strip()
    key = os.getenv('SUPABASE_SERVICE_KEY', '').strip()
    sb = create_client(url, key)

    # 1. Ensure CEO profile exists
    ceo_u = os.getenv('ADMIN_USERNAME', 'itz_ceo').strip().lower()
    ceo_rows = sb.table('profiles').select('id').eq('username', ceo_u).execute().data
    if not ceo_rows:
        sys.exit(f"Run 'python -m backend.create_ceo' first before seeding demo company.")
    ceo_id = ceo_rows[0]['id']

    # 2. Seed Demo Rules
    demo_rules = {
        'avoid': ['cheap', 'guys', 'second-rate', 'budget'],
        'prefer': [['customers', 'members'], ['clients', 'members']],
        'proof': ['#1', 'best', 'guaranteed', '100%', 'lifetime warranty'],
        'target': {'Reliable': 9, 'Friendly': 8, 'Fast': 8},
        'departments': ['Marketing', 'Product', 'Support', 'Legal', 'General']
    }
    sb.table('brand_rules').upsert({'id': 1, 'rules': demo_rules}).execute()
    print("  [OK] Brand rules seeded.")

    # 3. Seed Demo Users in all 4 roles
    demo_users = [
        {'u': 'sarah_head', 'n': 'Sarah Jenkins (Head)', 'role': 1, 'by': ceo_id, 'pow': ['review', 'approve', 'files', 'voice', 'authority'], 'dept': 'Marketing'},
        {'u': 'marcus_sup', 'n': 'Marcus Vance (Supervisor)', 'role': 2, 'by': None, 'pow': ['review', 'authority'], 'dept': 'Marketing'},
        {'u': 'elena_creator', 'n': 'Elena Rostova (Creator)', 'role': 3, 'by': None, 'pow': [], 'dept': 'Marketing'}
    ]

    id_map = {ceo_u: ceo_id}
    for uinfo in demo_users:
        u = uinfo['u']
        existing = sb.table('profiles').select('id').eq('username', u).execute().data
        if existing:
            id_map[u] = existing[0]['id']
            print(f"  [EXISTS] User @{u}")
            continue

        pwd = DEMO_PASSWORDS[u]
        parent_id = id_map.get('sarah_head') if u in ('marcus_sup', 'elena_creator') else ceo_id
        try:
            au = sb.auth.admin.create_user({
                'email': f'{u}@brandhub.local',
                'password': pwd,
                'email_confirm': True
            }).user
        except Exception:
            # Check existing auth user
            au, page = None, 1
            while au is None:
                batch = sb.auth.admin.list_users(page=page, per_page=200)
                if not batch:
                    break
                au = next((usr for usr in batch if usr.email == f'{u}@brandhub.local'), None)
                page += 1

        if au:
            id_map[u] = au.id
            sb.table('profiles').upsert({
                'id': au.id,
                'username': u,
                'name': uinfo['n'],
                'role': uinfo['role'],
                'powers': uinfo['pow'],
                'department': uinfo['dept'],
                'created_by': parent_id
            }).execute()
            CREATED_USERS.add(u)
            print(f"  [CREATED] User @{u}")

    # 4. Seed Brand Knowledge Base Sources
    sources = [
        {
            'kind': 'guidelines',
            'title': f'{DEMO_TAG} Brand Voice & Identity Guidelines',
            'content': 'We speak with warmth, clarity, and authority. Always refer to clients as community members. Words to avoid: cheap, budget, second-rate. Ensure all communications convey dependable craftsmanship.'
        },
        {
            'kind': 'facts',
            'title': f'{DEMO_TAG} Product SLA & Warranty Facts',
            'content': 'Our cloud uptime guarantee is 99.9%. Hardware carries a 1-year limited warranty. Refund requests are processed within 48 business hours. Never promise 100% bug-free or lifetime coverage.'
        },
        {
            'kind': 'terminology',
            'title': f'{DEMO_TAG} Approved Product Terminology',
            'content': 'Preferred terms: Use "BrandHub Studio" instead of "the tool". Use "Workspace" instead of "folder area". Claims like #1 or best-in-class require signed external benchmark audit reports.'
        }
    ]

    for s in sources:
        existing = sb.table('brand_sources').select('id').eq('title', s['title']).execute().data
        if not existing:
            sb.table('brand_sources').insert({
                'kind': s['kind'],
                'title': s['title'],
                'content': s['content'],
                'uploaded_by': ceo_id
            }).execute()
    print("  [OK] Brand knowledge base sources seeded.")

    # 5. Seed Workflow Posts
    elena_id = id_map.get('elena_creator', ceo_id)
    posts = [
        {
            'text': f'{DEMO_TAG} Welcome our new members to the annual leadership forum! Join us for insights and collaboration.',
            'status': 'Approved',
            'issues': 0,
            'note': 'Approved for general release.'
        },
        {
            'text': f'{DEMO_TAG} Discover how our members streamline workflows with our #1 guaranteed software suite.',
            'status': 'Recommended',
            'issues': 2,
            'note': 'Recommended by supervisor; please review claim evidence before sign-off.'
        },
        {
            'text': f'{DEMO_TAG} Get the cheapest subscription deal for your team today! Guaranteed best value for money.',
            'status': 'Sent back',
            'issues': 3,
            'note': 'Sent back: Violates avoid word ("cheap") and unproven superlative claim ("best value").'
        },
        {
            'text': f'{DEMO_TAG} Our upcoming feature release introduces streamlined member onboarding and instant dashboard exports.',
            'status': 'Waiting',
            'issues': 0,
            'note': ''
        }
    ]

    for p in posts:
        # Check if already seeded
        chk = sb.table('posts').select('id').eq('text', p['text']).execute().data
        if not chk:
            res = sb.table('posts').insert({
                'author_id': elena_id,
                'text': p['text'],
                'issues': p['issues'],
                'status': p['status'],
                'note': p['note']
            }).execute().data[0]
            sb.table('post_events').insert({
                'post_id': res['id'],
                'actor_id': elena_id,
                'action': p['status'],
                'note': p['note']
            }).execute()
    print("  [OK] Sample workflow posts across all approval stages seeded.")

    # 6. Seed Sample Customer Feedback
    feedback = [
        {'source': 'Website', 'text': f'{DEMO_TAG} The platform onboarding is very fast and helpful.', 'rating': 5, 'sentiment': 'positive', 'topic': 'support'},
        {'source': 'Google Play', 'text': f'{DEMO_TAG} Excellent customer service team, always friendly.', 'rating': 5, 'sentiment': 'positive', 'topic': 'support'},
        {'source': 'Email', 'text': f'{DEMO_TAG} Refund processing was delayed by two days, but eventually resolved.', 'rating': 2, 'sentiment': 'negative', 'topic': 'refunds'},
        {'source': 'Website', 'text': f'{DEMO_TAG} Very reliable uptime and high performance throughout the month.', 'rating': 5, 'sentiment': 'positive', 'topic': 'product quality'},
        {'source': 'Support Ticket', 'text': f'{DEMO_TAG} Subscription pricing feels slightly expensive for small teams.', 'rating': 3, 'sentiment': 'neutral', 'topic': 'pricing'}
    ]

    for fb_item in feedback:
        chk = sb.table('feedback').select('id').eq('text', fb_item['text']).execute().data
        if not chk:
            sb.table('feedback').insert(fb_item).execute()
    print("  [OK] Customer voice feedback samples seeded.")

    # 7. Seed Sample Folder
    chk_f = sb.table('folders').select('id').eq('name', f'{DEMO_TAG} Brand Guidelines 2026').execute().data
    if not chk_f:
        sb.table('folders').insert({
            'name': f'{DEMO_TAG} Brand Guidelines 2026',
            'created_by': ceo_id
        }).execute()
    print("  [OK] File vault demo folders seeded.")

    print(f"\n=== Demo Company Seeding Finished Successfully! ===")
    print("\nDemo Logins:")
    print(f"  - CEO:         {ceo_u} / [password from .env]")
    for u, label in (('sarah_head', 'Head'), ('marcus_sup', 'Supervisor'), ('elena_creator', 'Creator')):
        pw = DEMO_PASSWORDS[u] if u in CREATED_USERS else '(already existed - password unchanged)'
        print(f"  - {label + ':':<12} {u} / {pw}")
    print("\nThese passwords are shown only now. Do not use demo accounts in a real deployment.")

if __name__ == '__main__':
    seed()
