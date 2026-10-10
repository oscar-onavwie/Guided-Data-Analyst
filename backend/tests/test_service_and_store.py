from datetime import timedelta

import pytest
from conftest import csv_bytes, xlsx_bytes

from app import service
from app.config import Settings
from app.errors import AppError
from app.store import SessionStore


@pytest.fixture
def store(settings):
    return SessionStore(settings)


def test_upload_flow_end_to_end(store, settings):
    rows = "\n".join(f"2025-{1 + i % 12:02d}-{1 + i % 28:02d},{['N', 'S'][i % 2]},{i * 3}" for i in range(60))
    summary = service.load_upload(store, csv_bytes("date,region,sales\n" + rows + "\n"), "my data.csv", settings)
    assert summary.rows == 60 and summary.columns == 3 and not summary.is_demo
    assert len(summary.preview.rows) == 50 and summary.preview.total_rows == 60
    s = store.get(summary.dataset_id)
    assert service.get_profile(s).rows == 60
    assert service.get_analysis(s).measures == ["sales"]
    assert service.get_findings(s) is service.get_findings(s)  # cached
    html = service.report_html(s)
    assert "my data.csv" in html
    assert service.report_filename(s, "html") == "my-data-analysis.html"


def test_demo_datasets_labelled(store, settings):
    for key in service.DEMO_DATASETS:
        summary = service.load_demo(store, key, settings)
        assert summary.is_demo and summary.demo_key == key
        assert service.report_filename(store.get(summary.dataset_id), "html").startswith("DEMO-")


def test_unknown_demo_key_cannot_traverse(store, settings):
    with pytest.raises(AppError) as e:
        service.load_demo(store, "../../etc/passwd", settings)
    assert e.value.code == "demo_not_found"


def test_sheet_listing(settings):
    data = xlsx_bytes({"A": [["x"], [1]], "B": [["y"], [2]]})
    assert service.sheets_for_upload(data, "b.xlsx", settings).sheets == ["A", "B"]
    assert service.sheets_for_upload(b"a\n1\n", "c.csv", settings).sheets == []


def test_preview_paging_validation(store, settings):
    summary = service.load_upload(store, csv_bytes("a\n1\n2\n3\n"), "t.csv", settings)
    s = store.get(summary.dataset_id)
    assert service.preview(s, 1, 1).rows == [["2"]]
    with pytest.raises(AppError):
        service.preview(s, -1, 10)
    with pytest.raises(AppError):
        service.preview(s, 0, 1000)


def test_explore_validation_errors(store, settings):
    summary = service.load_upload(store, csv_bytes("team,score\nA,1\nB,2\n"), "t.csv", settings)
    s = store.get(summary.dataset_id)
    with pytest.raises(AppError) as e:
        service.explore_grouped(s, "missing", "score")
    assert e.value.status == 404
    with pytest.raises(AppError) as e:
        service.explore_scatter(s, "team", "score")
    assert e.value.code == "not_numeric"


def test_ai_requires_consent(store, settings):
    summary = service.load_upload(store, csv_bytes("a,b\nx,1\ny,2\n"), "t.csv", settings)
    with pytest.raises(AppError) as e:
        service.ai_explain(store.get(summary.dataset_id), settings, consent=False)
    assert e.value.code == "consent_required"


def test_sessions_expire_and_evict(monkeypatch):
    monkeypatch.setenv("MAX_SESSIONS", "2")
    s = Settings()
    st = SessionStore(s)
    ids = [service.load_upload(st, csv_bytes("a\n1\n"), f"{i}.csv", s).dataset_id for i in range(3)]
    assert len(st) == 2
    with pytest.raises(AppError) as e:
        st.get(ids[0])  # least recently used was evicted
    assert e.value.code == "dataset_not_found"
    sess = st.get(ids[1])
    sess.last_used -= timedelta(minutes=s.session_ttl_minutes + 1)
    with pytest.raises(AppError):
        st.get(ids[1])
    assert st.delete(ids[2]) is True and len(st) == 0


def test_dataset_ids_are_random_and_long(store, settings):
    ids = {service.load_upload(store, csv_bytes("a\n1\n"), "t.csv", settings).dataset_id for _ in range(5)}
    assert len(ids) == 5 and all(len(i) >= 20 for i in ids)
