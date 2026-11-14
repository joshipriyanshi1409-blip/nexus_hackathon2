"""Create one named account directly (for team/judge accounts you want on the sign-in page, not through the app).

Run from the project folder, after `python -m backend.create_ceo` has already created the CEO login:

    python -m backend.add_team_member --name "Vincent" --username twlightt --role head --department Legal --created-by itz_ceo

Role: ceo | head | supervisor | employee  (head/supervisor/employee need --department; ceo does not).
Powers default to the normal set for that role (head: review, approve, authority; supervisor: review; employee:
none). Pass --powers to override, e.g. --powers review,approve.

--created-by sets who manages this account (default: ADMIN_USERNAME, i.e. the CEO). This matters: it is how the
app knows a Supervisor's chain of command for takeback/remove, so create Heads under the CEO, then create each
Supervisor under their Head, then each Employee under their Supervisor (or Head), in that order.

If --password is omitted, a random 14-character password is generated and printed once; write it down, because
Supabase never lets you read it back. Running this again for the same --username only resets that one password
(it never touches other accounts), so it's also how you rotate a team member's password later.
"""
import argparse, os, secrets, string, sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

ROLE_NUM = {'ceo': 0, 'head': 1, 'supervisor': 2, 'employee': 3}
DEFAULT_POWERS = {'ceo': ['review', 'approve', 'files', 'voice', 'authority'],
                   'head': ['review', 'approve', 'authority'], 'supervisor': ['review'], 'employee': []}


def gen_password():
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(14))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--name', required=True)
    ap.add_argument('--username', required=True, help='letters, numbers, underscore; what they type to sign in')
    ap.add_argument('--role', required=True, choices=ROLE_NUM)
    ap.add_argument('--department', default='General')
    ap.add_argument('--powers', default=None, help='comma-separated; default is the normal set for --role')
    ap.add_argument('--password', default=None, help='omit to generate one (shown once, printed here)')
    ap.add_argument('--created-by', default=None, help='username of their manager (default: ADMIN_USERNAME / the CEO)')
    a = ap.parse_args()

    u = a.username.strip().lower().lstrip('@')
    if not u.replace('_', '').isalnum() or not (3 <= len(u) <= 30):
        sys.exit('--username must be 3-30 letters/numbers/underscore (no @, no spaces).')
    p = (a.password or gen_password()).strip()
    if len(p) < 12:
        sys.exit('--password must be at least 12 characters (or omit --password to generate one).')

    from backend.create_ceo import key_problem
    from supabase import create_client
    url = os.environ.get('SUPABASE_URL', '').strip()
    key = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()
    if not (url and key):
        sys.exit('Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env first.')
    bad = key_problem(key)
    if bad:
        sys.exit(f'SUPABASE_SERVICE_KEY is wrong: {bad}')
    sb = create_client(url, key)

    powers = a.powers.split(',') if a.powers else DEFAULT_POWERS[a.role]
    email = f'{u}@brandhub.local'

    creator_u = (a.created_by or os.getenv('ADMIN_USERNAME', 'itz_ceo')).strip().lower().lstrip('@')
    creator_id = None
    if a.role != 'ceo':
        try:
            found = sb.table('profiles').select('id').eq('username', creator_u).execute().data
        except Exception as e:
            sys.exit(f'Could not read the database ({type(e).__name__}). Have the SQL migrations been run in this Supabase project?')
        if not found:
            sys.exit(f'--created-by "{creator_u}" does not exist yet. Create their manager first (run this script '
                      f'for "{creator_u}" before "{u}").')
        creator_id = found[0]['id']

    try:
        existing = sb.table('profiles').select('id').eq('username', u).execute().data
    except Exception as e:
        sys.exit(f'Could not read the database ({type(e).__name__}). Have the SQL migrations been run in this Supabase project?')

    if existing:
        try:
            sb.auth.admin.update_user_by_id(existing[0]['id'], {'password': p})
        except Exception as e:
            sys.exit(f'Supabase refused the password change ({type(e).__name__}). Check SUPABASE_SERVICE_KEY.')
        sb.table('profiles').update({'name': a.name, 'role': ROLE_NUM[a.role], 'powers': powers,
                                      'department': a.department, 'created_by': creator_id}).eq('username', u).execute()
        print(f'Updated "{u}" and reset the password.')
    else:
        try:
            auth_user = sb.auth.admin.create_user({'email': email, 'password': p, 'email_confirm': True}).user
        except Exception as e:
            sys.exit(f'Could not create the login ({type(e).__name__}). Is "{u}" already used, or is SUPABASE_SERVICE_KEY wrong?')
        sb.table('profiles').upsert({'id': auth_user.id, 'username': u, 'name': a.name, 'role': ROLE_NUM[a.role],
                                      'powers': powers, 'department': a.department, 'created_by': creator_id}).execute()
        print(f'Created "{u}".')

    print(f'  Name:       {a.name}')
    print(f'  Username:   {u}')
    print(f'  Role:       {a.role} ({a.department})')
    print(f'  Password:   {p}')
    print('Write this down now; Supabase will not show the password again.')


if __name__ == '__main__':
    main()
