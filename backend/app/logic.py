"""Pure business logic (no network, no framework) so it can be unit-tested anywhere."""
import csv, hashlib, io, re, time
from typing import List, Dict, Any, Optional, Tuple

POWERS = ['review', 'approve', 'files', 'voice', 'authority']
ROLES = ['CEO', 'Head of Department', 'Supervisor', 'Employee']
LEVELS = ['None', 'View', 'Comment', 'Edit', 'Approve']
POSITIVE = {'friendly', 'helpful', 'kind', 'great', 'love', 'quick', 'fast', 'reliable', 'excellent', 'good', 'happy', 'easy'}
NEGATIVE = {'slow', 'late', 'delay', 'delayed', 'rude', 'ignored', 'broken', 'bug', 'failed', 'bad', 'worst', 'refund', 'disappointing', 'terrible', 'expensive'}
TOPICS = {
    'refunds': ['refund'],
    'delivery': ['delivery', 'late', 'delay', 'shipping'],
    'support': ['support', 'staff', 'rude', 'ignored', 'helpful', 'team'],
    'pricing': ['price', 'expensive', 'cost', 'cheap'],
    'product quality': ['broken', 'bug', 'failed', 'app', 'reliable', 'quality']
}
ATTR_WORDS = {
    'Reliable': ['reliable', 'trust', 'works', 'broken', 'bug', 'failed'],
    'Friendly': ['friendly', 'helpful', 'kind', 'rude', 'ignored'],
    'Fast': ['fast', 'quick', 'slow', 'late', 'delay', 'refund']
}

# ---- authority (mirrors the prototype's pw(): powers vanish if the grantee or any ancestor expired) ----
def effective_powers(user, by_username, now_ms=None):
    if now_ms is None: now_ms = int(time.time() * 1000)
    if user['role'] == 0: return list(POWERS)
    a, seen = user, set()
    while a and a['role'] > 0:
        if a['username'] in seen: return []
        seen.add(a['username'])
        if a.get('exp') and now_ms > a['exp']: return []
        a = by_username.get(a.get('by'))
    return [p for p in user.get('pow', []) if p in POWERS]

def can_delegate(grantor, grantor_powers, role, powers):
    """Downward only; cannot hand out powers you do not hold; needs 'authority'."""
    if 'authority' not in grantor_powers: return 'You do not have the authority power.'
    if role <= grantor['role'] or role > 3: return 'Authority can only be passed to a lower role.'
    extra = [p for p in powers if p not in grantor_powers]
    if extra: return 'You cannot give powers you do not hold: ' + ', '.join(extra)
    return None

def subtree(username, users):
    out, stack = [], [username]
    while stack:
        cur = stack.pop()
        for u in users:
            if u.get('by') == cur and u['username'] not in out:
                out.append(u['username'])
                stack.append(u['username'])
    return out

def can_access_post(me, author_id, author_dept):
    """CEO sees everything; authors see their own posts; reviewers/approvers see their own department only.
    `me['powers']` must be the EFFECTIVE powers (expired or taken-back authority grants nothing)."""
    if me['role'] == 0 or author_id == me['id']:
        return True
    has_review = bool({'review', 'approve'} & set(me.get('powers') or []))
    return has_review and author_dept == me.get('department', 'General')

def can_manage_target(me, target, users):
    """A person may only manage people below them in their own delegation chain (the CEO manages anyone but themselves)."""
    if target['username'] == me['username']:
        return False
    if me['role'] == 0:
        return target['role'] != 0
    return target['username'] in subtree(me['username'], users)

# ---- deterministic rule checks ----
def _re(w): return re.compile(r'(?<!\w)' + re.escape(w) + r'(?!\w)', re.I)

def scan(text, rules):
    """Findings, each citing the exact rule id."""
    out = []
    for pair in rules.get('prefer', []) or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2: continue
        a, b = (str(pair[0]).strip(), str(pair[1]).strip())
        if not a or not b: continue
        m = _re(a).search(text)
        if m:
            out.append(dict(
                type='terminology', quote=m.group(0), rule_id=f'RULE:prefer:{a}',
                rule=f'Preferred term: use "{b}" instead of "{a}"',
                headline=f'Say “{b}”, not “{a}”', why='Approved brand terminology.',
                fix=[m.group(0), b], sug=f'Say "{b}".',
                severity='medium', confidence='high', origin='rules', status='pending'
            ))
    for w in rules.get('avoid', []) or []:
        w = str(w).strip()
        if not w: continue
        m = _re(w).search(text)
        if m:
            out.append(dict(
                type='tone', quote=m.group(0), rule_id=f'RULE:avoid:{w}',
                rule=f'Word to avoid: "{w}"',
                headline=f'Avoid “{w}”', why="This word is on the brand's avoid list.",
                fix=[m.group(0), ''], sug=f'Remove or rephrase "{w}".',
                severity='low', confidence='high', origin='rules', status='pending'
            ))
    for w in rules.get('proof', []) or []:
        w = str(w).strip()
        if not w: continue
        m = _re(w).search(text)
        if m:
            out.append(dict(
                type='unsupported_claim', quote=m.group(0), rule_id=f'RULE:proof:{w}',
                rule=f'Claim needs approved evidence: "{w}"',
                headline=f'“{w}” needs proof', why='Promotional claims need an approved source before publishing.',
                fix=None, sug='Add approved proof or remove the claim.',
                severity='high', confidence='high', origin='rules', status='pending'
            ))
    m = re.search(r'!{2,}', text)
    if m:
        out.append(dict(
            type='tone', quote=m.group(0), rule_id='RULE:builtin:exclaim',
            rule='Avoid repeated exclamation marks', headline='Too many exclamation marks',
            why='Reads as shouting.', fix=[m.group(0), '!'],
            sug='Use a single "!".', severity='low', confidence='high', origin='rules', status='pending'
        ))
    m = re.search(r'<img\b(?![^>]*\balt=)[^>]*>', text, re.I)
    if m:
        out.append(dict(
            type='accessibility', quote=m.group(0), rule_id='RULE:builtin:alt',
            rule='Images need alt text (WCAG 1.1.1)', headline='Image has no alt text',
            why='Screen-reader users cannot understand the image.', fix=None,
            sug='Add an alt attribute describing the image.', severity='medium', confidence='high', origin='rules', status='pending'
        ))
    return out

def verify_findings(findings, text, valid_rule_ids):
    """Drop AI findings whose cited rule does not exist or whose quote is not in the text (blocks invented citations)."""
    kept = []
    for f in findings:
        q = str(f.get('quote', '')).strip()
        rid = f.get('rule_id')
        if rid not in valid_rule_ids and f'SRC:{rid}' not in valid_rule_ids:
            continue
        if not q or q.lower() not in text.lower():
            continue
        kept.append(f)
    return kept

def merge_rank(*lists):
    seen, out = set(), []
    for f in [x for l in lists for x in l]:
        k = (f.get('type'), str(f.get('quote', '')).lower())
        if k in seen: continue
        seen.add(k); out.append(f)
    order = {'high': 0, 'medium': 1, 'low': 2}
    return sorted(out, key=lambda f: order.get(f.get('severity'), 3))

def to_ui(f, idx=0):
    """Shape the prototype expects (m, r, fix) plus explanation fields and action tracking."""
    return dict(
        id=idx,
        m=f.get('headline') or f.get('rule', ''),
        r=f.get('rule', ''),
        why=f.get('why', ''),
        sug=f.get('sug', ''),
        fix=f.get('fix'),
        type=f.get('type'),
        quote=f.get('quote', ''),
        sev=f.get('severity'),
        conf=f.get('confidence'),
        origin=f.get('origin'),
        rule_id=f.get('rule_id'),
        status=f.get('status', 'pending'),
        edited=f.get('edited_text', ''),
        source_title=f.get('source_title', ''),
        source_url=f.get('source_url', '')
    )

def score(findings):
    # Only penalize pending or accepted findings (rejected findings don't lower the score)
    penalized = [f for f in findings if f.get('status') != 'rejected']
    return max(0, 10 - sum({'high': 3, 'medium': 2}.get(f.get('severity'), 1) for f in penalized))

def text_hash(t):
    return hashlib.sha256(t.strip().encode()).hexdigest()

# ---- customer voice ----
_PHONE_RE = re.compile(r'(?<![\w.])[+(]?\d[\d\s().-]{7,}\d(?![\w])')
_DATE_LIKE = re.compile(r'^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}')
_PAN_RE = re.compile(r'(?<![A-Z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Z0-9])', re.I)
_AADHAAR_RE = re.compile(r'(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)')

def _phone_sub(m):
    raw = m.group(0)
    digits = re.sub(r'\D', '', raw)
    if not 9 <= len(digits) <= 15: return raw
    if _DATE_LIKE.match(raw.strip()): return raw            # 2024-01-15, 15/01/2024 (+ times)
    has_plus = raw.lstrip().startswith('+')
    has_sep = bool(re.search(r'[\s().-]', raw.strip()))
    indian_mobile = len(digits) == 10 and digits[0] in '6789'
    if has_plus or has_sep or indian_mobile: return '[phone]'
    return raw                                              # bare long numbers (order ids) are left alone

def mask_pii(t):
    t = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '[email]', str(t))
    t = _PAN_RE.sub('[pan]', t)
    t = _AADHAAR_RE.sub('[government-id]', t)
    return _PHONE_RE.sub(_phone_sub, t)

def lexicon_sentiment(text, rating=None):
    w = set(re.findall(r'[a-z]+', text.lower()))
    s = len(w & POSITIVE) - len(w & NEGATIVE)
    if rating: s += (rating - 3)
    return 'positive' if s > 0 else 'negative' if s < 0 else 'neutral'

def lexicon_topic(text):
    t = text.lower()
    for k, ws in TOPICS.items():
        if any(w in t for w in ws): return k
    return 'other'

def parse_csv(raw):
    """Accepts headers like text/review/comment, rating/stars/score, source, date. Returns (rows, skipped)."""
    r = csv.DictReader(io.StringIO(raw.lstrip('\ufeff')))
    names = {(n or '').strip().lower(): n for n in (r.fieldnames or [])}
    pick = lambda *c: next((names[x] for x in c if x in names), None)
    tc, rc, sc, dc = pick('text', 'review', 'comment', 'feedback', 'message'), pick('rating', 'stars', 'score'), pick('source', 'channel'), pick('date', 'created')
    if not tc: raise ValueError('CSV needs a column named text, review, comment or feedback.')
    rows, skipped = [], 0
    for line in r:
        t = (line.get(tc) or '').strip()
        if not t: skipped += 1; continue
        try: rt = min(5, max(1, int(float(line.get(rc) or 3))))
        except (ValueError, OverflowError): rt = 3
        src = ((line.get(sc) or '').strip() or 'CSV') if sc else 'CSV'
        rows.append(dict(source=src, text=t, rating=rt, date=(line.get(dc) or '').strip() if dc else ''))
    return rows, skipped

def perception_gap(feedback, target):
    out = []
    for k, words in ATTR_WORDS.items():
        hit = [f for f in feedback if any(w in f['text'].lower() for w in words)]
        n = len(hit)
        sc = round(sum(f['rating'] for f in hit) / n * 2, 1) if n else None
        tg = target.get(k)
        out.append(dict(
            k=k, n=n, sc=sc, tg=tg,
            g=None if sc is None or tg is None else round(tg - sc, 1),
            reviews=[f['text'] for f in hit[:5]]
        ))
    return out


def norm_ws(t):
    return re.sub(r'\s+', ' ', str(t or '')).strip().lower()

def quote_in(haystack, needle):
    """Whitespace/case-insensitive containment check used to verify cited quotes."""
    n = norm_ws(needle)
    return bool(n) and n in norm_ws(haystack)

# ---- complaint intelligence: deterministic semantic grouping + evaluation ----
_CLUSTER_STOP = {
    'the','and','for','with','this','that','was','were','are','you','your','our','have','has','had',
    'not','but','from','they','them','then','when','what','why','how','can','could','would','should',
    'very','just','too','also','into','about','after','before','there','their','its','is','to',
    'of','in','on','at','a','an','i','we','it','my','me','be','been','being','do','did','does','as',
    'whenever','whenever','keeps','keep','still','never','please','today','days','several','whenever'
}

# Coarse issue signatures provide explainable semantic anchors across different wording/channels.
# A complaint may match more than one category; categories are used as a boost, not as an AI claim.
_COMPLAINT_SIGNATURES = {
    'payment': {'payment','paid','charge','charged','charging','deduct','deducted','debit','debited','billing','transaction'},
    'delivery': {'delivery','shipping','shipment','tracking','parcel','package','courier','late','delay','delayed','arrived','arrival'},
    'app_crash': {'app','application','crash','crashes','crashing','close','closes','closed','closing','launch','freeze','freezes','freezing'},
}
_COMPLAINT_LABELS = {
    'payment': 'Payment Problems',
    'delivery': 'Delivery Delays',
    'app_crash': 'App Crashes',
}


def complaint_tokens(text):
    words = re.findall(r"[a-z0-9]+", str(text or '').lower())
    return [w for w in words if len(w) > 2 and w not in _CLUSTER_STOP]


def complaint_categories(text):
    tokens = set(re.findall(r"[a-z0-9]+", str(text or '').lower()))
    return {category for category, terms in _COMPLAINT_SIGNATURES.items() if tokens & terms}


def _complaint_similarity(a, b):
    from collections import Counter
    ca, cb = Counter(complaint_tokens(a)), Counter(complaint_tokens(b))
    if not ca or not cb: return 0.0
    topics_a, topics_b = complaint_categories(a), complaint_categories(b)
    if topics_a and topics_b and not (topics_a & topics_b):
        return 0.0
    vocab = set(ca) | set(cb)
    dot = sum(ca[w] * cb[w] for w in vocab)
    na = sum(v*v for v in ca.values()) ** .5
    nb = sum(v*v for v in cb.values()) ** .5
    lexical = dot / (na * nb) if na and nb else 0.0
    shared_topics = topics_a & topics_b
    return max(lexical, 0.55 if shared_topics else 0.0)

def group_complaints(rows, threshold=0.34):
    """Greedy cosine grouping. Deterministic and explainable; tune threshold on labelled examples."""
    groups = []
    for row in rows:
        text = str(row.get('text') or '').strip()
        if not text: continue
        best, best_score = None, 0.0
        for group in groups:
            score = max((_complaint_similarity(text, ex['text']) for ex in group['items']), default=0.0)
            if score > best_score: best, best_score = group, score
        if best is not None and best_score >= threshold:
            best['items'].append(row)
        else:
            groups.append({'items': [row]})
    out = []
    from collections import Counter
    for i, group in enumerate(groups):
        items = group['items']; source_counts = Counter(str(x.get('source') or 'Unknown') for x in items)
        words = Counter(w for x in items for w in complaint_tokens(x.get('text', '')))
        topic_counts = Counter(topic for x in items for topic in complaint_categories(x.get('text', '')))
        dominant_topic = topic_counts.most_common(1)[0][0] if topic_counts else None
        label = _COMPLAINT_LABELS.get(dominant_topic) or (' / '.join(w for w, _ in words.most_common(3)) or 'General feedback')
        dated = []
        for x in items:
            raw = x.get('happened_at') or x.get('created_at') or x.get('date') or ''
            try: dated.append(str(raw)[:10])
            except Exception: pass
        out.append({
            'cluster_id': i + 1, 'label': label.title(), 'count': len(items),
            'sources': dict(source_counts), 'examples': [str(x.get('text',''))[:280] for x in items[:3]],
            'trend': _cluster_trend(items), 'first_seen': min(dated) if dated else None,
            'last_seen': max(dated) if dated else None,
            'complaint_ids': [x.get('id') for x in items if x.get('id') is not None]
        })
    return sorted(out, key=lambda x: (-x['count'], x['label']))

def _cluster_trend(items):
    from collections import Counter
    from datetime import date, timedelta
    now = date.today(); recent, previous = 0, 0
    for item in items:
        raw = str(item.get('happened_at') or item.get('created_at') or item.get('date') or '')[:10]
        try: d = date.fromisoformat(raw)
        except (ValueError, TypeError): continue
        if d >= now - timedelta(days=30): recent += 1
        elif d >= now - timedelta(days=60): previous += 1
    if recent > previous: direction = 'rising'
    elif recent < previous: direction = 'falling'
    else: direction = 'stable'
    change = round((recent - previous) / max(previous, 1) * 100)
    return {'direction': direction, 'recent_30d': recent, 'previous_30d': previous, 'change_percent': change}

def evaluate_complaint_groups(rows, labels, threshold=0.34):
    """Pairwise precision/recall/F1 against manually assigned label ids."""
    predicted = {}
    for cluster_no, cluster in enumerate(group_complaints(rows, threshold=threshold)):
        for cid in cluster.get('complaint_ids', []): predicted[cid] = cluster_no
    actual = {int(k): str(v) for k, v in labels.items()}
    ids = [int(r['id']) for r in rows if r.get('id') is not None and int(r['id']) in actual and int(r['id']) in predicted]
    tp = fp = fn = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            same_actual = actual[ids[i]] == actual[ids[j]]
            same_pred = predicted[ids[i]] == predicted[ids[j]]
            if same_actual and same_pred: tp += 1
            elif same_pred: fp += 1
            elif same_actual: fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2*precision*recall/(precision+recall) if precision+recall else 0.0
    return {'labelled_complaints': len(ids), 'true_positive_pairs': tp, 'false_positive_pairs': fp,
            'false_negative_pairs': fn, 'precision': round(precision, 4), 'recall': round(recall, 4), 'f1': round(f1, 4)}

def pii_mask_stats(text):
    original = str(text or '')
    email_count = len(re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', original))
    pan_count = len(_PAN_RE.findall(original))
    aadhaar_matches = list(_AADHAAR_RE.finditer(original))
    phone_matches = list(_PHONE_RE.finditer(original))
    phone_count = sum(1 for m in phone_matches if _phone_sub(m) == '[phone]' and not any(m.start() < a.end() and a.start() < m.end() for a in aadhaar_matches))
    return mask_pii(original), email_count + pan_count + len(aadhaar_matches) + phone_count

def verify_approved_facts(text, facts):
    """Check named fact mentions against approved values. Facts are structured and source-attributed."""
    out, body = [], str(text or '')
    aliases = {
        'product price': ('product price', 'price', 'cost', 'costs'),
        'launch date': ('launch date', 'release date', 'released on', 'launches on', 'launch on', 'launching on'),
        'battery life': ('battery life', 'battery lasts', 'runtime'),
        'refunds': ('refund', 'refunds', 'refund turnaround'),
    }
    for fact in facts or []:
        name, value = str(fact.get('name') or '').strip(), str(fact.get('value') or '').strip()
        if not name or not value: continue
        terms = aliases.get(name.lower(), (name,))
        match = next((re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', body, re.I) for term in terms
                      if re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', body, re.I)), None)
        if not match: continue
        # Compare values in the local clause containing the fact name or alias.
        # Split on sentence punctuation and clause conjunctions, not commas (which
        # may be part of a formatted amount such as ₹1,299) or decimal points.
        pos = match.start()
        boundaries = list(re.finditer(r'[!?;\n]|\.(?=\s|$)|\b(?:and|but|whereas)\b', body, re.I))
        left = max((b.end() for b in boundaries if b.end() <= pos), default=0)
        right = min((b.start() for b in boundaries if b.start() >= pos), default=len(body))
        segment = body[left:right].strip()[:300]
        approved_tokens = re.findall(r'\d+(?:[.,]\d+)*', value)
        observed_tokens = re.findall(r'\d+(?:[.,]\d+)*', segment)
        months = {'january','february','march','april','may','june','july','august','september','october','november','december',
                  'jan','feb','mar','apr','jun','jul','aug','sep','sept','oct','nov','dec'}
        approved_months = set(re.findall(r'[a-z]+', value.lower())) & months
        observed_months = set(re.findall(r'[a-z]+', segment.lower())) & months
        currencies = {'₹':'inr', '$':'usd', '€':'eur', '£':'gbp'}
        approved_currency = next((code for symbol, code in currencies.items() if symbol in value), None)
        observed_currency = next((code for symbol, code in currencies.items() if symbol in segment), None)
        mismatch = bool(approved_tokens and approved_tokens != observed_tokens)
        mismatch = mismatch or bool(approved_months and approved_months != observed_months)
        mismatch = mismatch or bool(approved_currency and approved_currency != observed_currency)
        if mismatch:
            out.append({
                'type': 'incorrect_fact', 'quote': segment.strip()[:500],
                'rule_id': f"FACT:{fact.get('id', name)}", 'rule': f"Approved fact: {name} = {value}",
                'headline': f"Check approved fact: {name}",
                'why': f"The draft appears to state {', '.join(observed_tokens)}, but the approved value is {value}.",
                'fix': None, 'sug': f"Use the approved value: {name} {value}.",
                'severity': 'high', 'confidence': 'high', 'origin': 'approved_fact', 'status': 'pending',
                'source_title': fact.get('source_title') or 'Approved facts',
                'source_url': fact.get('source_url') or ''
            })
    return out
