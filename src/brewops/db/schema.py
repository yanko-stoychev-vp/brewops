"""Schema and reference data.

Timestamps are stored as naive local time, 'YYYY-MM-DD HH:MM:SS'.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS machines (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    floor         INTEGER NOT NULL,
    has_telemetry INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS drink_types (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS brew_events (
    id         INTEGER PRIMARY KEY,
    machine_id INTEGER NOT NULL REFERENCES machines(id),
    drink_type TEXT NOT NULL REFERENCES drink_types(name),
    timestamp  TEXT NOT NULL,
    duration_s REAL,
    temp_c     REAL,
    source     TEXT NOT NULL CHECK (source IN ('csv', 'manual'))
);

CREATE TABLE IF NOT EXISTS maintenance_events (
    id         INTEGER PRIMARY KEY,
    machine_id INTEGER NOT NULL REFERENCES machines(id),
    type       TEXT NOT NULL CHECK (type IN ('descale', 'refill', 'repair', 'error')),
    timestamp  TEXT NOT NULL,
    note       TEXT,
    error_code TEXT
);

CREATE INDEX IF NOT EXISTS idx_brew_events_machine ON brew_events(machine_id);
CREATE INDEX IF NOT EXISTS idx_brew_events_timestamp ON brew_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_maintenance_events_machine ON maintenance_events(machine_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_events_machine_type_ts ON maintenance_events(machine_id, type, timestamp);
"""

# The fleet. Old Faithful predates telemetry; its brews are logged by hand in the UI.
MACHINES = [
    (1, "Bertha (3rd floor)", 3, True),
    (2, "The Intern (kitchen)", 1, True),
    (3, "Old Faithful (2nd floor)", 2, False),
    (4, "Rocket (4th floor)", 4, True),
]

# Supported drinks. name is the machine-readable key used in events and the API.
DRINK_TYPES = [
    ("espresso", "Espresso"),
    ("lungo", "Lungo"),
    ("cappuccino", "Cappuccino"),
    ("latte", "Latte"),
    ("americano", "Americano"),
    ("hot_water", "Hot water"),
]


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and insert reference data. Safe to call repeatedly."""
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT OR IGNORE INTO machines (id, name, floor, has_telemetry) VALUES (?, ?, ?, ?)",
        MACHINES,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO drink_types (name, label) VALUES (?, ?)",
        DRINK_TYPES,
    )
    conn.commit()


def reset_db(conn: sqlite3.Connection) -> None:
    """Drop all data and recreate the schema (used by `uv run seed`)."""
    conn.executescript(
        """
        DROP TABLE IF EXISTS brew_events;
        DROP TABLE IF EXISTS maintenance_events;
        DROP TABLE IF EXISTS drink_types;
        DROP TABLE IF EXISTS machines;
        """
    )
    init_db(conn)
