import sys, unittest, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'app'))
import logic as L
import ai as AI

RULES = {
    'avoid': ['cheap', 'guys'],
    'prefer': [['customers', 'members']],
    'proof': ['#1', 'best', 'guaranteed'],
    'target': {'Reliable': 9, 'Friendly': 8, 'Fast': 8}
}
U = lambda u, role, by=None, pow=(), exp=None: dict(username=u, role=role, by=by, pow=list(pow), exp=exp)

class TestLogic(unittest.TestCase):
    def test_scan_cites_rules(self):
        f = L.scan('Our customers love our cheap #1 service!!', RULES)
        ids = {x['rule_id'] for x in f}
        self.assertTrue({'RULE:prefer:customers', 'RULE:avoid:cheap', 'RULE:proof:#1', 'RULE:builtin:exclaim'} <= ids)
        self.assertEqual(next(x for x in f if x['type'] == 'unsupported_claim')['severity'], 'high')

    def test_scan_clean_and_alt(self):
        self.assertEqual(L.scan('Welcome, members.', RULES), [])
        self.assertEqual(L.scan('<img src="a.png">', RULES)[0]['type'], 'accessibility')
        self.assertEqual(L.scan('<img src="a.png" alt="logo">', RULES), [])

    def test_verify_drops_fake_citations(self):
        t = 'We are fast and friendly.'
        good = dict(rule_id='SRC:1', quote='fast and friendly')
        bad_rule = dict(rule_id='SRC:99', quote='fast')
        bad_quote = dict(rule_id='SRC:1', quote='cheapest ever')
        self.assertEqual(L.verify_findings([good, bad_rule, bad_quote], t, {'SRC:1'}), [good])

    def test_merge_dedupes_and_ranks(self):
        a = [dict(type='tone', quote='X', severity='low')]
        b = [dict(type='tone', quote='x', severity='high'), dict(type='terminology', quote='y', severity='high')]
        m = L.merge_rank(a, b)
        self.assertEqual(len(m), 2)
        self.assertEqual(m[0]['severity'], 'high')

    def test_score_and_rejected_actions(self):
        self.assertEqual(L.score([]), 10)
        # 4 high severity findings: 10 - 4*3 = 0
        self.assertEqual(L.score([dict(severity='high')] * 4), 0)
        # If a finding is rejected by a human reviewer, it should not lower the score
        f_rejected = [dict(severity='high', status='rejected'), dict(severity='low', status='accepted')]
        self.assertEqual(L.score(f_rejected), 9)

    def test_delegation(self):
        ceo = U('ceo', 0)
        head = U('h', 1, 'ceo', ['review', 'approve', 'authority'])
        self.assertIsNone(L.can_delegate(ceo, L.POWERS, 1, ['review']))
        self.assertIn('lower role', L.can_delegate(head, ['authority'], 1, []))
        self.assertIn('do not hold', L.can_delegate(head, ['review', 'authority'], 2, ['approve']))
        self.assertIn('authority power', L.can_delegate(head, ['review'], 2, []))

    def test_expiry_cascades(self):
        users = [U('ceo', 0), U('h', 1, 'ceo', ['review'], exp=1000), U('s', 2, 'h', ['review'])]
        by = {u['username']: u for u in users}
        self.assertEqual(L.effective_powers(by['s'], by, now_ms=500), ['review'])
        self.assertEqual(L.effective_powers(by['s'], by, now_ms=2000), [])
        self.assertEqual(sorted(L.subtree('ceo', users)), ['h', 's'])

    def test_pii_masking(self):
        self.assertEqual(L.mask_pii('mail a.b@x.com or +91 98765 43210'), 'mail [email] or [phone]')

    def test_csv_parser(self):
        rows, sk = L.parse_csv('Review,Stars,Source\nSlow refunds,1,Play\n,3,Play\nGreat team,5,\n')
        self.assertEqual((len(rows), sk, rows[0]['rating'], rows[1]['source']), (2, 1, 1, 'CSV'))
        with self.assertRaises(ValueError): L.parse_csv('a,b\n1,2')

    def test_sentiment_topic_gap(self):
        self.assertEqual(L.lexicon_sentiment('refund was slow and rude', 1), 'negative')
        self.assertEqual(L.lexicon_sentiment('friendly and quick', 5), 'positive')
        self.assertEqual(L.lexicon_topic('slow refunds'), 'refunds')
        fb = [dict(text='Refund was slow', rating=1), dict(text='quick delivery', rating=5)]
        g = {x['k']: x for x in L.perception_gap(fb, RULES['target'])}
        self.assertEqual(g['Fast']['n'], 2)
        self.assertEqual(g['Fast']['sc'], 6.0)
        self.assertEqual(g['Fast']['g'], 2.0)
        self.assertIsNone(g['Reliable']['sc'])

    def test_chunking_and_retrieval(self):
        long_text = "Paragraph one describes our customer promise.\n\nParagraph two details our 48-hour refund policy with no hassle.\n\nParagraph three covers logo sizing rules."
        chunks = AI.chunk_text(long_text, chunk_size=80)
        self.assertGreaterEqual(len(chunks), 3)

        sources = [{'id': 10, 'kind': 'guidelines', 'title': 'Refund Policy', 'content': 'Refund requests are honored within 48 hours.'}]
        top = AI.retrieve_top_k('How do refunds work?', sources, k=1)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]['source_id'], 10)

    def test_wcag_contrast(self):
        black = (0, 0, 0)
        white = (255, 255, 255)
        # Black and white contrast ratio is 21:1
        ratio = AI.contrast_ratio(black, white)
        self.assertGreater(ratio, 20.0)
        # Similar colors contrast ratio < 4.5
        gray1 = (100, 100, 100)
        gray2 = (120, 120, 120)
        self.assertLess(AI.contrast_ratio(gray1, gray2), 4.5)

if __name__ == '__main__':
    unittest.main()

class TestCustomerIntelligence(unittest.TestCase):
    def test_similar_complaints_are_grouped_and_sources_counted(self):
        rows = [
            {'id': 1, 'source': 'Website', 'text': 'Payment failed but money was charged'},
            {'id': 2, 'source': 'Google Play', 'text': 'Money charged but payment failed'},
            {'id': 3, 'source': 'Email', 'text': 'Courier delivery arrived late'},
        ]
        groups = L.group_complaints(rows, threshold=0.25)
        self.assertEqual(sum(g['count'] for g in groups), 3)
        payment = next(g for g in groups if g['count'] == 2)
        self.assertEqual(payment['sources'], {'Website': 1, 'Google Play': 1})
        self.assertEqual(len(payment['examples']), 2)

    def test_manual_cluster_evaluation(self):
        rows = [
            {'id': 1, 'source': 'A', 'text': 'Payment failed money charged'},
            {'id': 2, 'source': 'B', 'text': 'Money charged payment failed'},
            {'id': 3, 'source': 'A', 'text': 'Delivery parcel arrived late'},
        ]
        result = L.evaluate_complaint_groups(rows, {'1':'payment','2':'payment','3':'delivery'}, threshold=0.25)
        self.assertEqual(result['labelled_complaints'], 3)
        self.assertGreaterEqual(result['f1'], 0.0)
        self.assertLessEqual(result['f1'], 1.0)

    def test_approved_fact_detects_numeric_mismatch_and_accepts_correct_value(self):
        facts = [{'id': 7, 'name': 'Product price', 'value': '₹999', 'source_title': 'Approved price sheet'}]
        bad = L.verify_approved_facts('Product price is ₹1,299 today.', facts)
        good = L.verify_approved_facts('Product price is ₹999 today.', facts)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]['type'], 'incorrect_fact')
        self.assertEqual(bad[0]['source_title'], 'Approved price sheet')
        self.assertEqual(good, [])

    def test_pii_masking_counts_multiple_items(self):
        masked, count = L.pii_mask_stats('Contact a@example.com and b@example.com or +91 98765 43210')
        self.assertEqual(count, 3)
        self.assertNotIn('a@example.com', masked)
        self.assertNotIn('98765', masked)

    def test_retrieval_preserves_custom_approved_fact_citation_id(self):
        sources = [{'id': -5, 'rule_id': 'FACT:5', 'kind': 'facts', 'title': 'Price sheet', 'content': 'Product price: ₹999'}]
        chunks = AI.retrieve_top_k('Product price', sources, k=1)
        self.assertEqual(chunks[0]['rule_id'], 'FACT:5')

    def test_approved_fact_checks_month_and_currency_not_only_digits(self):
        facts = [
            {'id': 8, 'name': 'Launch date', 'value': '15 December 2026', 'source_title': 'Launch plan'},
            {'id': 9, 'name': 'Product price', 'value': '₹999', 'source_title': 'Price sheet'},
        ]
        text = 'Launch date is 15 November 2026. Product price is $999.'
        findings = L.verify_approved_facts(text, facts)
        self.assertEqual(len(findings), 2)

    def test_mask_pii_masks_indian_pan_and_aadhaar_patterns(self):
        masked, count = L.pii_mask_stats('PAN ABCDE1234F Aadhaar 2345 6789 1234')
        self.assertIn('[pan]', masked)
        self.assertIn('[government-id]', masked)
        self.assertEqual(count, 2)
