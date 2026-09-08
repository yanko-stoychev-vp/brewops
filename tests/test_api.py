import pytest

from brewops.api.main import app
from brewops.db.connection import connect
from brewops.db.queries import insert_brew, insert_maintenance
from brewops.db.schema import init_db

from asgi_client import request


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "api-test.db"
    monkeypatch.setenv("BREWOPS_DB", str(path))
    conn = connect(path)
    init_db(conn)
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.5, 92.0, "csv")
    insert_brew(conn, 1, "espresso", "2026-06-01 09:00:00", 26.0, 91.5, "csv")
    insert_brew(conn, 2, "latte", "2026-06-02 10:00:00", 44.0, 88.0, "csv")
    insert_maintenance(conn, 1, "descale", "2026-06-03 18:00:00", note="quarterly")
    conn.commit()
    yield conn
    conn.close()


def test_stats(db):
    r = request(app, "GET", "/api/stats")
    assert r.status == 200
    stats = r.json()
    assert stats["total_brews"] == 3
    per_drink = {d["name"]: d["count"] for d in stats["per_drink"]}
    assert per_drink["espresso"] == 2
    assert {d["day"]: d["count"] for d in stats["per_day"]} == {
        "2026-06-01": 2,
        "2026-06-02": 1,
    }

    # Test date_from filter: only 2026-06-02
    r = request(app, "GET", "/api/stats?date_from=2026-06-02")
    assert r.status == 200
    stats = r.json()
    assert stats["total_brews"] == 1
    assert {d["day"]: d["count"] for d in stats["per_day"]} == {"2026-06-02": 1}

    # Test date_to filter: only 2026-06-01
    r = request(app, "GET", "/api/stats?date_to=2026-06-01")
    assert r.status == 200
    stats = r.json()
    assert stats["total_brews"] == 2
    assert {d["day"]: d["count"] for d in stats["per_day"]} == {"2026-06-01": 2}

    # Test both: single day
    r = request(app, "GET", "/api/stats?date_from=2026-06-01&date_to=2026-06-01")
    assert r.status == 200
    stats = r.json()
    assert stats["total_brews"] == 2

    # Test error: date_from after date_to
    r = request(app, "GET", "/api/stats?date_from=2026-06-10&date_to=2026-06-01")
    assert r.status == 400
    assert "date_from" in r.json()["detail"]

    # Test error: malformed date_from
    r = request(app, "GET", "/api/stats?date_from=not-a-date")
    assert r.status == 400
    assert "date_from" in r.json()["detail"]

    # Test error: malformed date_to
    r = request(app, "GET", "/api/stats?date_to=2026/06/01")
    assert r.status == 400
    assert "date_to" in r.json()["detail"]

    # Test empty range: valid dates with no brews
    r = request(app, "GET", "/api/stats?date_from=1900-01-01&date_to=1900-01-02")
    assert r.status == 200
    stats = r.json()
    assert stats["total_brews"] == 0
    per_drink = {d["name"]: d["count"] for d in stats["per_drink"]}
    assert per_drink["espresso"] == 0
    assert stats["per_day"] == []


def test_machines_list_and_health(db):
    r = request(app, "GET", "/api/machines")
    assert r.status == 200
    assert len(r.json()) == 4

    r = request(app, "GET", "/api/machines/1")
    assert r.status == 200
    health = r.json()
    assert health["brew_count"] == 2
    assert health["last_maintenance"]["type"] == "descale"


def test_machine_health_404(db):
    r = request(app, "GET", "/api/machines/999")
    assert r.status == 404


def test_drink_types(db):
    r = request(app, "GET", "/api/drink-types")
    assert r.status == 200
    assert {d["name"] for d in r.json()} >= {"espresso", "latte", "cappuccino"}


def test_post_brew_ok_and_visible_in_stats(db):
    r = request(app, "POST", "/api/brews", {
        "machine_id": 3,
        "drink_type": "lungo",
        "timestamp": "2026-06-05 14:30:00",
    })
    assert r.status == 200, r.text
    assert r.json()["status"] == "logged"

    row = db.execute("SELECT source, duration_s FROM brew_events WHERE machine_id = 3").fetchone()
    assert row["source"] == "manual"
    assert row["duration_s"] is None

    stats = request(app, "GET", "/api/stats").json()
    assert stats["total_brews"] == 4


def test_post_brew_accepts_html_form_timestamp(db):
    r = request(app, "POST", "/api/brews", {
        "machine_id": 1,
        "drink_type": "espresso",
        "timestamp": "2026-06-05T14:30",
    })
    assert r.status == 200, r.text
    row = db.execute(
        "SELECT timestamp FROM brew_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["timestamp"] == "2026-06-05 14:30:00"


@pytest.mark.parametrize(
    "payload,fragment",
    [
        ({"machine_id": 99, "drink_type": "espresso", "timestamp": "2026-06-05 14:30:00"}, "unknown machine"),
        ({"machine_id": 1, "drink_type": "unicorn_frappe", "timestamp": "2026-06-05 14:30:00"}, "unknown drink"),
        ({"machine_id": 1, "drink_type": "espresso", "timestamp": "2099-01-01 00:00:00"}, "future"),
        ({"machine_id": 1, "drink_type": "espresso", "timestamp": "yesterday-ish"}, "unparsable"),
    ],
)
def test_post_brew_validation(db, payload, fragment):
    r = request(app, "POST", "/api/brews", payload)
    assert r.status == 400
    assert fragment in r.json()["detail"]


def test_post_maintenance(db):
    r = request(app, "POST", "/api/maintenance", {
        "machine_id": 2,
        "type": "descale",
        "timestamp": "2026-06-06 09:00:00",
        "note": "smelled funny",
    })
    assert r.status == 200
    r = request(app, "POST", "/api/maintenance", {
        "machine_id": 2,
        "type": "exploded",
        "timestamp": "2026-06-06 09:00:00",
    })
    assert r.status == 400


def test_export_brews_csv(db):
    import csv

    r = request(app, "GET", "/api/export/brews.csv")
    assert r.status == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in r.headers["content-disposition"]

    body = r.text
    reader = csv.DictReader(body.splitlines())
    rows = list(reader)

    # Check header
    assert reader.fieldnames == ["timestamp", "machine", "drink", "duration_s", "temp_c", "source"]

    # Check we got all 3 brews
    assert len(rows) == 3

    # Verify first brew (espresso on 2026-06-01)
    assert rows[0]["timestamp"] == "2026-06-01 08:00:00"
    assert rows[0]["machine"] == "Bertha (3rd floor)"  # Machine 1 is Bertha
    assert rows[0]["drink"] == "Espresso"  # drink_type espresso has label Espresso
    assert rows[0]["source"] == "csv"

    # Verify last brew (latte on 2026-06-02)
    assert rows[2]["timestamp"] == "2026-06-02 10:00:00"
    assert rows[2]["machine"] == "The Intern (kitchen)"  # Machine 2 is The Intern
    assert rows[2]["drink"] == "Latte"


def test_export_brews_csv_with_date_filters(db):
    import csv

    # Test with date_from filter
    r = request(app, "GET", "/api/export/brews.csv?date_from=2026-06-02")
    assert r.status == 200
    reader = csv.DictReader(r.text.splitlines())
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2026-06-02 10:00:00"

    # Verify filename includes date range
    assert "2026-06-02" in r.headers["content-disposition"]

    # Test with date_to filter
    r = request(app, "GET", "/api/export/brews.csv?date_to=2026-06-01")
    assert r.status == 200
    reader = csv.DictReader(r.text.splitlines())
    rows = list(reader)
    assert len(rows) == 2

    # Test with both filters
    r = request(app, "GET", "/api/export/brews.csv?date_from=2026-06-01&date_to=2026-06-01")
    assert r.status == 200
    reader = csv.DictReader(r.text.splitlines())
    rows = list(reader)
    assert len(rows) == 2
    # Verify row count matches stats for same date range
    stats = request(app, "GET", "/api/stats?date_from=2026-06-01&date_to=2026-06-01").json()
    assert len(rows) == stats["total_brews"]


def test_export_brews_csv_invalid_date_range(db):
    # Test invalid date_from format
    r = request(app, "GET", "/api/export/brews.csv?date_from=not-a-date")
    assert r.status == 400
    assert "date_from" in r.json()["detail"]

    # Test date_from after date_to
    r = request(app, "GET", "/api/export/brews.csv?date_from=2026-06-10&date_to=2026-06-01")
    assert r.status == 400
    assert "date_from" in r.json()["detail"]
