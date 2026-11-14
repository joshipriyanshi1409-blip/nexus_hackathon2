"""Offline checks for the simulated Gmail and Play Store connector demo."""
from backend.demo_connectors import demo_feedback_rows
from backend.app.main import preview_feedback_cleaning, _clean_feedback_rows, _dedupe_feedback_rows


def test_demo_connectors_are_explicitly_synthetic_and_have_both_sources():
    rows = demo_feedback_rows()
    assert len(rows) == 10
    assert {row['source'] for row in rows} == {'Demo Gmail', 'Demo Google Play'}
    assert all(str(row['external_id']).startswith('demo_connector:') for row in rows)


def test_demo_connector_rows_use_same_pii_and_duplicate_cleaning_pipeline():
    rows = demo_feedback_rows()
    preview = preview_feedback_cleaning(rows)
    assert preview['input_rows'] == 10
    assert preview['accepted_rows'] == 8
    assert preview['duplicates_removed'] == 2
    assert preview['pii_items_masked'] >= 2
    assert preview['persisted'] is False
    assert all('demo.customer@example.com' not in row['text'] for row in preview['preview'])
    assert all('+91 98765 43210' not in row['text'] for row in preview['preview'])


def test_demo_connector_rerun_is_idempotent_for_existing_rows():
    clean, _ = _clean_feedback_rows(demo_feedback_rows())
    first_batch, first_duplicates = _dedupe_feedback_rows(clean)
    second_batch, second_duplicates = _dedupe_feedback_rows(clean, first_batch)
    assert len(first_batch) == 8
    assert first_duplicates == 2
    assert second_batch == []
    assert second_duplicates == 10


def test_demo_sync_api_is_ceo_only_and_returns_simulation_notice(monkeypatch):
    from backend.app import main
    captured = {}

    def fake_save(rows, use_llm=True, return_details=False):
        captured['rows'] = rows
        captured['use_llm'] = use_llm
        captured['return_details'] = return_details
        return {'imported': 8, 'duplicates': 2, 'pii_redactions': 4}

    monkeypatch.setattr(main, 'save_feedback', fake_save)
    monkeypatch.setattr(main, 'audit', lambda *args, **kwargs: None)
    result = main.sync_demo_feedback_connectors({'powers': ['voice'], 'role': 0, 'id': 'demo-ceo'})

    assert result['demo'] is True
    assert 'SIMULATED DATA ONLY' in result['notice']
    assert 'demo/test workspace' in result['notice']
    assert 'not automatically deleted' in result['notice']
    assert result['imported'] == 8
    assert captured['use_llm'] is False
    assert captured['return_details'] is True
    assert len(captured['rows']) == 10

    from fastapi import HTTPException
    try:
        main.sync_demo_feedback_connectors({'powers': ['voice'], 'role': 1, 'id': 'demo-head'})
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError('Non-CEO should not be allowed to run connector sync')


def test_demo_preview_endpoint_masks_pii_and_separates_inbox_from_reviews():
    from backend.app import main
    result = main.preview_demo_feedback_connectors({'powers': ['voice']})
    assert result['demo'] is True
    assert len(result['gmail']) == 4
    assert len(result['google_play']) == 4
    assert 'demo.customer@example.com' not in str(result)
    assert '+91 98765 43210' not in str(result)
    assert all(item.get('subject') for item in result['gmail'])
    assert all(1 <= item.get('rating', 0) <= 5 for item in result['google_play'])
