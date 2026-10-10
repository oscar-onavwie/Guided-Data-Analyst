"""HTTP-level tests through FastAPI's TestClient.

Skipped automatically if FastAPI is not installed (pip install -r requirements-dev.txt).
"""

import pytest
from conftest import xlsx_bytes

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(create_app(Settings()))


def upload(client, content: bytes, name: str, sheet: str | None = None):
    data = {"sheet": sheet} if sheet else None
    return client.post("/api/datasets", files={"file": (name, content, "application/octet-stream")}, data=data)


def test_health_and_config(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    cfg = client.get("/api/config").json()
    assert cfg["ai_available"] is False and "memory" in cfg["data_retention"]
    assert {d["key"] for d in client.get("/api/demo-datasets").json()} == {"small-business", "retail", "workforce"}


def test_full_journey_csv(client):
    rows = "\n".join(f"2025-{1 + i % 12:02d}-15,{['N', 'S', 'E'][i % 3]},{10 + i}" for i in range(48))
    r = upload(client, ("date,region,sales\n" + rows + "\n").encode(), "sales.csv")
    assert r.status_code == 201, r.text
    ds = r.json()
    did = ds["dataset_id"]
    assert ds["rows"] == 48 and ds["is_demo"] is False
    assert r.headers["x-content-type-options"] == "nosniff"

    assert client.get(f"/api/datasets/{did}/profile").json()["rows"] == 48
    analysis = client.get(f"/api/datasets/{did}/analysis").json()
    assert analysis["measures"] == ["sales"] and analysis["default_timeseries"]["granularity"] == "month"
    g = client.post(f"/api/datasets/{did}/explore/grouped", json={"category_column": "region", "value_column": "sales"}).json()
    assert sum(row["count"] for row in g["rows"]) == 48
    ts = client.post(
        f"/api/datasets/{did}/explore/timeseries", json={"date_column": "date", "agg": "count", "granularity": "quarter"}
    ).json()
    assert [p["count"] for p in ts["points"]] == [12, 12, 12, 12]
    assert "findings" in client.get(f"/api/datasets/{did}/findings").json()

    rep = client.get(f"/api/datasets/{did}/report.html")
    assert rep.status_code == 200 and "attachment" in rep.headers["content-disposition"]
    assert "default-src 'none'" in rep.headers["content-security-policy"]
    assert "sales.csv" in rep.text

    exp = client.get(f"/api/datasets/{did}/export/numeric_summary.csv")
    assert exp.status_code == 200 and exp.headers["content-type"].startswith("text/csv")
    assert "sales" in exp.text

    assert client.delete(f"/api/datasets/{did}").status_code == 204
    gone = client.get(f"/api/datasets/{did}/profile")
    assert gone.status_code == 404 and gone.json()["error"]["code"] == "dataset_not_found"


def test_excel_sheet_selection(client):
    data = xlsx_bytes({"One": [["a"], [1]], "Two": [["b"], [2], [3]]})
    sheets = client.post("/api/files/sheets", files={"file": ("b.xlsx", data, "application/octet-stream")}).json()
    assert sheets["sheets"] == ["One", "Two"]
    r = upload(client, data, "b.xlsx")
    assert r.status_code == 422 and r.json()["error"]["code"] == "sheet_required"
    r = upload(client, data, "b.xlsx", sheet="Two")
    assert r.status_code == 201 and r.json()["rows"] == 2


@pytest.mark.parametrize(
    "content,name,status,code",
    [
        (b"", "empty.csv", 422, "empty_file"),
        (b"a,b\n1,2\n", "notes.txt", 415, "unsupported_file_type"),
        (b"a,b\n1,2\n", "fake.xlsx", 422, "invalid_excel_file"),
        (b"a,b\n1,2\n3,4,5\n", "bad.csv", 422, "malformed_csv"),
    ],
)
def test_upload_errors_have_consistent_shape(client, content, name, status, code):
    r = upload(client, content, name)
    assert r.status_code == status
    body = r.json()["error"]
    assert body["code"] == code and body["message"]


def test_oversized_upload_rejected(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    c = TestClient(create_app(Settings()))
    r = upload(c, b"a\n" + b"1\n" * (700 * 1024), "big.csv")
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_validation_errors(client):
    r = client.post("/api/datasets")  # no file
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    demo = client.post("/api/demo-datasets/retail").json()
    r = client.post(f"/api/datasets/{demo['dataset_id']}/explore/scatter", json={"x": "category", "y": "revenue"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_numeric"
    assert client.get(f"/api/datasets/{demo['dataset_id']}/export/nope.csv").status_code == 404
    assert client.post("/api/demo-datasets/..%2F..%2Fetc").status_code == 404


def test_ai_endpoint_unconfigured(client):
    demo = client.post("/api/demo-datasets/retail").json()
    r = client.post(f"/api/datasets/{demo['dataset_id']}/ai-explanation", json={"consent": True})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_not_configured"
