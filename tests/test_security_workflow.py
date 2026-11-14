"""Security and workflow tests for backend/app/main.py.

They call the endpoint functions directly against the in-memory FakeSupabase (tests/fakes.py), so they need no
network and no database. Run from the project root with the real dependencies installed:

    python -m unittest tests.test_security_workflow -v

(Offline sandboxes without FastAPI/pydantic/dotenv can put stand-in modules on PYTHONPATH; the stand-ins are
never part of the project.)
"""
import os, sys, unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from backend.app import main
    from tests.fakes import FakeSupabase
    from fastapi import HTTPException
    _IMPORT_ERROR = None
except ImportError as e:            # dependencies missing: skip instead of failing the whole run
    main = FakeSupabase = None
    HTTPException = Exception
    _IMPORT_ERROR = e


def iso(delta_days):
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


class FakeReq:
    """Just enough of a Request for client_ip()."""
    def __init__(self, host='1.2.3.4'):
        self.client = type('C', (), {'host': host})()


def status_of(fn, *a, **k):
    """HTTP status an endpoint call ends in (200 when it returns normally)."""
    try:
        fn(*a, **k)
    except HTTPException as e:
        return e.status_code
    return 200


@unittest.skipIf(_IMPORT_ERROR is not None, f'backend dependencies not installed: {_IMPORT_ERROR}')
class Base(unittest.TestCase):
    """Org chart used by every test:

        ceo
        |- head_m  (Head, Marketing: review, approve, authority)  -> sup_m (Supervisor: review) -> emp_m
        |- head_s  (Head, Support:   review, approve, authority)  -> emp_s
    """
    def setUp(self):
        self.db = FakeSupabase()
        main._sb = self.db
        main._RATE_LIMITS.clear()
        P = self.db.add_person
        self.uid = {}
        self.uid['ceo'] = P('ceo', 0, powers=main.L.POWERS)
        self.uid['head_m'] = P('head_m', 1, ['review', 'approve', 'authority'], 'Marketing', self.uid['ceo'])
        self.uid['head_s'] = P('head_s', 1, ['review', 'approve', 'authority'], 'Support', self.uid['ceo'])
        self.uid['sup_m'] = P('sup_m', 2, ['review'], 'Marketing', self.uid['head_m'])
        self.uid['emp_m'] = P('emp_m', 3, [], 'Marketing', self.uid['sup_m'])
        self.uid['emp_s'] = P('emp_s', 3, [], 'Support', self.uid['head_s'])

    def tearDown(self):
        main._sb = None

    # helpers
    def me(self, username):
        return main.current(f'Bearer tok-{username}')

    def add_post(self, author, text='Hello members', status='Waiting', findings=None, review_id=None):
        findings = findings if findings is not None else []
        row = self.db.table('posts').insert({
            'author_id': self.uid[author], 'text': text, 'status': status, 'findings': findings,
            'issues': main.active_issues(findings), 'review_id': review_id,
        }).execute().data[0]
        return row['id']

    def add_review(self, author, text, findings):
        return self.db.table('reviews').insert({
            'user_id': self.uid[author], 'text_hash': main.L.text_hash(text), 'findings': findings,
        }).execute().data[0]['id']

    def profile(self, username):
        return self.db.table('profiles').select('*').eq('username', username).execute().data[0]

    def audit_actions(self):
        return [r['action'] for r in self.db.table('audit_log').select('*').execute().data]


def finding(rule, quote, severity='medium'):
    return dict(type='tone', quote=quote, rule_id=rule, rule=rule, severity=severity, confidence='high',
                origin='rules', status='pending')


# --------------------------------------------------------------------------------------------------------------
class TestAuthentication(Base):
    def test_missing_or_bad_token_is_401(self):
        self.assertEqual(status_of(main.current, None), 401)
        self.assertEqual(status_of(main.current, 'Token abc'), 401)
        self.assertEqual(status_of(main.current, 'Bearer nope'), 401)

    def test_effective_powers_are_used_not_stored_ones(self):
        self.assertEqual(self.me('ceo')['powers'], list(main.L.POWERS))
        self.assertEqual(sorted(self.me('head_m')['powers']), ['approve', 'authority', 'review'])
        self.assertEqual(self.me('emp_m')['powers'], [])


class TestDepartmentIsolation(Base):
    def setUp(self):
        super().setUp()
        self.pm = self.add_post('emp_m', 'Marketing post')
        self.ps = self.add_post('emp_s', 'Support post')

    def test_cross_department_endpoints_return_404(self):
        head_s = self.me('head_s')
        body = main.DecideIn(status='Approved', note='x')
        self.assertEqual(status_of(main.decide, self.pm, body, head_s), 404)
        self.assertEqual(status_of(main.get_comments, self.pm, head_s), 404)
        self.assertEqual(status_of(main.history, self.pm, head_s), 404)
        self.assertEqual(status_of(main.add_comment, self.pm, main.CommentIn(quote='q', comment='c'), head_s), 404)
        self.assertEqual(self.db.table('posts').select('*').eq('id', self.pm).execute().data[0]['status'], 'Waiting')

    def test_same_department_head_can_act(self):
        head_m = self.me('head_m')
        self.assertEqual(status_of(main.add_comment, self.pm, main.CommentIn(quote='Marketing', comment='ok?'), head_m), 200)
        self.assertEqual(len(main.get_comments(self.pm, head_m)), 1)
        self.assertEqual(status_of(main.decide, self.pm, main.DecideIn(status='Approved'), head_m), 200)
        self.assertEqual([e['action'] for e in main.history(self.pm, head_m)][-1], 'Approved')

    def test_author_and_ceo_can_always_see_their_post(self):
        self.assertEqual(status_of(main.history, self.pm, self.me('emp_m')), 200)
        self.assertEqual(status_of(main.history, self.ps, self.me('ceo')), 200)

    def test_employee_cannot_see_a_colleagues_post(self):
        self.assertEqual(status_of(main.history, self.pm, self.me('emp_s')), 404)

    def test_missing_post_is_404_not_500(self):
        self.assertEqual(status_of(main.history, 9999, self.me('ceo')), 404)

    def test_state_posts_are_scoped(self):
        def authors(u): return sorted(p['by'] for p in main.state(self.me(u))['posts'])
        self.assertEqual(authors('ceo'), ['emp_m', 'emp_s'])
        self.assertEqual(authors('head_m'), ['emp_m'])
        self.assertEqual(authors('head_s'), ['emp_s'])
        self.assertEqual(authors('sup_m'), ['emp_m'])
        self.assertEqual(authors('emp_m'), ['emp_m'])
        self.assertEqual(authors('emp_s'), ['emp_s'])

    def test_insights_are_scoped(self):
        self.assertEqual(main.insights(self.me('ceo'))['posts'], 2)
        self.assertEqual(main.insights(self.me('head_m'))['posts'], 1)
        self.assertEqual(main.insights(self.me('emp_s'))['posts'], 1)


class TestRevokedAuthority(Base):
    def setUp(self):
        super().setUp()
        self.pm = self.add_post('emp_m')

    def revoke_head_m(self):
        main.takeback('head_m', self.me('ceo'))

    def test_revoked_head_loses_audit_log_and_department_posts(self):
        head = self.me('head_m')
        self.assertEqual(status_of(main.get_audit_log, 100, head), 200)
        self.revoke_head_m()
        head = self.me('head_m')
        self.assertEqual(head['powers'], [])
        self.assertEqual(status_of(main.get_audit_log, 100, head), 403)
        self.assertEqual([p['by'] for p in main.state(head)['posts']], [])     # not a reviewer any more
        self.assertEqual(status_of(main.history, self.pm, head), 404)
        self.assertEqual(status_of(main.decide, self.pm, main.DecideIn(status='Approved'), head), 404)

    def test_takeback_reaches_the_whole_subtree(self):
        self.revoke_head_m()
        self.assertEqual(self.profile('sup_m')['powers'], [])
        self.assertEqual(self.me('sup_m')['powers'], [])

    def test_takeback_keeps_department_column(self):
        self.revoke_head_m()
        self.assertEqual(self.profile('head_m')['department'], 'Marketing')
        self.assertEqual(self.me('head_m')['department'], 'Marketing')
        self.assertEqual(self.me('sup_m')['department'], 'Marketing')

    def test_takeback_keeps_legacy_dept_tag(self):
        self.db.add_person('legacy', 2, ['review', 'dept:Legal'], 'General', self.uid['head_m'])
        self.assertEqual(self.me('legacy')['department'], 'Legal')
        self.revoke_head_m()
        self.assertEqual(self.profile('legacy')['powers'], ['dept:Legal'])
        legacy = self.me('legacy')
        self.assertEqual(legacy['department'], 'Legal')
        self.assertEqual(legacy['powers'], [])

    def test_expired_head_loses_authority(self):
        self.db.table('profiles').update({'expires_at': iso(-1)}).eq('username', 'head_m').execute()
        head = self.me('head_m')
        self.assertEqual(head['powers'], [])
        self.assertEqual(status_of(main.get_audit_log, 100, head), 403)
        # ...and everyone below them lose theirs too
        self.assertEqual(self.me('sup_m')['powers'], [])

    def test_takeback_needs_authority_and_a_target_below_you(self):
        self.assertEqual(status_of(main.takeback, 'emp_m', self.me('sup_m')), 403)    # supervisor has no authority power
        self.assertEqual(status_of(main.takeback, 'head_s', self.me('head_m')), 404)  # not in head_m's chain
        self.assertEqual(status_of(main.takeback, 'ceo', self.me('head_m')), 404)
        self.assertEqual(status_of(main.takeback, 'ceo', self.me('ceo')), 404)        # CEO cannot manage themselves
        self.assertEqual(status_of(main.takeback, 'sup_m', self.me('head_m')), 200)

    def test_remove_user_requires_the_same_checks(self):
        self.assertEqual(status_of(main.remove_user, 'emp_s', self.me('head_m')), 404)
        self.assertEqual(status_of(main.remove_user, 'emp_m', self.me('emp_m')), 403)
        self.assertEqual(len(self.db.table('profiles').select('*').execute().data), 6)


class TestRemoveUser(Base):
    def test_detaches_rows_that_must_survive_and_removes_the_subtree(self):
        t = self.db.table
        fid = t('folders').insert({'name': 'Kit', 'created_by': self.uid['head_m']}).execute().data[0]['id']
        t('files').insert({'folder_id': fid, 'name': 'a.txt', 'version': 1, 'storage_path': 'p', 'uploaded_by': self.uid['sup_m']}).execute()
        t('brand_sources').insert({'kind': 'facts', 'title': 'T', 'content': 'c', 'uploaded_by': self.uid['head_m']}).execute()
        post = self.add_post('emp_m')
        t('post_events').insert({'post_id': post, 'actor_id': self.uid['emp_m'], 'action': 'submitted'}).execute()
        t('reviews').insert({'user_id': self.uid['emp_m'], 'text_hash': 'h', 'findings': []}).execute()

        self.assertEqual(status_of(main.remove_user, 'head_m', self.me('ceo')), 200)

        names = {p['username'] for p in t('profiles').select('*').execute().data}
        self.assertEqual(names, {'ceo', 'head_s', 'emp_s'})
        self.assertEqual(t('folders').select('*').execute().data[0]['created_by'], None)
        self.assertEqual(t('files').select('*').execute().data[0]['uploaded_by'], None)
        self.assertEqual(t('brand_sources').select('*').execute().data[0]['uploaded_by'], None)
        self.assertEqual(t('posts').select('*').execute().data, [])
        self.assertEqual(t('post_events').select('*').execute().data, [])
        self.assertEqual(t('reviews').select('*').execute().data, [])
        emails = {u['email'] for u in self.db.auth_users.values()}
        self.assertNotIn('head_m@brandhub.local', emails)
        self.assertNotIn('emp_m@brandhub.local', emails)
        self.assertIn('head_s@brandhub.local', emails)
        self.assertIn('user.remove', self.audit_actions())


class TestFolderAccess(Base):
    def setUp(self):
        super().setUp()
        ceo = self.me('ceo')
        main.new_folder(main.FolderIn(name='Brand kit', confidential=True), ceo)
        self.fid = self.db.table('folders').select('*').execute().data[0]['id']

    def grant(self, user, level='View', days=0):
        main.set_access(self.fid, main.AccessIn(username=user, level=level, days=days), self.me('ceo'))

    def test_no_access_by_default(self):
        self.assertEqual(main.level(self.me('emp_m'), self.fid), 'None')
        self.assertEqual(main.state(self.me('emp_m'))['folders'], [])

    def test_open_ended_grant_has_no_expiry(self):
        self.grant('emp_m', 'Edit')
        row = self.db.table('folder_access').select('*').execute().data[0]
        self.assertIsNone(row['expires_at'])
        self.assertEqual(main.level(self.me('emp_m'), self.fid), 'Edit')

    def test_time_limited_grant_expires(self):
        self.grant('emp_m', 'View', days=7)
        row = self.db.table('folder_access').select('*').execute().data[0]
        left = (datetime.fromisoformat(row['expires_at']) - datetime.now(timezone.utc)).total_seconds()
        self.assertTrue(6.9 * 86400 < left < 7.1 * 86400)
        me = self.me('emp_m')
        self.assertEqual(main.level(me, self.fid), 'View')
        st = main.state(me)
        self.assertEqual([f['name'] for f in st['folders']], ['Brand kit'])
        self.assertIn('emp_m', st['folders'][0]['access_exp'])

        # time passes
        self.db.table('folder_access').update({'expires_at': iso(-1)}).eq('folder_id', self.fid).execute()
        me = self.me('emp_m')
        self.assertEqual(main.level(me, self.fid), 'None')
        self.assertEqual(main.state(me)['folders'], [])
        self.assertEqual(status_of(main.file_versions, self.fid, 'a.txt', me), 404)

    def test_expired_rows_do_not_show_in_the_ceo_access_list(self):
        self.grant('emp_m', 'View', days=1)
        self.db.table('folder_access').update({'expires_at': iso(-1)}).eq('folder_id', self.fid).execute()
        self.assertEqual(main.state(self.me('ceo'))['folders'][0]['access'], {})

    def test_revoking_with_level_none_removes_the_row(self):
        self.grant('emp_m', 'View')
        self.grant('emp_m', 'None')
        self.assertEqual(self.db.table('folder_access').select('*').execute().data, [])

    def test_only_files_power_can_change_access(self):
        body = main.AccessIn(username='emp_m', level='View', days=0)
        self.assertEqual(status_of(main.set_access, self.fid, body, self.me('head_m')), 403)
        self.assertEqual(status_of(main.set_access, 9999, body, self.me('ceo')), 404)
        self.assertEqual(status_of(main.set_access, self.fid, main.AccessIn(username='emp_m', level='Owner'), self.me('ceo')), 400)
        self.assertEqual(status_of(main.set_access, self.fid, main.AccessIn(username='ghost', level='View'), self.me('ceo')), 404)


class TestReviewDecisionsCarryToPost(Base):
    TEXT = 'Our customers get the best cheap deal'

    def setUp(self):
        super().setUp()
        self.rid = self.add_review('emp_m', self.TEXT, [
            finding('RULE:avoid:cheap', 'cheap', 'low'), finding('RULE:proof:best', 'best', 'high')])

    def test_review_id_reuse_keeps_choices_and_insights_accept_rate(self):
        emp = self.me('emp_m')
        main.finding_action(self.rid, 0, main.ActionIn(action='accepted'), emp)
        main.finding_action(self.rid, 1, main.ActionIn(action='rejected', note='we have proof'), emp)
        with mock.patch.object(main, 'execute_review', side_effect=AssertionError('must not re-review')):
            pid = main.submit(main.PostIn(text=self.TEXT, review_id=self.rid), emp)['id']
        post = self.db.table('posts').select('*').eq('id', pid).execute().data[0]
        self.assertEqual([f['status'] for f in post['findings']], ['accepted', 'rejected'])
        self.assertEqual(post['issues'], 1)                      # rejected finding is not an open issue
        self.assertEqual(post['review_id'], self.rid)
        acts = main.insights(self.me('ceo'))['actions']
        self.assertEqual((acts['accepted'], acts['rejected'], acts['accept_rate']), (1, 1, 50.0))

    def test_later_action_is_synced_to_the_post_and_insights(self):
        emp = self.me('emp_m')
        with mock.patch.object(main, 'execute_review', side_effect=AssertionError):
            pid = main.submit(main.PostIn(text=self.TEXT, review_id=self.rid), emp)['id']
        main.finding_action(self.rid, 0, main.ActionIn(action='accepted'), emp)
        main.finding_action(self.rid, 1, main.ActionIn(action='edited', edited_text='top-rated'), emp)
        post = self.db.table('posts').select('*').eq('id', pid).execute().data[0]
        self.assertEqual([f['status'] for f in post['findings']], ['accepted', 'edited'])
        self.assertEqual(post['findings'][1]['edited_text'], 'top-rated')
        main.finding_action(self.rid, 0, main.ActionIn(action='rejected'), emp)
        post = self.db.table('posts').select('*').eq('id', pid).execute().data[0]
        self.assertEqual(post['issues'], 1)
        acts = main.insights(self.me('ceo'))['actions']
        self.assertEqual((acts['accepted'], acts['rejected'], acts['edited'], acts['accept_rate']), (0, 1, 1, 0.0))

    def test_finding_action_is_owner_only(self):
        body = main.ActionIn(action='accepted')
        for other in ('head_m', 'sup_m', 'ceo', 'emp_s'):
            self.assertEqual(status_of(main.finding_action, self.rid, 0, body, self.me(other)), 404, other)
        self.assertEqual(self.db.table('reviews').select('*').execute().data[0]['findings'][0]['status'], 'pending')

    def test_finding_action_index_and_missing_review(self):
        emp = self.me('emp_m')
        self.assertEqual(status_of(main.finding_action, self.rid, 5, main.ActionIn(action='accepted'), emp), 404)
        self.assertEqual(status_of(main.finding_action, self.rid, -1, main.ActionIn(action='accepted'), emp), 404)
        self.assertEqual(status_of(main.finding_action, 999, 0, main.ActionIn(action='accepted'), emp), 404)

    def test_findings_lock_once_the_post_moves_on(self):
        emp = self.me('emp_m')
        with mock.patch.object(main, 'execute_review', side_effect=AssertionError):
            pid = main.submit(main.PostIn(text=self.TEXT, review_id=self.rid), emp)['id']
        main.decide(pid, main.DecideIn(status='Recommended'), self.me('sup_m'))
        self.assertEqual(status_of(main.finding_action, self.rid, 0, main.ActionIn(action='accepted'), emp), 409)

    def test_changed_text_or_foreign_review_is_reviewed_again(self):
        fake = (777, [finding('RULE:avoid:guys', 'guys', 'low')], False, None)
        with mock.patch.object(main, 'execute_review', return_value=fake) as m:
            rid, f = main.reuse_or_review(self.me('emp_m'), 'Different text', self.rid)
            self.assertEqual((rid, m.call_count), (777, 1))
            rid, f = main.reuse_or_review(self.me('emp_s'), self.TEXT, self.rid)       # someone else's review
            self.assertEqual((rid, m.call_count), (777, 2))
            rid, f = main.reuse_or_review(self.me('emp_m'), self.TEXT + '  ', self.rid)  # same text, whitespace only
            self.assertEqual((rid, m.call_count), (self.rid, 2))

    def test_revise_resets_status_and_only_author_may_revise(self):
        emp = self.me('emp_m')
        with mock.patch.object(main, 'execute_review', return_value=(5, [], False, None)):
            pid = main.submit(main.PostIn(text=self.TEXT), emp)['id']
            self.assertEqual(status_of(main.revise_post, pid, main.ReviseIn(text='new'), self.me('head_m')), 403)
            main.decide(pid, main.DecideIn(status='Sent back', note='fix'), self.me('sup_m'))
            main.revise_post(pid, main.ReviseIn(text='new text'), emp)
        post = self.db.table('posts').select('*').eq('id', pid).execute().data[0]
        self.assertEqual((post['status'], post['text']), ('Waiting', 'new text'))


class TestDecideTransitions(Base):
    def decide(self, who, pid, status):
        return status_of(main.decide, pid, main.DecideIn(status=status, note='n'), self.me(who))

    def status(self, pid):
        return self.db.table('posts').select('*').eq('id', pid).execute().data[0]['status']

    def test_happy_path(self):
        pid = self.add_post('emp_m')
        self.assertEqual(self.decide('sup_m', pid, 'Recommended'), 200)
        self.assertEqual(self.decide('head_m', pid, 'Approved'), 200)
        self.assertEqual(self.status(pid), 'Approved')

    def test_head_can_approve_straight_from_waiting(self):
        pid = self.add_post('emp_m')
        self.assertEqual(self.decide('head_m', pid, 'Approved'), 200)

    def test_invalid_transitions_are_409(self):
        approved = self.add_post('emp_m', status='Approved')
        recommended = self.add_post('emp_m', status='Recommended')
        sent_back = self.add_post('emp_m', status='Sent back')
        self.assertEqual(self.decide('head_m', approved, 'Approved'), 409)
        self.assertEqual(self.decide('head_m', approved, 'Sent back'), 409)
        self.assertEqual(self.decide('head_m', approved, 'Recommended'), 409)
        self.assertEqual(self.decide('head_m', recommended, 'Recommended'), 409)
        self.assertEqual(self.decide('head_m', sent_back, 'Approved'), 409)
        self.assertEqual(self.decide('head_m', sent_back, 'Recommended'), 409)
        self.assertEqual(self.status(approved), 'Approved')

    def test_recommended_can_be_sent_back(self):
        pid = self.add_post('emp_m', status='Recommended')
        self.assertEqual(self.decide('head_m', pid, 'Sent back'), 200)

    def test_permissions(self):
        pid = self.add_post('emp_m')
        self.assertEqual(self.decide('sup_m', pid, 'Approved'), 403)       # reviewer without 'approve'
        self.assertEqual(self.decide('emp_m', pid, 'Recommended'), 403)    # author without any review power
        self.assertEqual(self.decide('head_m', pid, 'Published'), 400)     # unknown status
        self.assertEqual(self.status(pid), 'Waiting')

    def test_nobody_reviews_their_own_post(self):
        pid = self.add_post('head_m')
        self.assertEqual(self.decide('head_m', pid, 'Approved'), 403)
        self.assertEqual(self.decide('ceo', pid, 'Approved'), 200)         # CEO is a different person: allowed

    def test_ceo_cannot_approve_own_post(self):
        pid = self.add_post('ceo')
        self.assertEqual(self.decide('ceo', pid, 'Approved'), 403)

    def test_decisions_are_audited(self):
        pid = self.add_post('emp_m')
        self.decide('head_m', pid, 'Approved')
        self.assertIn('post.approved', self.audit_actions())


class TestDelegation(Base):
    def new(self, who, **kw):
        base = dict(name='New Person', username='newbie', password='longenough1', role=3, powers=[], days=7)
        base.update(kw)
        return status_of(main.add_user, main.UserIn(**base), self.me(who))

    def test_non_ceo_cannot_grant_open_ended_authority(self):
        self.assertEqual(self.new('head_m', days=0), 403)
        self.assertEqual(self.db.table('profiles').select('*').eq('username', 'newbie').execute().data, [])

    def test_ceo_can_grant_open_ended_authority(self):
        self.assertEqual(self.new('ceo', days=0, role=1, powers=['review']), 200)
        self.assertIsNone(self.profile('newbie')['expires_at'])

    def test_child_expiry_is_clamped_to_the_grantors(self):
        head_exp = datetime.now(timezone.utc) + timedelta(days=10)
        self.db.table('profiles').update({'expires_at': head_exp.isoformat()}).eq('username', 'head_m').execute()
        self.assertEqual(self.new('head_m', days=30, role=2, powers=['review']), 200)
        got = datetime.fromisoformat(self.profile('newbie')['expires_at'])
        self.assertLess(abs((got - head_exp).total_seconds()), 2)
        # a shorter request is kept as is
        self.assertEqual(self.new('head_m', username='short', days=3), 200)
        got = datetime.fromisoformat(self.profile('short')['expires_at'])
        self.assertLess(abs((got - (datetime.now(timezone.utc) + timedelta(days=3))).total_seconds()), 5)

    def test_non_ceo_delegates_stay_in_the_grantors_department(self):
        self.assertEqual(self.new('head_m', department='Support'), 200)
        self.assertEqual(self.profile('newbie')['department'], 'Marketing')

    def test_ceo_picks_a_known_department_only(self):
        self.assertEqual(self.new('ceo', role=1, department='Atlantis'), 400)
        self.assertEqual(self.new('ceo', role=1, department='Legal'), 200)
        self.assertEqual(self.profile('newbie')['department'], 'Legal')

    def test_cannot_give_powers_you_do_not_hold_or_go_upward(self):
        self.assertEqual(self.new('head_m', role=2, powers=['files']), 403)
        self.assertEqual(self.new('head_m', role=1), 403)
        self.assertEqual(self.new('head_m', role=0), 403)
        self.assertEqual(self.new('sup_m', role=3), 403)                    # no authority power
        self.assertEqual(self.new('ceo', role=1, powers=['teleport']), 403)   # not a power anyone holds
        self.assertEqual(self.db.table('profiles').select('*').eq('username', 'newbie').execute().data, [])

    def test_duplicate_username_is_409(self):
        self.assertEqual(self.new('head_m', username='EMP_M'), 409)


class TestAuditLogScoping(Base):
    def setUp(self):
        super().setUp()
        for who in ('ceo', 'head_m', 'sup_m', 'emp_m', 'head_s', 'emp_s'):
            self.db.table('audit_log').insert({'actor_id': self.uid[who], 'action': f'mark.{who}'}).execute()
        self.db.table('audit_log').insert({'actor_id': None, 'action': 'mark.public'}).execute()

    def actions(self, who):
        return {r['action'] for r in main.get_audit_log(100, self.me(who))}

    def test_ceo_sees_everything(self):
        self.assertEqual(self.actions('ceo'), {f'mark.{w}' for w in
                         ('ceo', 'head_m', 'sup_m', 'emp_m', 'head_s', 'emp_s', 'public')})

    def test_head_sees_only_self_and_subtree(self):
        self.assertEqual(self.actions('head_m'), {'mark.head_m', 'mark.sup_m', 'mark.emp_m'})
        self.assertEqual(self.actions('head_s'), {'mark.head_s', 'mark.emp_s'})

    def test_everyone_else_is_refused(self):
        for who in ('sup_m', 'emp_m', 'emp_s'):
            self.assertEqual(status_of(main.get_audit_log, 100, self.me(who)), 403, who)

    def test_limit_is_clamped(self):
        self.assertEqual(len(main.get_audit_log(-5, self.me('ceo'))), 1)
        self.assertLessEqual(len(main.get_audit_log(10 ** 9, self.me('ceo'))), 500)


class TestRules(Base):
    def seed(self, **extra):
        rules = dict(main.DEFAULT_RULES, departments=['Marketing', 'Support', 'Legal', 'Atlantis', 'General'])
        rules.update(extra)
        self.db.table('brand_rules').insert({'id': 1, 'rules': rules}).execute()

    def saved(self):
        return self.db.table('brand_rules').select('*').execute().data[0]['rules']

    def test_empty_departments_never_wipe_custom_ones(self):
        self.seed()
        main.put_rules(main.RulesIn(avoid=['cheap'], departments=[]), self.me('ceo'))
        self.assertEqual(self.saved()['departments'], ['Marketing', 'Support', 'Legal', 'Atlantis', 'General'])

    def test_general_is_always_present(self):
        self.seed()
        main.put_rules(main.RulesIn(departments=['Marketing']), self.me('ceo'))
        self.assertEqual(self.saved()['departments'], ['Marketing', 'General'])

    def test_empty_and_duplicate_words_are_dropped(self):
        self.seed()
        main.put_rules(main.RulesIn(
            avoid=['  ', 'cheap', 'CHEAP', '', 'guys'],
            proof=['', '#1'],
            prefer=[['customers', 'members'], ['x', ''], ['', 'y'], ['only one']],
            target={'Reliable': 99, 'Friendly': 0, 'Nonsense': 5}), self.me('ceo'))
        r = self.saved()
        self.assertEqual(r['avoid'], ['cheap', 'guys'])
        self.assertEqual(r['proof'], ['#1'])
        self.assertEqual(r['prefer'], [['customers', 'members']])
        self.assertEqual(r['target'], {'Reliable': 10, 'Friendly': 1})
        # the saved rules must behave: no empty-word match, no crash
        self.assertEqual(main.L.scan('hello world', r), [])

    def test_missing_target_falls_back_to_existing(self):
        self.seed(target={'Reliable': 7})
        main.put_rules(main.RulesIn(target={'Nonsense': 5}), self.me('ceo'))
        self.assertEqual(self.saved()['target'], {'Reliable': 7})

    def test_only_ceo_can_change_rules_and_departments(self):
        self.seed()
        self.assertEqual(status_of(main.put_rules, main.RulesIn(avoid=['x']), self.me('head_m')), 403)
        self.assertEqual(status_of(main.add_department, main.DeptIn(name='Ops'), self.me('head_m')), 403)
        self.assertEqual(status_of(main.delete_department, 'Legal', self.me('head_m')), 403)

    def test_deleting_a_department_moves_people_to_general(self):
        self.seed()
        self.assertEqual(status_of(main.delete_department, 'General', self.me('ceo')), 400)
        main.delete_department('Marketing', self.me('ceo'))
        self.assertNotIn('Marketing', self.saved()['departments'])
        self.assertEqual(self.profile('head_m')['department'], 'General')
        self.assertEqual(self.profile('head_s')['department'], 'Support')

    def test_add_department_is_idempotent(self):
        self.seed()
        main.add_department(main.DeptIn(name='Ops'), self.me('ceo'))
        main.add_department(main.DeptIn(name='Ops'), self.me('ceo'))
        self.assertEqual(self.saved()['departments'].count('Ops'), 1)


class TestPublicFeedback(Base):
    def setUp(self):
        super().setUp()
        # An AI key "exists", so anything that wrongly reaches the model would be caught.
        p1 = mock.patch.object(main.AI, 'get_active_model_info',
                               return_value={'has_key': True, 'provider': 'Gemini', 'model': 'm'})
        self.llm = mock.patch.object(main.AI, 'call_llm', side_effect=AssertionError('LLM must not be called'))
        p1.start(); self.llm_mock = self.llm.start()
        self.addCleanup(p1.stop); self.addCleanup(self.llm.stop)

    def test_public_form_never_calls_the_llm_and_masks_pii(self):
        body = main.FbIn(text='Slow delivery, call me on +91 98765 43210 or mail a.b@example.com', rating=1)
        out = main.public_feedback(body, FakeReq())
        self.assertTrue(out['ok'])
        self.assertEqual(self.llm_mock.call_count, 0)
        row = self.db.table('feedback').select('*').execute().data[0]
        self.assertNotIn('98765', row['text'])
        self.assertNotIn('example.com', row['text'])
        self.assertEqual(row['source'], 'Public Website Form')
        self.assertEqual(row['sentiment'], 'negative')

    def test_source_cannot_be_spoofed(self):
        main.public_feedback(main.FbIn(source='Verified Customer', text='ok', rating=5), FakeReq())
        self.assertEqual(self.db.table('feedback').select('*').execute().data[0]['source'], 'Public Website Form')

    def test_per_ip_limit(self):
        codes = [status_of(main.public_feedback, main.FbIn(text='hi'), FakeReq('9.9.9.9')) for _ in range(12)]
        self.assertEqual(codes[:10], [200] * 10)
        self.assertEqual(codes[10:], [429, 429])
        self.assertEqual(status_of(main.public_feedback, main.FbIn(text='hi'), FakeReq('8.8.8.8')), 200)

    def test_global_cap(self):
        import time
        main._RATE_LIMITS['pub_fb:global'] = [time.time()] * 300
        self.assertEqual(status_of(main.public_feedback, main.FbIn(text='hi'), FakeReq('7.7.7.7')), 429)
        self.assertEqual(self.db.table('feedback').select('*').execute().data, [])

    def test_voice_data_needs_the_voice_power(self):
        self.assertEqual(status_of(main.voice, self.me('head_m')), 403)
        self.assertEqual(status_of(main.voice, self.me('ceo')), 200)
        self.assertEqual(main.state(self.me('head_m'))['fb'], [])


class TestAuthorisationOfAdminAreas(Base):
    def test_knowledge_base_is_ceo_only(self):
        self.assertEqual(status_of(main.del_source, 1, self.me('head_m')), 403)
        self.assertEqual(main.state(self.me('head_m'))['sources'], [])

    def test_folders_need_files_power(self):
        self.assertEqual(status_of(main.new_folder, main.FolderIn(name='x'), self.me('head_m')), 403)

    def test_login_throttle_is_per_username(self):
        main._RATE_LIMITS.clear()
        with mock.patch.dict(os.environ, {'SUPABASE_URL': '', 'SUPABASE_SERVICE_KEY': ''}):
            codes = [status_of(main.login, main.LoginIn(username='Victim', password='x'), FakeReq(f'10.0.0.{i}'))
                     for i in range(12)]
        self.assertEqual(codes[:10], [503] * 10)       # reached the (unconfigured) backend: not throttled yet
        self.assertEqual(codes[10:], [429, 429])        # 11th guess at the same account is throttled, other IPs or not

    def _login_with(self, exc):
        """Run login() with a fake supabase client whose sign-in raises exc."""
        fake_mod = type(sys)('supabase')
        class Auth:
            def sign_in_with_password(self, creds): raise exc
        fake_mod.create_client = lambda url, key: type('C', (), {'auth': Auth()})()
        env = {'SUPABASE_URL': 'https://x.supabase.co', 'SUPABASE_SERVICE_KEY': 'k'}
        with mock.patch.dict(os.environ, env), mock.patch.dict(sys.modules, {'supabase': fake_mod}):
            return status_of(main.login, main.LoginIn(username='itz_ceo', password='x'), FakeReq())

    def test_wrong_password_is_401_but_setup_problems_are_not(self):
        self.assertEqual(self._login_with(Exception('Invalid login credentials')), 401)
        self.assertEqual(self._login_with(Exception('Invalid API key')), 503)
        self.assertEqual(self._login_with(ConnectionError('getaddrinfo failed')), 503)

class TestAllAccountAccess(Base):
    """Demo markers must not create a special restricted account or filter shared records."""
    def setUp(self):
        super().setUp()
        self.uid['judge_demo'] = self.db.add_person(
            'judge_demo', 2, ['voice'], 'Marketing', self.uid['ceo']
        )
        self.db.table('profiles').update({'is_demo': True}).eq('username', 'judge_demo').execute()

    def test_all_profiles_remain_visible_to_every_authenticated_account(self):
        judge = self.me('judge_demo')
        self.assertEqual({u['username'] for u in judge['all']},
                         {'ceo', 'head_m', 'head_s', 'sup_m', 'emp_m', 'emp_s', 'judge_demo'})
        state = main.state(judge)
        self.assertEqual({u['username'] for u in state['users']},
                         {'ceo', 'head_m', 'head_s', 'sup_m', 'emp_m', 'emp_s', 'judge_demo'})

    def test_voice_account_can_read_and_add_shared_feedback(self):
        self.db.table('feedback').insert([
            {'source':'Google Play','text':'Existing customer complaint','rating':1,
             'sentiment':'negative','topic':'payment','external_id':'play:live-1'}
        ]).execute()
        judge = self.me('judge_demo')
        state = main.state(judge)
        self.assertIn('Existing customer complaint', [row['t'] for row in state['fb']])
        self.assertEqual(status_of(main.add_fb, main.FbIn(text='new shared customer comment'), judge), 200)
        self.assertEqual(self.db.table('feedback').select('*').execute().data[-1]['text'], 'new shared customer comment')

    def test_voice_account_uses_shared_brand_rules_sources_feedback_and_facts(self):
        self.db.table('brand_rules').upsert({'id':1,'rules':{
            'avoid':['shared-approved-term'],'prefer':[],'proof':[],
            'target':{'Reliable':7},'departments':['Marketing','Support']
        }}).execute()
        self.db.table('brand_sources').insert([
            {'kind':'guidelines','title':'Shared organisation source','content':'This is approved shared content.'}
        ]).execute()
        self.db.table('feedback').insert([
            {'source':'Website','text':'Shared payment complaint','rating':1,
             'sentiment':'negative','topic':'payment','external_id':'web:shared-1'}
        ]).execute()
        self.db.table('approved_facts').insert([
            {'name':'Live price','value':'₹1,499','source_title':'Shared live price list','is_demo':False},
            {'name':'Sample price','value':'₹999','source_title':'Sample price list','is_demo':True},
        ]).execute()
        judge = self.me('judge_demo')
        self.assertEqual(main.get_departments(judge)['departments'], ['Marketing','Support'])
        facts = main.list_approved_facts(judge)
        self.assertEqual({f['name'] for f in facts}, {'Live price','Sample price'})
        seen = {}
        def fake_review(text, sources, recent_complaints=None):
            seen['sources'] = sources
            seen['complaints'] = recent_complaints
            return [], False, 'Rules Engine Only'
        with mock.patch.object(main.AI, 'run_ai_review', side_effect=fake_review):
            main.execute_review(judge, 'A neutral product update for customers.')
        self.assertIn('Shared organisation source', [row['title'] for row in seen['sources']])
        self.assertIn('Shared live price list', [row['title'] for row in seen['sources']])
        self.assertIn('Shared payment complaint', [row['text'] for row in seen['complaints']])

    def test_sample_evaluation_tools_are_available_to_any_voice_account(self):
        judge = self.me('judge_demo')
        self.assertEqual(status_of(main.complaint_demo_labels, judge), 200)
        preview = main.demo_feedback_cleaning_preview(judge)
        self.assertEqual(preview['input_rows'], 3)
        self.assertEqual(preview['duplicates_removed'], 1)
        self.assertEqual(preview['pii_items_masked'], 6)
        self.assertFalse(preview['persisted'])

    def test_normal_role_permissions_are_not_elevated(self):
        judge = self.me('judge_demo')
        self.assertEqual(status_of(main.add_approved_fact, main.ApprovedFactIn(
            name='Unauthorized fact', value='₹1', source_title='Unapproved source'
        ), judge), 403)
        self.assertEqual(status_of(main.sync_feedback_connectors, judge), 403)


class TestDemoLogin(Base):
    def test_existing_optional_demo_login_flag_is_preserved_and_off_by_default(self):
        with mock.patch.dict(os.environ, {'DEMO_LOGIN_ENABLED':'0'}):
            self.assertEqual(main.health(), {'ok':True, 'demo_login':False})
            self.assertEqual(status_of(main.demo_login, FakeReq()), 404)

    def test_existing_optional_demo_login_can_be_enabled_explicitly(self):
        with mock.patch.dict(os.environ, {'DEMO_LOGIN_ENABLED':'1', 'ADMIN_USERNAME':'ceo', 'ADMIN_PASSWORD':'StrongTestPassword123!'}), \
             mock.patch.object(main, '_password_sign_in', return_value=type('Sess', (), {'access_token':'test-token'})()):
            # The endpoint reaches the existing authentication path and audits the CEO login.
            result = main.demo_login(FakeReq())
            self.assertEqual(result['username'], 'ceo')
            self.assertEqual(result['token'], 'test-token')


if __name__ == '__main__':
    unittest.main()
