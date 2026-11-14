"""One-time / idempotent: create the first CEO login.
Run from the project folder: python -m backend.create_ceo
To change the CEO password later (after editing ADMIN_PASSWORD in .env): python -m backend.create_ceo --reset-password
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

# Passwords that appear in the README / .env.example / old demos and must never protect a real account.
PLACEHOLDERS = {'choose-a-long-password', 'changeme', 'change-me', 'password', 'password123', 'admin', 'admin123',
                'your-password', 'your-admin-password', 'democeo2026!'}

def weak_reason(pw: str, username: str):
    if len(pw) < 12:
        return 'must be at least 12 characters'
    if pw.lower() in PLACEHOLDERS or pw.lower().startswith('choose-'):
        return 'is a well-known placeholder'
    if username and username in pw.lower():
        return 'must not contain the username'
    if len(set(pw)) < 5:
        return 'is too repetitive'
    return None

def key_problem(key: str):
    """Explain why a key cannot manage users (the usual cause of 403 errors), or None if it looks right."""
    import base64, json
    if key.startswith('sb_publishable_'):
        return 'this is the PUBLISHABLE key. Use the secret key (sb_secret_...) or the legacy service_role key.'
    if key.count('.') == 2:                                   # legacy JWT keys: anon vs service_role
        try:
            part = key.split('.')[1]
            role = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))).get('role')
            if role and role != 'service_role':
                return f'this is the "{role}" key. Use the "service_role" key (Project Settings -> API Keys -> Legacy).'
        except Exception:
            pass
    return None

def main():
    from supabase import create_client
    u = os.getenv('ADMIN_USERNAME', 'itz_ceo').strip().lower()
    p = os.getenv('ADMIN_PASSWORD', '').strip()
    why = weak_reason(p, u)
    if why:
        sys.exit(f'ADMIN_PASSWORD {why}. Set a strong, unique password in .env first.')

    url = os.environ.get('SUPABASE_URL', '').strip()
    key = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()
    if not (url and key):
        sys.exit('Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env first.')
    bad = key_problem(key)
    if bad:
        sys.exit(f'SUPABASE_SERVICE_KEY is wrong: {bad}')
    sb = create_client(url, key)

    try:
        existing = sb.table('profiles').select('id').eq('username', u).execute().data
    except Exception as e:
        sys.exit(f'Could not read the database ({type(e).__name__}). Did you run the SQL migrations in THIS Supabase project, '
                 'and do SUPABASE_URL and SUPABASE_SERVICE_KEY come from that same project?')
    if existing:
        if '--reset-password' in sys.argv:
            try:
                sb.auth.admin.update_user_by_id(existing[0]['id'], {'password': p})
            except Exception as e:
                sys.exit(f'Supabase refused the password change ({type(e).__name__}). A 403 here means SUPABASE_SERVICE_KEY is not the '
                         'service_role/secret key. Fix it in .env and run again.')
            print(f'Password for "{u}" reset to the ADMIN_PASSWORD currently in .env.')
        else:
            print(f'CEO "{u}" already exists, so its password was NOT changed.')
            print('If you edited ADMIN_PASSWORD in .env and want it to apply, run: python -m backend.create_ceo --reset-password')
        return

    email = f'{u}@brandhub.local'
    auth_user = None
    try:
        auth_user = sb.auth.admin.create_user({'email': email, 'password': p, 'email_confirm': True}).user
    except Exception:
        # The login may already exist without a profile (interrupted earlier run): find it across all pages.
        page = 1
        while auth_user is None:
            batch = sb.auth.admin.list_users(page=page, per_page=200)
            if not batch:
                break
            auth_user = next((x for x in batch if x.email == email), None)
            page += 1
        if auth_user is None:
            sys.exit('Could not create or find the CEO login. Check your Supabase credentials.')
        sb.auth.admin.update_user_by_id(auth_user.id, {'password': p})

    sb.table('profiles').upsert({
        'id': auth_user.id,
        'username': u,
        'name': 'CEO',
        'role': 0,
        'powers': ['review', 'approve', 'files', 'voice', 'authority'],
        'department': 'General',
    }).execute()
    print(f'CEO created. Log in with username "{u}" and the password from .env.')

if __name__ == '__main__':
    main()
