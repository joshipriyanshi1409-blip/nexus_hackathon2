"""Offline regression tests for the public judge fixtures and their disclosed scores."""
import json
from datetime import date, timedelta
from pathlib import Path

from backend.app import logic as L
from backend.demo_fixtures import COMPLAINTS

ROOT = Path(__file__).resolve().parents[1]


def _complaint_rows():
    today = date.today()
    rows, labels = [], {}
    for idx, (group, source, text, rating, days_ago) in enumerate(COMPLAINTS, start=1):
        rows.append({
            'id': idx, 'source': source, 'text': text, 'rating': rating,
            'happened_at': (today - timedelta(days=days_ago)).isoformat(),
        })
        labels[str(idx)] = group
    return rows, labels


def test_judge_complaint_fixture_has_three_explainable_groups_and_trends():
    rows, labels = _complaint_rows()
    groups = L.group_complaints(rows)
    by_label = {g['label']: g for g in groups}
    assert {k: v['count'] for k, v in by_label.items()} == {
        'Payment Problems': 6, 'Delivery Delays': 5, 'App Crashes': 4,
    }
    assert by_label['Payment Problems']['trend']['direction'] == 'rising'
    assert by_label['Delivery Delays']['trend']['direction'] == 'falling'
    assert by_label['App Crashes']['trend']['direction'] == 'stable'
    assert sum(sum(g['sources'].values()) for g in groups) == 15
    result = L.evaluate_complaint_groups(rows, labels)
    assert result == {
        'labelled_complaints': 15, 'true_positive_pairs': 31,
        'false_positive_pairs': 0, 'false_negative_pairs': 0,
        'precision': 1.0, 'recall': 1.0, 'f1': 1.0,
    }


def test_judge_fact_benchmark_is_52_posts_with_five_fact_contradictions():
    fixture = json.loads((ROOT / 'backend/data/judge_fact_benchmark_52.json').read_text(encoding='utf-8'))
    assert fixture['posts_count'] == 52
    assert len(fixture['posts']) == 52
    assert sum(bool(row['wrong_fact']) for row in fixture['posts']) == 5
    assert sum(not bool(row['wrong_fact']) for row in fixture['posts']) == 47
    facts = [dict(row, id=index + 1) for index, row in enumerate(fixture['facts'])]
    detected = {i for i, row in enumerate(fixture['posts']) if L.verify_approved_facts(row['text'], facts)}
    truth = {i for i, row in enumerate(fixture['posts']) if row['wrong_fact']}
    assert detected == truth
    baseline = [row for row in fixture['posts'] if row.get('baseline_detected') is not None]
    assert len(baseline) == 52
    assert sum(bool(row['baseline_detected']) for row in baseline) == 1


def test_fact_verifier_supports_common_price_and_launch_date_aliases():
    facts = [
        {'id': 1, 'name': 'Product price', 'value': '₹999', 'source_title': 'ECHO demo catalogue'},
        {'id': 2, 'name': 'Launch date', 'value': '18 December 2026', 'source_title': 'ECHO demo plan'},
    ]
    assert len(L.verify_approved_facts('The item costs ₹1,299.', facts)) == 1
    assert len(L.verify_approved_facts('We launch on 19 December 2026.', facts)) == 1
    assert L.verify_approved_facts('The item costs ₹999 and launches on 18 December 2026.', facts) == []


def test_demo_pii_sample_contains_maskable_email_and_phone():
    sample_text = COMPLAINTS[0][2]
    masked, redactions = L.pii_mask_stats(sample_text)
    assert redactions >= 2
    assert 'demo.customer@example.com' not in masked
    assert '+91 98765 43210' not in masked


def test_sample_feedback_preview_uses_production_cleaning_without_persisting():
    from backend.app.main import preview_feedback_cleaning
    sample_text = COMPLAINTS[0][2]
    rows = [
        {'source':'Google Play', 'text':sample_text, 'external_id':'preview:play:1'},
        {'source':'Google Play', 'text':sample_text, 'external_id':'preview:play:2'},
        {'source':'Website', 'text':sample_text, 'external_id':'preview:website:1'},
    ]
    result = preview_feedback_cleaning(rows)
    assert result['input_rows'] == 3
    assert result['accepted_rows'] == 2
    assert result['duplicates_removed'] == 1
    assert result['pii_items_masked'] == 6
    assert result['persisted'] is False
    assert all('demo.customer@example.com' not in row['text'] for row in result['preview'])


def test_fact_findings_keep_approved_source_and_suggested_correction_in_api_shape():
    facts = [{
        'id': 7, 'name': 'Product price', 'value': '₹999',
        'source_title': 'Approved price list', 'source_url': 'https://example.com/prices',
    }]
    finding = L.verify_approved_facts('Product price is ₹1,299.', facts)[0]
    ui = L.to_ui(finding)
    assert ui['source_title'] == 'Approved price list'
    assert ui['source_url'] == 'https://example.com/prices'
    assert ui['sug'] == 'Use the approved value: Product price ₹999.'


def test_public_judges_page_keeps_all_existing_role_accounts():
    html = (ROOT / 'frontend' / 'brandhub.html').read_text(encoding='utf-8')
    for username in ('itz_ceo', 'twlightt', 'finding_nemo', 'the_dark_knight', 'godfather', 'hannibal'):
        assert username in html
    assert 'function judgesScreen()' in html
    assert 'Fill judge demo credentials' not in html


def test_judges_page_displays_all_hackathon_credentials_and_has_direct_sign_in():
    html = (ROOT / 'frontend' / 'brandhub.html').read_text(encoding='utf-8')
    expected = {
        'itz_ceo': 'Inkloom#Admin2026',
        'twlightt': 'kuchbhi123',
        'finding_nemo': 'Ellen_DeGeneres',
        'godfather': 'al_pacino',
        'the_dark_knight': 'heath_ledger',
        'hannibal': 'Mads_Mikkelsen',
    }
    for username, password in expected.items():
        assert username in html
        assert password in html
    assert 'function loginJudgeAccount(username,password)' in html
    assert "api('/login','POST',{username,password})" in html
    assert 'function copyJudgeAccount(username,password)' in html


def test_workspace_has_sidebar_theme_and_post_delete_controls():
    html = (ROOT / 'frontend' / 'brandhub.html').read_text(encoding='utf-8')
    assert 'class="app-sidebar"' in html
    assert 'function toggleSidebar()' in html
    assert 'function toggleTheme()' in html
    assert "localStorage.setItem('echo-theme',next)" in html
    assert "api('/posts/'+id,'DELETE')" in html
    assert "aria-label=" + '"Delete post ${p.id}"' in html
    assert "S.posts.filter(p=>!isMine(p)" in html
    assert 'Brand writing standards' in html
    assert 'What gets checked' in html
    assert 'AI and human review' not in html
    assert 'Connected to Google Gemini' not in html
    assert 'gemini-3.8-flash' not in html
    assert 'AI connected' not in html
    assert 'class="vault-folder-grid"' in html
    assert 'function filterVault(query)' in html
    assert 'Folder permissions' in html
