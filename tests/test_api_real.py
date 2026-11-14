"""Real Integration Tests for ECHO API against live Supabase backend.
Creates temporary users across all four roles, tests permissions,
full governance workflow (submit -> recommend -> approve),
file versioning, customer voice, and cleans up completely.
"""
import pytest, os, sys, uuid, io

pytestmark = pytest.mark.live   # real services: skipped unless RUN_LIVE_TESTS=1 (see conftest.py)
from pathlib import Path
from dotenv import load_dotenv
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT))

from backend.app.main import app, sb

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

@pytest.fixture(scope="module")
def ceo_auth(client):
    u = os.getenv('ADMIN_USERNAME', 'itz_ceo').strip().lower()
    p = os.getenv('ADMIN_PASSWORD', '').strip()
    r = client.post('/api/login', json={'username': u, 'password': p})
    assert r.status_code == 200, f"CEO login failed: {r.text}"
    token = r.json()['token']
    return {'Authorization': f'Bearer {token}'}

def test_01_ceo_state_and_departments(client, ceo_auth):
    r = client.get('/api/state', headers=ceo_auth)
    assert r.status_code == 200
    data = r.json()
    assert data['me'] == 'itz_ceo'
    assert data['role'] == 0
    assert 'Marketing' in data['departments']

def test_02_role_hierarchy_and_delegation(client, ceo_auth):
    prefix = uuid.uuid4().hex[:6]
    head_u = f"h_{prefix}"
    sup_u = f"s_{prefix}"
    emp_u = f"e_{prefix}"
    pwd = "TestPassword123!"

    # 1. CEO creates Head of Department
    r1 = client.post('/api/users', json={
        'name': f'Head {prefix}',
        'username': head_u,
        'password': pwd,
        'role': 1,
        'powers': ['review', 'approve', 'files', 'voice', 'authority'],
        'days': 30,
        'department': 'Marketing'
    }, headers=ceo_auth)
    assert r1.status_code == 200, f"Head creation failed: {r1.text}"

    # Login as Head
    r_h_login = client.post('/api/login', json={'username': head_u, 'password': pwd})
    assert r_h_login.status_code == 200
    head_auth = {'Authorization': f"Bearer {r_h_login.json()['token']}"}

    # 2. Head delegates to Supervisor
    r2 = client.post('/api/users', json={
        'name': f'Supervisor {prefix}',
        'username': sup_u,
        'password': pwd,
        'role': 2,
        'powers': ['review', 'authority'],
        'days': 30,
        'department': 'Marketing'
    }, headers=head_auth)
    assert r2.status_code == 200, f"Supervisor creation failed: {r2.text}"

    # Login as Supervisor
    r_s_login = client.post('/api/login', json={'username': sup_u, 'password': pwd})
    assert r_s_login.status_code == 200
    sup_auth = {'Authorization': f"Bearer {r_s_login.json()['token']}"}

    # 3. Supervisor creates Employee
    r3 = client.post('/api/users', json={
        'name': f'Employee {prefix}',
        'username': emp_u,
        'password': pwd,
        'role': 3,
        'powers': [],
        'days': 30,
        'department': 'Marketing'
    }, headers=sup_auth)
    assert r3.status_code == 200, f"Employee creation failed: {r3.text}"

    # Login as Employee
    r_e_login = client.post('/api/login', json={'username': emp_u, 'password': pwd})
    assert r_e_login.status_code == 200
    emp_auth = {'Authorization': f"Bearer {r_e_login.json()['token']}"}

    # 4. Permission Denials
    # Employee cannot approve content
    bad_approve = client.post('/api/posts/1/decide', json={'status': 'Approved', 'note': 'Hacked'}, headers=emp_auth)
    assert bad_approve.status_code in (403, 404)

    # Supervisor cannot grant powers they do not hold (e.g. approve or files)
    bad_delegate = client.post('/api/users', json={
        'name': 'Cheater',
        'username': f"c_{prefix}",
        'password': pwd,
        'role': 3,
        'powers': ['approve'],
        'days': 7
    }, headers=sup_auth)
    assert bad_delegate.status_code == 403

    # Clean up created test users
    client.delete(f'/api/users/{head_u}', headers=ceo_auth)

def test_03_governance_workflow_and_comments(client, ceo_auth):
    prefix = uuid.uuid4().hex[:6]
    h_user = f"h_wf_{prefix}"
    s_user = f"s_wf_{prefix}"
    e_user = f"e_wf_{prefix}"
    pwd = "TestPassword123!"

    # Create test chain
    client.post('/api/users', json={'name': 'Head', 'username': h_user, 'password': pwd, 'role': 1, 'powers': ['review', 'approve', 'authority'], 'days': 30}, headers=ceo_auth)
    h_auth = {'Authorization': f"Bearer {client.post('/api/login', json={'username': h_user, 'password': pwd}).json()['token']}"}

    client.post('/api/users', json={'name': 'Sup', 'username': s_user, 'password': pwd, 'role': 2, 'powers': ['review', 'authority'], 'days': 30}, headers=h_auth)
    s_auth = {'Authorization': f"Bearer {client.post('/api/login', json={'username': s_user, 'password': pwd}).json()['token']}"}

    client.post('/api/users', json={'name': 'Emp', 'username': e_user, 'password': pwd, 'role': 3, 'powers': [], 'days': 30}, headers=s_auth)
    e_auth = {'Authorization': f"Bearer {client.post('/api/login', json={'username': e_user, 'password': pwd}).json()['token']}"}

    # 1. Employee submits draft post
    post_res = client.post('/api/posts', json={'text': 'Welcome our customers to the #1 guaranteed best event.'}, headers=e_auth)
    assert post_res.status_code == 200
    pid = post_res.json()['id']

    # 2. Supervisor cannot approve directly, but can recommend
    bad_appr = client.post(f'/api/posts/{pid}/decide', json={'status': 'Approved', 'note': 'Supervisor cannot approve'}, headers=s_auth)
    assert bad_appr.status_code == 403

    # Supervisor adds inline comment
    comm_res = client.post(f'/api/posts/{pid}/comments', json={'quote': '#1 guaranteed', 'comment': 'Please remove this claim before release'}, headers=s_auth)
    assert comm_res.status_code == 200

    # Supervisor recommends post
    rec_res = client.post(f'/api/posts/{pid}/decide', json={'status': 'Recommended', 'note': 'Looks good after edits'}, headers=s_auth)
    assert rec_res.status_code == 200

    # 3. Head gives final approval
    appr_res = client.post(f'/api/posts/{pid}/decide', json={'status': 'Approved', 'note': 'Approved for launch'}, headers=h_auth)
    assert appr_res.status_code == 200

    # 4. Check timeline history
    hist_res = client.get(f'/api/posts/{pid}/history', headers=e_auth)
    assert hist_res.status_code == 200
    actions = [ev['action'] for ev in hist_res.json()]
    assert 'submitted' in actions
    assert 'comment' in actions
    assert 'Recommended' in actions
    assert 'Approved' in actions

    # Clean up
    client.delete(f'/api/users/{h_user}', headers=ceo_auth)

def test_04_file_vault_versioning_and_signed_url(client, ceo_auth):
    # Create test folder
    f_res = client.post('/api/folders', json={'name': f'Vault_Test_{uuid.uuid4().hex[:6]}'}, headers=ceo_auth)
    assert f_res.status_code == 200
    state = client.get('/api/state', headers=ceo_auth).json()
    fid = state['folders'][-1]['id']

    # Upload file v1
    f_bytes1 = b"Logo guidelines v1: Always maintain clear space."
    up1 = client.post(f'/api/folders/{fid}/files', files={'file': ('logo_guide.txt', io.BytesIO(f_bytes1), 'text/plain')}, headers=ceo_auth)
    assert up1.status_code == 200
    assert up1.json()['version'] == 1

    # Upload file v2
    f_bytes2 = b"Logo guidelines v2: Approved RGB palette added."
    up2 = client.post(f'/api/folders/{fid}/files', files={'file': ('logo_guide.txt', io.BytesIO(f_bytes2), 'text/plain')}, headers=ceo_auth)
    assert up2.status_code == 200
    assert up2.json()['version'] == 2

    # Verify versions list
    v_res = client.get(f'/api/files/{fid}/versions?name=logo_guide.txt', headers=ceo_auth)
    assert v_res.status_code == 200
    versions = v_res.json()
    assert len(versions) >= 2
    assert versions[0]['version'] == 2

    # Get signed download URL
    url_res = client.get(f'/api/files/{versions[0]["id"]}/url', headers=ceo_auth)
    assert url_res.status_code == 200
    assert 'url' in url_res.json()
    assert 'supabase.co' in url_res.json()['url']

    # Restore v1 as latest active version
    v1_id = versions[1]['id']
    rest_res = client.post(f'/api/files/{v1_id}/restore', headers=ceo_auth)
    assert rest_res.status_code == 200
    assert rest_res.json()['new_version'] == 3

def test_05_customer_voice_and_public_feedback(client, ceo_auth):
    # Public feedback submission (no auth)
    pub_res = client.post('/api/public/feedback', json={
        'text': 'The new checkout flow is incredibly fast and smooth!',
        'rating': 5,
        'source': 'Website'
    })
    assert pub_res.status_code == 200
    assert pub_res.json()['ok'] is True

    # Authenticated voice perception gap query
    voice_res = client.get('/api/voice', headers=ceo_auth)
    assert voice_res.status_code == 200
    gap_data = voice_res.json()
    assert 'gap' in gap_data
    assert len(gap_data['gap']) >= 3

    # Insights query
    ins_res = client.get('/api/insights', headers=ceo_auth)
    assert ins_res.status_code == 200
    ins = ins_res.json()
    assert 'violations' in ins
    assert 'by_status' in ins
    assert 'by_department' in ins
    assert 'actions' in ins
