"""In-memory stand-in for the Supabase client, so API logic can be tested offline (no network, no real database)."""
import copy, itertools
from datetime import datetime, timezone

_DEFAULTS = {
    'posts': {'note': '', 'issues': 0, 'findings': [], 'review_id': None, 'status': 'Waiting'},
    'post_events': {'note': ''},
    'reviews': {'findings': [], 'model': None, 'used_ai': False},
    'folders': {'is_confidential': True},
    'files': {'size': 0},
    'brand_sources': {'storage_path': None},
    'feedback': {'rating': 3, 'happened_at': ''},
    'audit_log': {'detail': ''},
}
_KEYS = {'folder_access': ('folder_id', 'user_id'), 'profiles': ('id',), 'brand_rules': ('id',)}


class Result:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.op, self.payload = 'select', None
        self.filters, self._order, self._limit = [], None, None

    # operations
    def select(self, cols='*'): self.op = 'select'; return self
    def insert(self, rows): self.op, self.payload = 'insert', rows; return self
    def update(self, vals): self.op, self.payload = 'update', vals; return self
    def delete(self): self.op = 'delete'; return self
    def upsert(self, rows, on_conflict=None): self.op, self.payload = 'upsert', rows; return self
    # filters
    def eq(self, c, v): self.filters.append(lambda r: r.get(c) == v); return self
    def neq(self, c, v): self.filters.append(lambda r: r.get(c) != v); return self
    def in_(self, c, vs): vs = list(vs); self.filters.append(lambda r: r.get(c) in vs); return self
    def order(self, c, desc=False): self._order = (c, desc); return self
    def limit(self, n): self._limit = n; return self

    def _match(self, r): return all(f(r) for f in self.filters)

    def execute(self):
        rows = self.db.tables.setdefault(self.name, [])
        if self.op == 'select':
            out = [copy.deepcopy(r) for r in rows if self._match(r)]
            if self._order:
                c, desc = self._order
                out.sort(key=lambda r: (r.get(c) is None, r.get(c)), reverse=desc)
            return Result(out[:self._limit] if self._limit else out)
        if self.op == 'insert':
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            if not items:
                raise ValueError('insert of an empty list')
            made = [self.db.new_row(self.name, i) for i in items]
            rows.extend(made)
            return Result(copy.deepcopy(made))
        if self.op == 'update':
            hit = [r for r in rows if self._match(r)]
            for r in hit: r.update(copy.deepcopy(self.payload))
            return Result(copy.deepcopy(hit))
        if self.op == 'delete':
            gone = [r for r in rows if self._match(r)]
            self.db.tables[self.name] = [r for r in rows if not self._match(r)]
            self.db.after_delete(self.name, gone)
            return Result(copy.deepcopy(gone))
        if self.op == 'upsert':
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            keys = _KEYS.get(self.name, ('id',))
            for it in items:
                ex = next((r for r in rows if all(r.get(k) == it.get(k) for k in keys)), None)
                if ex: ex.update(copy.deepcopy(it))
                else: rows.append(self.db.new_row(self.name, it))
            return Result(copy.deepcopy(items))


class _Admin:
    def __init__(self, db): self.db = db
    def create_user(self, attrs):
        if any(u['email'] == attrs['email'] for u in self.db.auth_users.values()):
            raise ValueError('already registered')
        uid = f"uid-{next(self.db.counter)}"
        self.db.auth_users[uid] = {'email': attrs['email'], 'password': attrs['password']}
        return type('R', (), {'user': type('U', (), {'id': uid, 'email': attrs['email']})()})()
    def delete_user(self, uid): self.db.auth_users.pop(uid, None)


class _Auth:
    def __init__(self, db): self.db, self.admin = db, _Admin(db)
    def get_user(self, token):
        uid = self.db.tokens.get(token)
        if not uid: raise ValueError('invalid jwt')
        return type('R', (), {'user': type('U', (), {'id': uid})()})()


class _Bucket:
    def __init__(self, db): self.db = db
    def upload(self, path, data, opts=None): self.db.blobs[path] = data
    def create_signed_url(self, path, ttl): return {'signedURL': f'https://files.example/{path}?token=t'}


class _Storage:
    def __init__(self, db): self.db = db
    def from_(self, name): return _Bucket(self.db)


class FakeSupabase:
    def __init__(self):
        self.tables, self.auth_users, self.tokens, self.blobs = {}, {}, {}, {}
        self.counter, self._ids = itertools.count(1), {}
        self.auth, self.storage = _Auth(self), _Storage(self)

    def table(self, name): return Query(self, name)

    def new_row(self, table, item):
        row = dict(_DEFAULTS.get(table, {}))
        row.update(copy.deepcopy(item))
        if table not in _KEYS and 'id' not in row:
            self._ids[table] = self._ids.get(table, 0) + 1
            row['id'] = self._ids[table]
        row.setdefault('created_at', datetime.now(timezone.utc).isoformat())
        return row

    def after_delete(self, table, gone):
        """Emulate a few ON DELETE rules the real schema has."""
        if table == 'folders':
            ids = {r['id'] for r in gone}
            self.tables['folder_access'] = [a for a in self.tables.get('folder_access', []) if a['folder_id'] not in ids]

    # ---- test helpers ----
    def add_person(self, username, role, powers=(), department='General', created_by=None, expires_at=None, name=None):
        uid = f"uid-{next(self.counter)}"
        self.auth_users[uid] = {'email': f'{username}@brandhub.local', 'password': 'x'}
        self.tokens[f'tok-{username}'] = uid
        self.tables.setdefault('profiles', []).append({
            'id': uid, 'username': username, 'name': name or username.title(), 'role': role,
            'powers': list(powers), 'department': department, 'created_by': created_by, 'expires_at': expires_at,
        })
        return uid
