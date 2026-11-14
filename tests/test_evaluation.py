"""Offline tests for the benchmark's own arithmetic and wiring (no model calls)."""
import os, sys, unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'backend', 'app'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import run_evaluation as E  # noqa: E402


class TestMetrics(unittest.TestCase):
    def test_counts_to_metrics(self):
        r = E.score_counts(tp=8, fp=2, tn=6, fn=4)
        self.assertAlmostEqual(r['precision'], 0.8)
        self.assertAlmostEqual(r['recall'], 8 / 12)
        self.assertAlmostEqual(r['fpr'], 0.25)
        self.assertAlmostEqual(r['f1'], 16 / 22)          # 2TP / (2TP + FP + FN)
        self.assertEqual(r['n'], 20)

    def test_undefined_metrics_are_none_not_zero_or_perfect(self):
        r = E.score_counts(0, 0, 5, 0)
        self.assertIsNone(r['precision']); self.assertIsNone(r['recall']); self.assertIsNone(r['f1'])
        self.assertEqual(r['fpr'], 0.0)

    def test_dataset_is_labelled_consistently(self):
        ids = [s['id'] for s in E.TEST_SAMPLES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(E.TEST_SAMPLES), 52)
        self.assertEqual(sum(1 for s in E.TEST_SAMPLES if not s['has_violation']), 15)


class TestEvaluate(unittest.TestCase):
    S = [dict(text='a', has_violation=True, category='x'), dict(text='b', has_violation=True, category='y'),
         dict(text='c', has_violation=False, category='clean'), dict(text='d', has_violation=False, category='clean')]

    def test_confusion_matrix_and_missed_categories(self):
        r = E.evaluate(lambda t: t in ('a', 'c'), self.S)
        self.assertEqual((r['TP'], r['FP'], r['TN'], r['FN']), (1, 1, 1, 1))
        self.assertEqual(r['missed_by_category'], {'y': '0/1 caught'})

    def test_failed_calls_are_errors_not_clean(self):
        r = E.evaluate(lambda t: None if t == 'a' else False, self.S)
        self.assertEqual(r['errors'], 1)
        self.assertEqual(r['n'], 3)
        self.assertEqual(r['FN'], 1)                      # only 'b'; 'a' is excluded, not counted as a miss

    def test_rules_only_is_real_scanner_output(self):
        r = E.evaluate(E.predict_rules, E.TEST_SAMPLES)
        self.assertEqual((r['FP'], r['TN']), (0, 15))     # clean posts stay clean
        self.assertLess(r['recall'], 1.0)                 # rules alone cannot see fact contradictions
        self.assertIn('fact_contradiction', r['missed_by_category'])


class TestLlmModesAreWiredToTheRealPipeline(unittest.TestCase):
    def test_modes_call_run_ai_review_with_the_right_verify_flag(self):
        calls = []
        def fake(text, sources, recent_complaints=None, verify=True):
            calls.append(verify)
            return [{'type': 'tone', 'quote': 'x', 'severity': 'low'}], True, 'm'
        with mock.patch.object(E.AI, 'run_ai_review', side_effect=fake):
            self.assertTrue(E.make_llm_predictor(False, 0)('hello'))      # raw: model finding alone flags it
            self.assertTrue(E.make_llm_predictor(True, 0)('hello'))
        self.assertEqual(calls, [False, True])

    def test_llm_only_ignores_the_rules_and_failures_are_none(self):
        with mock.patch.object(E.AI, 'run_ai_review', return_value=([], True, 'm')):
            self.assertFalse(E.make_llm_predictor(False, 0)('We are cheap'))     # rules would flag this; LLM-only must not
            self.assertTrue(E.make_llm_predictor(True, 0)('We are cheap'))       # full pipeline adds the rules
        with mock.patch.object(E.AI, 'run_ai_review', return_value=([], False, 'm')):
            self.assertIsNone(E.make_llm_predictor(True, 0)('anything'))

    def test_delay_is_applied_between_calls(self):
        with mock.patch.object(E.AI, 'run_ai_review', return_value=([], True, 'm')), mock.patch.object(E.time, 'sleep') as sl:
            E.make_llm_predictor(True, 3.0)('x')
        sl.assert_called_once_with(3.0)


if __name__ == '__main__':
    unittest.main()
