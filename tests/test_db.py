import pytest

from brewops.db.connection import connect
from brewops.db.queries import (
    get_drink_types,
    get_machine_health,
    get_machines,
    get_stats,
    insert_brew,
    insert_maintenance,
)
from brewops.db.schema import init_db, reset_db


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


def test_init_is_idempotent(conn):
    init_db(conn)
    init_db(conn)
    assert len(get_machines(conn)) == 4
    assert len(get_drink_types(conn)) == 6


def test_reference_data_seeded(conn):
    machines = {m["name"]: m for m in get_machines(conn)}
    assert "Bertha (3rd floor)" in machines
    assert machines["Old Faithful (2nd floor)"]["has_telemetry"] is False
    drinks = {d["name"] for d in get_drink_types(conn)}
    assert "espresso" in drinks


def test_stats_math(conn):
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.5, 92.0, "csv")
    insert_brew(conn, 1, "espresso", "2026-06-01 09:00:00", 26.0, 91.5, "csv")
    insert_brew(conn, 2, "latte", "2026-06-02 10:00:00", 44.0, 88.0, "csv")
    insert_brew(conn, 3, "lungo", "2026-06-02 11:00:00", 38.0, 90.0, "manual")
    conn.commit()

    stats = get_stats(conn)
    assert stats["total_brews"] == 4
    per_drink = {d["name"]: d["count"] for d in stats["per_drink"]}
    assert per_drink["espresso"] == 2
    assert per_drink["latte"] == 1
    assert per_drink["cappuccino"] == 0
    per_day = {d["day"]: d["count"] for d in stats["per_day"]}
    assert per_day == {"2026-06-01": 2, "2026-06-02": 2}

    # Test date_from filter: only 2026-06-02
    stats_filtered = get_stats(conn, date_from="2026-06-02")
    assert stats_filtered["total_brews"] == 2
    per_drink_filtered = {d["name"]: d["count"] for d in stats_filtered["per_drink"]}
    assert per_drink_filtered["espresso"] == 0
    assert per_drink_filtered["latte"] == 1
    assert per_drink_filtered["lungo"] == 1
    per_day_filtered = {d["day"]: d["count"] for d in stats_filtered["per_day"]}
    assert per_day_filtered == {"2026-06-02": 2}

    # Test date_to filter: only 2026-06-01
    stats_to = get_stats(conn, date_to="2026-06-01")
    assert stats_to["total_brews"] == 2
    per_day_to = {d["day"]: d["count"] for d in stats_to["per_day"]}
    assert per_day_to == {"2026-06-01": 2}

    # Test both: exact single day
    stats_single = get_stats(conn, date_from="2026-06-01", date_to="2026-06-01")
    assert stats_single["total_brews"] == 2
    per_day_single = {d["day"]: d["count"] for d in stats_single["per_day"]}
    assert per_day_single == {"2026-06-01": 2}


def test_machine_health(conn):
    insert_brew(conn, 4, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_maintenance(conn, 4, "descale", "2026-06-03 18:00:00", note="quarterly descale")
    insert_maintenance(conn, 4, "error", "2026-06-04 09:15:00", error_code="E42")
    conn.commit()

    health = get_machine_health(conn, 4)
    assert health["brew_count"] == 1
    assert health["last_brew"] == "2026-06-01 08:00:00"
    assert health["last_maintenance"]["type"] == "descale"
    assert health["recent_errors"][0]["error_code"] == "E42"


def test_machine_health_unknown_machine(conn):
    assert get_machine_health(conn, 999) is None


def test_stats_empty_range(conn):
    """Test that an empty date range returns zero brews, zero-filled per_drink, and empty per_day."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.5, 92.0, "csv")
    conn.commit()

    # Query a date range with no brews in it
    stats = get_stats(conn, date_from="1900-01-01", date_to="1900-01-02")
    assert stats["total_brews"] == 0
    per_drink = {d["name"]: d["count"] for d in stats["per_drink"]}
    assert per_drink["espresso"] == 0
    assert per_drink["cappuccino"] == 0
    assert per_drink["latte"] == 0
    assert stats["per_day"] == []


def test_reset_db_clears_events(conn):
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    conn.commit()
    reset_db(conn)
    assert get_stats(conn)["total_brews"] == 0
    assert len(get_machines(conn)) == 4
