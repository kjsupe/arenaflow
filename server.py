#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import html
import hmac
import json
import os
import secrets
import socket
import struct
import sqlite3
import subprocess
import textwrap
import traceback
import zlib
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DB_PATH = Path(os.environ.get("LASERTAG_DB", APP_DIR / "data" / "scheduler.sqlite3"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_BACKEND = "postgres" if DATABASE_URL.startswith(("postgres://", "postgresql://")) else "sqlite"
COOKIE_NAME = "lt_session"
SESSION_TTL = timedelta(hours=10)
APP_SECRET = os.environ.get("LASERTAG_SECRET", "laser-tag-scheduler-dev-secret")
TICKET_BOTTOM_FEED_LINES = 4
QR_CODE_MARKER = "[[QR_CODE]]"
FRIENDLY_QR_LABEL = "Need to change your game time? Scan this code to choose another available time."
DEFAULT_TIMEZONE = os.environ.get("LASERTAG_TIMEZONE", "America/New_York")

sessions: dict[str, dict[str, object]] = {}

WEEKDAY_KEYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

DEFAULT_SETTINGS = {
    "venue_name": "ArenaFlow",
    "venue_timezone": DEFAULT_TIMEZONE,
    "app_logo_image": "",
    "open_time": "12:00",
    "first_game_time": "12:00",
    "close_time": "22:00",
    "game_interval_minutes": "15",
    "weekly_schedule_json": "{}",
    "schedule_overrides_json": "[]",
    "max_players_per_game": "24",
    "default_blaster_count": "24",
    "public_base_url": "",
    "ticket_heading": "GAME TICKET",
    "ticket_logo_text": "Laser Tag",
    "ticket_logo_enabled": "yes",
    "ticket_logo_raster": "",
    "ticket_logo_preview": "",
    "ticket_logo_width": "0",
    "ticket_logo_height": "0",
    "ticket_width_chars": "42",
    "ticket_show_qr": "yes",
    "ticket_qr_label": FRIENDLY_QR_LABEL,
    "customer_reschedule_last_game": "no",
    "ticket_footer": "Please be at the arena entrance 5 minutes before your game.",
    "printer_mode": "dry_run",
    "printer_host": "",
    "printer_port": "9100",
    "cups_queue": "",
    "theme": "laser",
}

ATTRACTION_SETTING_KEYS = {
    "open_time",
    "first_game_time",
    "close_time",
    "game_interval_minutes",
    "weekly_schedule_json",
    "schedule_overrides_json",
    "max_players_per_game",
    "default_blaster_count",
    "ticket_heading",
    "ticket_logo_text",
    "ticket_footer",
    "customer_reschedule_enabled",
    "customer_reschedule_last_game",
}

DEFAULT_ATTRACTION_SETTINGS = {
    "open_time": DEFAULT_SETTINGS["open_time"],
    "first_game_time": DEFAULT_SETTINGS["first_game_time"],
    "close_time": DEFAULT_SETTINGS["close_time"],
    "game_interval_minutes": DEFAULT_SETTINGS["game_interval_minutes"],
    "weekly_schedule_json": DEFAULT_SETTINGS["weekly_schedule_json"],
    "schedule_overrides_json": DEFAULT_SETTINGS["schedule_overrides_json"],
    "max_players_per_game": DEFAULT_SETTINGS["max_players_per_game"],
    "default_blaster_count": DEFAULT_SETTINGS["default_blaster_count"],
    "ticket_heading": DEFAULT_SETTINGS["ticket_heading"],
    "ticket_logo_text": "Laser Tag",
    "ticket_footer": DEFAULT_SETTINGS["ticket_footer"],
    "customer_reschedule_enabled": "yes",
    "customer_reschedule_last_game": DEFAULT_SETTINGS["customer_reschedule_last_game"],
}

PUBLIC_SETTING_KEYS = {
    "open_time",
    "first_game_time",
    "close_time",
    "game_interval_minutes",
    "schedule_closed",
    "schedule_label",
    "max_players_per_game",
    "default_blaster_count",
    "ticket_footer",
    "theme",
    "customer_reschedule_enabled",
    "customer_reschedule_last_game",
}

PUBLIC_BRANDING_KEYS = {
    "venue_name",
    "app_logo_image",
    "theme",
}

ADMIN_SETTING_KEYS = set(DEFAULT_SETTINGS)


class AppError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def app_zone() -> ZoneInfo:
    try:
        return ZoneInfo(DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def settings_zone(settings: dict[str, str]) -> ZoneInfo:
    timezone_name = settings.get("venue_timezone", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise AppError(400, "Venue timezone is not valid.")


def venue_now(settings: dict[str, str]) -> datetime:
    return datetime.now(settings_zone(settings)).replace(tzinfo=None, second=0, microsecond=0)


def today_iso() -> str:
    return datetime.now(app_zone()).date().isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 140_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_raw)
        expected = base64.b64decode(digest_raw)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'marshal')),
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    settings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blaster_counts (
    service_date TEXT PRIMARY KEY,
    active_blasters INTEGER NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (updated_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS blaster_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    effective_at TEXT NOT NULL UNIQUE,
    active_blasters INTEGER NOT NULL,
    updated_by INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (updated_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_blaster_events_effective_at ON blaster_events(effective_at);

CREATE TABLE IF NOT EXISTS capacity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attraction_id INTEGER NOT NULL,
    effective_at TEXT NOT NULL,
    active_blasters INTEGER NOT NULL,
    updated_by INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (attraction_id, effective_at),
    FOREIGN KEY (attraction_id) REFERENCES attractions(id),
    FOREIGN KEY (updated_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_capacity_events_attraction_effective_at ON capacity_events(attraction_id, effective_at);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attraction_id INTEGER,
    ticket_code TEXT UNIQUE,
    ticket_pin TEXT,
    service_date TEXT NOT NULL,
    game_time TEXT NOT NULL,
    group_name TEXT NOT NULL,
    players INTEGER NOT NULL,
    admitted INTEGER NOT NULL,
    booking_type TEXT NOT NULL CHECK (booking_type IN ('walkup', 'party')),
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('booked', 'cancelled')) DEFAULT 'booked',
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (attraction_id) REFERENCES attractions(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS print_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    ticket_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (actor_id) REFERENCES users(id)
);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'marshal')),
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attractions (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    settings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blaster_counts (
    service_date TEXT PRIMARY KEY,
    active_blasters INTEGER NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (updated_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS blaster_events (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    effective_at TEXT NOT NULL UNIQUE,
    active_blasters INTEGER NOT NULL,
    updated_by INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (updated_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_blaster_events_effective_at ON blaster_events(effective_at);

CREATE TABLE IF NOT EXISTS capacity_events (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    attraction_id INTEGER NOT NULL,
    effective_at TEXT NOT NULL,
    active_blasters INTEGER NOT NULL,
    updated_by INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (attraction_id, effective_at),
    FOREIGN KEY (attraction_id) REFERENCES attractions(id),
    FOREIGN KEY (updated_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_capacity_events_attraction_effective_at ON capacity_events(attraction_id, effective_at);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    attraction_id INTEGER,
    ticket_code TEXT UNIQUE,
    ticket_pin TEXT,
    service_date TEXT NOT NULL,
    game_time TEXT NOT NULL,
    group_name TEXT NOT NULL,
    players INTEGER NOT NULL,
    admitted INTEGER NOT NULL,
    booking_type TEXT NOT NULL CHECK (booking_type IN ('walkup', 'party')),
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('booked', 'cancelled')) DEFAULT 'booked',
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (attraction_id) REFERENCES attractions(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS print_logs (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    booking_id INTEGER,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    ticket_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    actor_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (actor_id) REFERENCES users(id)
);
"""


def connect_db() -> Any:
    if DB_BACKEND == "postgres":
        if psycopg is None or dict_row is None:
            raise RuntimeError("PostgreSQL requires the psycopg package. Install requirements.txt or use Docker.")
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def execute(db: Any, sql: str, params: tuple[object, ...] = ()) -> Any:
    if DB_BACKEND == "postgres":
        sql = sql.replace("?", "%s")
    return db.execute(sql, params)


def execute_script(db: Any, sql: str) -> None:
    if DB_BACKEND == "sqlite":
        db.executescript(sql)
        return

    for statement in sql.split(";"):
        statement = statement.strip()
        if statement:
            execute(db, statement)


def initialize_db() -> None:
    with connect_db() as db:
        execute_script(db, POSTGRES_SCHEMA if DB_BACKEND == "postgres" else SQLITE_SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            execute(
                db,
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
                (key, value),
            )
        migrate_default_qr_label(db)
        migrate_attractions(db)
        migrate_booking_attractions(db)
        migrate_blaster_counts(db)
        migrate_capacity_events(db)
        migrate_ticket_codes(db)
        user_count = execute(db, "SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        if user_count == 0:
            now = utc_now()
            execute(
                db,
                """
                INSERT INTO users (username, display_name, role, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("admin", "Admin", "admin", hash_password("admin123"), now),
            )
            execute(
                db,
                """
                INSERT INTO users (username, display_name, role, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("marshal", "Marshal", "marshal", hash_password("marshal"), now),
            )


def generate_ticket_code(db: Any) -> str:
    for _ in range(50):
        code = str(secrets.randbelow(9_000_000_000) + 1_000_000_000)
        existing = execute(db, "SELECT id FROM bookings WHERE ticket_code = ?", (code,)).fetchone()
        if not existing:
            return code
    raise RuntimeError("Unable to generate a unique ticket code.")


def generate_ticket_pin() -> str:
    return f"{secrets.randbelow(900_000) + 100_000:06d}"


def migrate_default_qr_label(db: Any) -> None:
    execute(
        db,
        "UPDATE settings SET value = ? WHERE key = 'ticket_qr_label' AND value = ?",
        (FRIENDLY_QR_LABEL, "Scan to change game time"),
    )


def attraction_settings_from_global(settings: dict[str, str]) -> dict[str, str]:
    merged = dict(DEFAULT_ATTRACTION_SETTINGS)
    for key in ATTRACTION_SETTING_KEYS:
        if key in settings:
            merged[key] = settings[key]
    merged.setdefault("customer_reschedule_enabled", "yes")
    return normalize_attraction_settings(merged)


def default_attraction_id(db: Any) -> int:
    row = execute(db, "SELECT id FROM attractions ORDER BY sort_order ASC, id ASC LIMIT 1").fetchone()
    if not row:
        migrate_attractions(db)
        row = execute(db, "SELECT id FROM attractions ORDER BY sort_order ASC, id ASC LIMIT 1").fetchone()
    if not row:
        raise AppError(500, "No attractions are configured.")
    return int(row["id"])


def migrate_attractions(db: Any) -> None:
    count = execute(db, "SELECT COUNT(*) AS count FROM attractions").fetchone()["count"]
    if int(count) > 0:
        return
    settings = get_settings(db)
    attraction_name = settings.get("ticket_logo_text", "").strip() or "Laser Tag"
    if attraction_name.lower() in {"arenaflow", "arenaflow scheduler"}:
        attraction_name = "Laser Tag"
    now = utc_now()
    execute(
        db,
        """
        INSERT INTO attractions (name, active, sort_order, settings_json, created_at, updated_at)
        VALUES (?, 1, 1, ?, ?, ?)
        """,
        (attraction_name[:80], json.dumps(attraction_settings_from_global(settings), sort_keys=True), now, now),
    )


def migrate_booking_attractions(db: Any) -> None:
    if DB_BACKEND == "postgres":
        execute(db, "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS attraction_id INTEGER")
    else:
        columns = execute(db, "PRAGMA table_info(bookings)").fetchall()
        if not any(row["name"] == "attraction_id" for row in columns):
            execute(db, "ALTER TABLE bookings ADD COLUMN attraction_id INTEGER")
    attraction_id = default_attraction_id(db)
    execute(db, "UPDATE bookings SET attraction_id = ? WHERE attraction_id IS NULL", (attraction_id,))
    execute(db, "CREATE INDEX IF NOT EXISTS idx_bookings_attraction_date_time ON bookings(attraction_id, service_date, game_time)")


def migrate_capacity_events(db: Any) -> None:
    count = execute(db, "SELECT COUNT(*) AS count FROM capacity_events").fetchone()["count"]
    if int(count) > 0:
        return
    attraction_id = default_attraction_id(db)
    if DB_BACKEND == "postgres":
        execute(
            db,
            """
            INSERT INTO capacity_events (attraction_id, effective_at, active_blasters, updated_by, created_at)
            SELECT ?, effective_at, active_blasters, updated_by, created_at
            FROM blaster_events
            ON CONFLICT (attraction_id, effective_at) DO NOTHING
            """,
            (attraction_id,),
        )
        return
    execute(
        db,
        """
        INSERT OR IGNORE INTO capacity_events (attraction_id, effective_at, active_blasters, updated_by, created_at)
        SELECT ?, effective_at, active_blasters, updated_by, created_at
        FROM blaster_events
        """,
        (attraction_id,),
    )


def normalize_ticket_code(value: str) -> str:
    code = value.replace(" ", "").replace("-", "").strip()
    if not code.isdigit() or len(code) < 6 or len(code) > 20:
        raise AppError(404, "Ticket code was not found.")
    return code


def normalize_ticket_pin(value: str) -> str:
    pin = value.replace(" ", "").replace("-", "").strip()
    if not pin.isdigit() or len(pin) < 4 or len(pin) > 6:
        raise AppError(404, "Ticket code or PIN was not found.")
    return pin


def migrate_ticket_codes(db: Any) -> None:
    if DB_BACKEND == "postgres":
        execute(db, "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS ticket_code TEXT")
        execute(db, "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS ticket_pin TEXT")
        execute(
            db,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_ticket_code ON bookings(ticket_code) WHERE ticket_code IS NOT NULL",
        )
    else:
        columns = execute(db, "PRAGMA table_info(bookings)").fetchall()
        has_ticket_code = any(row["name"] == "ticket_code" for row in columns)
        has_ticket_pin = any(row["name"] == "ticket_pin" for row in columns)
        if not has_ticket_code:
            execute(db, "ALTER TABLE bookings ADD COLUMN ticket_code TEXT")
        if not has_ticket_pin:
            execute(db, "ALTER TABLE bookings ADD COLUMN ticket_pin TEXT")
        execute(
            db,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_ticket_code ON bookings(ticket_code) WHERE ticket_code IS NOT NULL",
        )

    rows = execute(db, "SELECT id FROM bookings WHERE ticket_code IS NULL OR ticket_code = ''").fetchall()
    for row in rows:
        execute(db, "UPDATE bookings SET ticket_code = ? WHERE id = ?", (generate_ticket_code(db), int(row["id"])))

    rows = execute(db, "SELECT id FROM bookings WHERE ticket_pin IS NULL OR ticket_pin = ''").fetchall()
    for row in rows:
        execute(db, "UPDATE bookings SET ticket_pin = ? WHERE id = ?", (generate_ticket_pin(), int(row["id"])))


def migrate_blaster_counts(db: Any) -> None:
    existing_events = execute(db, "SELECT COUNT(*) AS count FROM blaster_events").fetchone()["count"]
    if int(existing_events) > 0:
        return

    if DB_BACKEND == "postgres":
        execute(
            db,
            """
            INSERT INTO blaster_events (effective_at, active_blasters, updated_by, created_at)
            SELECT service_date || 'T00:00', active_blasters, updated_by, updated_at
            FROM blaster_counts
            ON CONFLICT (effective_at) DO NOTHING
            """,
        )
        return

    execute(
        db,
        """
        INSERT OR IGNORE INTO blaster_events (effective_at, active_blasters, updated_by, created_at)
        SELECT service_date || 'T00:00', active_blasters, updated_by, updated_at
        FROM blaster_counts
        """,
    )


def get_settings(db: Any) -> dict[str, str]:
    settings = dict(DEFAULT_SETTINGS)
    rows = execute(db, "SELECT key, value FROM settings").fetchall()
    for row in rows:
        if row["key"] in DEFAULT_SETTINGS:
            settings[row["key"]] = row["value"]
    return settings


def update_settings(db: Any, updates: dict[str, object], actor_id: int) -> None:
    clean_updates: dict[str, str] = {}
    for key, value in updates.items():
        if key not in ADMIN_SETTING_KEYS:
            continue
        clean_updates[key] = str(value).strip()

    validate_settings({**get_settings(db), **clean_updates})

    for key, value in clean_updates.items():
        execute(
            db,
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
    write_audit(db, actor_id, "settings_updated", json.dumps(clean_updates, sort_keys=True))


def row_value(row: Any, key: str, default: object = "") -> object:
    try:
        return row[key]
    except Exception:
        return default


def row_to_attraction(row: Any) -> dict[str, object]:
    raw_settings = parse_json_setting(str(row["settings_json"] or "{}"), {}, f"Attraction {row['id']} settings")
    if not isinstance(raw_settings, dict):
        raw_settings = {}
    settings = normalize_attraction_settings(raw_settings)
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "active": str(row["active"]) not in {"0", "false", "False", "no"},
        "sort_order": int(row["sort_order"] or 0),
        "settings": settings,
    }


def public_attraction(attraction: dict[str, object]) -> dict[str, object]:
    return {
        "id": attraction["id"],
        "name": attraction["name"],
        "active": attraction["active"],
    }


def get_attractions(db: Any, include_inactive: bool = False) -> list[dict[str, object]]:
    if include_inactive:
        rows = execute(db, "SELECT * FROM attractions ORDER BY sort_order ASC, id ASC").fetchall()
    else:
        rows = execute(db, "SELECT * FROM attractions WHERE active != 0 ORDER BY sort_order ASC, id ASC").fetchall()
    return [row_to_attraction(row) for row in rows]


def get_attraction(db: Any, attraction_id: int | str | None = None, include_inactive: bool = True) -> dict[str, object]:
    if attraction_id is None or str(attraction_id).strip() == "":
        attractions = get_attractions(db, include_inactive=False)
        if attractions:
            return attractions[0]
        attractions = get_attractions(db, include_inactive=True)
        if attractions:
            return attractions[0]
        raise AppError(404, "No attractions are configured.")

    try:
        parsed_id = int(str(attraction_id))
    except ValueError:
        raise AppError(404, "Attraction not found.")

    row = execute(db, "SELECT * FROM attractions WHERE id = ?", (parsed_id,)).fetchone()
    if not row:
        raise AppError(404, "Attraction not found.")
    attraction = row_to_attraction(row)
    if not include_inactive and not attraction["active"]:
        raise AppError(404, "Attraction not found.")
    return attraction


def create_attraction(db: Any, payload: dict[str, object], actor_id: int) -> dict[str, object]:
    name = str(payload.get("name") or "New Attraction").strip()
    if not name:
        raise AppError(400, "Attraction name is required.")
    if len(name) > 80:
        raise AppError(400, "Attraction name is too long.")
    sort_row = execute(db, "SELECT COALESCE(MAX(sort_order), 0) AS sort_order FROM attractions").fetchone()
    sort_order = int(sort_row["sort_order"] or 0) + 1
    settings = dict(DEFAULT_ATTRACTION_SETTINGS)
    settings["ticket_logo_text"] = name
    now = utc_now()
    if DB_BACKEND == "postgres":
        cursor = execute(
            db,
            """
            INSERT INTO attractions (name, active, sort_order, settings_json, created_at, updated_at)
            VALUES (?, 1, ?, ?, ?, ?)
            RETURNING id
            """,
            (name, sort_order, json.dumps(normalize_attraction_settings(settings), sort_keys=True), now, now),
        )
        attraction_id = int(cursor.fetchone()["id"])
    else:
        cursor = execute(
            db,
            """
            INSERT INTO attractions (name, active, sort_order, settings_json, created_at, updated_at)
            VALUES (?, 1, ?, ?, ?, ?)
            """,
            (name, sort_order, json.dumps(normalize_attraction_settings(settings), sort_keys=True), now, now),
        )
        attraction_id = int(cursor.lastrowid)
    write_audit(db, actor_id, "attraction_created", f"attraction_id={attraction_id} name={name}")
    return get_attraction(db, attraction_id)


def update_attraction(db: Any, payload: dict[str, object], actor_id: int) -> dict[str, object]:
    attraction = get_attraction(db, payload.get("id"), include_inactive=True)
    name = str(payload.get("name") or attraction["name"]).strip()
    if not name:
        raise AppError(400, "Attraction name is required.")
    if len(name) > 80:
        raise AppError(400, "Attraction name is too long.")
    active = 1 if truthy_setting(payload.get("active", attraction["active"])) else 0
    raw_settings = payload.get("settings", {})
    if not isinstance(raw_settings, dict):
        raise AppError(400, "Attraction settings must be an object.")
    settings = normalize_attraction_settings({**attraction["settings"], **raw_settings})
    execute(
        db,
        """
        UPDATE attractions
        SET name = ?, active = ?, settings_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (name, active, json.dumps(settings, sort_keys=True), utc_now(), int(attraction["id"])),
    )
    write_audit(db, actor_id, "attraction_updated", f"attraction_id={attraction['id']} name={name}")
    return get_attraction(db, int(attraction["id"]), include_inactive=True)


def default_day_schedule(settings: dict[str, str]) -> dict[str, str]:
    return {
        "open_time": settings["open_time"],
        "first_game_time": settings["first_game_time"],
        "close_time": settings["close_time"],
        "game_interval_minutes": settings["game_interval_minutes"],
    }


def parse_json_setting(value: str, fallback: object, label: str) -> object:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise AppError(400, f"{label} must be valid JSON.")


def truthy_setting(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "closed"}


def normalize_clock_setting(value: object, fallback: str) -> str:
    raw = str(value or "").strip() or fallback
    return parse_clock(raw).strftime("%H:%M")


def validate_time_window(
    open_time: str,
    first_game_time: str,
    close_time: str,
    label: str = "Schedule",
) -> None:
    base = date.today()
    open_dt = datetime.combine(base, parse_clock(open_time))
    first_game_dt = datetime.combine(base, parse_clock(first_game_time))
    close_dt = datetime.combine(base, parse_clock(close_time))
    if close_dt <= open_dt:
        close_dt += timedelta(days=1)
    if first_game_dt < open_dt:
        first_game_dt += timedelta(days=1)
    if first_game_dt < open_dt or first_game_dt >= close_dt:
        raise AppError(400, f"{label}: first game time must be between open time and close time.")


def normalize_day_schedule(
    raw: object,
    defaults: dict[str, str],
    label: str,
) -> dict[str, object]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise AppError(400, f"{label} must be a schedule object.")

    closed = truthy_setting(raw.get("closed", False))
    open_time = normalize_clock_setting(raw.get("open_time"), defaults["open_time"])
    first_game_time = normalize_clock_setting(raw.get("first_game_time"), defaults["first_game_time"])
    close_time = normalize_clock_setting(raw.get("close_time"), defaults["close_time"])
    interval = as_int(raw.get("game_interval_minutes") or defaults["game_interval_minutes"], f"{label} interval")
    if interval < 5 or interval > 120:
        raise AppError(400, f"{label}: game interval must be between 5 and 120 minutes.")
    if not closed:
        validate_time_window(open_time, first_game_time, close_time, label)

    return {
        "closed": closed,
        "open_time": open_time,
        "first_game_time": first_game_time,
        "close_time": close_time,
        "game_interval_minutes": str(interval),
    }


def weekly_schedule(settings: dict[str, str]) -> dict[str, dict[str, object]]:
    raw = parse_json_setting(settings.get("weekly_schedule_json", "{}"), {}, "Weekly schedule")
    if not isinstance(raw, dict):
        raise AppError(400, "Weekly schedule must be a JSON object.")

    defaults = default_day_schedule(settings)
    normalized: dict[str, dict[str, object]] = {}
    for day_key in WEEKDAY_KEYS:
        day_label = day_key.replace("_", " ").title()
        normalized[day_key] = normalize_day_schedule(raw.get(day_key, {}), defaults, day_label)
    return normalized


def schedule_overrides(settings: dict[str, str]) -> list[dict[str, object]]:
    raw = parse_json_setting(settings.get("schedule_overrides_json", "[]"), [], "Holiday overrides")
    if not isinstance(raw, list):
        raise AppError(400, "Holiday overrides must be a JSON array.")
    if len(raw) > 120:
        raise AppError(400, "Holiday overrides are limited to 120 dates.")

    defaults = default_day_schedule(settings)
    seen_dates: set[str] = set()
    normalized: list[dict[str, object]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise AppError(400, f"Holiday override {index} must be an object.")
        date_value = str(item.get("date") or "").strip()
        parse_service_date(date_value)
        if date_value in seen_dates:
            raise AppError(400, f"Holiday override {date_value} is duplicated.")
        seen_dates.add(date_value)

        label = str(item.get("label") or "").strip()
        if len(label) > 80:
            raise AppError(400, f"Holiday override {date_value} label is too long.")
        override = normalize_day_schedule(item, defaults, f"Holiday override {date_value}")
        override["date"] = date_value
        override["label"] = label or "Holiday override"
        normalized.append(override)

    return sorted(normalized, key=lambda item: str(item["date"]))


def effective_schedule_settings(settings: dict[str, str], service_date: str) -> dict[str, str]:
    service_day = parse_service_date(service_date)
    day_key = WEEKDAY_KEYS[service_day.weekday()]
    effective = dict(settings)
    day_schedule = weekly_schedule(settings)[day_key]
    label = day_key.title()

    for override in schedule_overrides(settings):
        if override["date"] == service_date:
            day_schedule = override
            label = str(override.get("label") or "Holiday override")
            break

    effective["open_time"] = str(day_schedule["open_time"])
    effective["first_game_time"] = str(day_schedule["first_game_time"])
    effective["close_time"] = str(day_schedule["close_time"])
    effective["game_interval_minutes"] = str(day_schedule["game_interval_minutes"])
    effective["schedule_closed"] = "yes" if day_schedule["closed"] else "no"
    effective["schedule_label"] = label
    return effective


def validate_settings(settings: dict[str, str]) -> None:
    open_clock = parse_clock(settings["open_time"])
    first_game_clock = parse_clock(settings["first_game_time"])
    close_clock = parse_clock(settings["close_time"])
    interval = as_int(settings["game_interval_minutes"], "Game interval")
    max_players = as_int(settings["max_players_per_game"], "Max players")
    default_blasters = as_int(settings["default_blaster_count"], "Default blasters")
    printer_port = as_int(settings["printer_port"], "Printer port")
    ticket_width = as_int(settings["ticket_width_chars"], "Ticket width")
    logo_width = as_int(settings["ticket_logo_width"], "Logo width")
    logo_height = as_int(settings["ticket_logo_height"], "Logo height")

    if interval < 5 or interval > 120:
        raise AppError(400, "Game interval must be between 5 and 120 minutes.")
    if max_players < 1 or max_players > 200:
        raise AppError(400, "Max players must be between 1 and 200.")
    if default_blasters < 1 or default_blasters > 200:
        raise AppError(400, "Default blasters must be between 1 and 200.")
    if len(settings["venue_timezone"]) > 80:
        raise AppError(400, "Venue timezone is too long.")
    settings_zone(settings)
    if printer_port < 1 or printer_port > 65535:
        raise AppError(400, "Printer port must be between 1 and 65535.")
    if settings["printer_mode"] not in {"dry_run", "tcp", "cups"}:
        raise AppError(400, "Printer mode must be dry_run, tcp, or cups.")
    if settings["theme"] not in {"laser", "daylight", "arcade", "coastal"}:
        raise AppError(400, "Theme must be laser, daylight, arcade, or coastal.")
    if settings["ticket_logo_enabled"] not in {"yes", "no"}:
        raise AppError(400, "Logo setting must be yes or no.")
    if settings["ticket_show_qr"] not in {"yes", "no"}:
        raise AppError(400, "QR code setting must be yes or no.")
    if settings["customer_reschedule_last_game"] not in {"yes", "no"}:
        raise AppError(400, "Customer last-game reschedule setting must be yes or no.")
    if ticket_width < 32 or ticket_width > 48:
        raise AppError(400, "Ticket width must be between 32 and 48 characters.")
    if len(settings["public_base_url"]) > 180:
        raise AppError(400, "Public booking URL is too long.")
    if settings["public_base_url"]:
        parsed_url = urlparse(settings["public_base_url"])
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise AppError(400, "Public booking URL must start with http:// or https://.")
    if len(settings["ticket_heading"]) > 60:
        raise AppError(400, "Ticket heading is too long.")
    if len(settings["ticket_logo_text"]) > 80:
        raise AppError(400, "Logo text is too long.")
    if len(settings["ticket_qr_label"]) > 80:
        raise AppError(400, "QR label is too long.")
    if len(settings["ticket_footer"]) > 240:
        raise AppError(400, "Ticket footer is too long.")

    validate_image_data_url(settings["app_logo_image"].strip(), "App logo", 600_000)
    validate_image_data_url(settings["ticket_logo_preview"].strip(), "Logo preview", 300_000)

    logo_raster = settings["ticket_logo_raster"].strip()
    if logo_raster:
        if logo_width < 8 or logo_width > 576 or logo_width % 8 != 0:
            raise AppError(400, "Logo width must be an 8-pixel multiple up to 576.")
        if logo_height < 1 or logo_height > 240:
            raise AppError(400, "Logo height must be between 1 and 240 pixels.")
        try:
            logo_bytes = base64.b64decode(logo_raster, validate=True)
        except Exception:
            raise AppError(400, "Logo data is not valid.")
        expected_bytes = (logo_width // 8) * logo_height
        if len(logo_bytes) != expected_bytes:
            raise AppError(400, "Logo data does not match its dimensions.")
    elif logo_width != 0 or logo_height != 0:
        raise AppError(400, "Logo dimensions must be 0 when no logo is uploaded.")

    validate_time_window(open_clock.strftime("%H:%M"), first_game_clock.strftime("%H:%M"), close_clock.strftime("%H:%M"))
    weekly_schedule(settings)
    schedule_overrides(settings)


def normalize_attraction_settings(raw_settings: dict[str, object]) -> dict[str, str]:
    settings = dict(DEFAULT_ATTRACTION_SETTINGS)
    for key in ATTRACTION_SETTING_KEYS:
        if key in raw_settings:
            settings[key] = str(raw_settings[key]).strip()

    open_clock = parse_clock(settings["open_time"])
    first_game_clock = parse_clock(settings["first_game_time"])
    close_clock = parse_clock(settings["close_time"])
    interval = as_int(settings["game_interval_minutes"], "Game interval")
    max_players = as_int(settings["max_players_per_game"], "Max players")
    default_blasters = as_int(settings["default_blaster_count"], "Default capacity")

    if interval < 5 or interval > 120:
        raise AppError(400, "Game interval must be between 5 and 120 minutes.")
    if max_players < 1 or max_players > 200:
        raise AppError(400, "Max players must be between 1 and 200.")
    if default_blasters < 1 or default_blasters > 200:
        raise AppError(400, "Default capacity must be between 1 and 200.")
    if len(settings["ticket_heading"]) > 60:
        raise AppError(400, "Ticket heading is too long.")
    if len(settings["ticket_logo_text"]) > 80:
        raise AppError(400, "Logo text is too long.")
    if len(settings["ticket_footer"]) > 240:
        raise AppError(400, "Ticket footer is too long.")
    if settings["customer_reschedule_enabled"] not in {"yes", "no"}:
        raise AppError(400, "Customer reschedule setting must be yes or no.")
    if settings["customer_reschedule_last_game"] not in {"yes", "no"}:
        raise AppError(400, "Customer last-game reschedule setting must be yes or no.")

    settings["open_time"] = open_clock.strftime("%H:%M")
    settings["first_game_time"] = first_game_clock.strftime("%H:%M")
    settings["close_time"] = close_clock.strftime("%H:%M")
    settings["game_interval_minutes"] = str(interval)
    settings["max_players_per_game"] = str(max_players)
    settings["default_blaster_count"] = str(default_blasters)
    validate_time_window(settings["open_time"], settings["first_game_time"], settings["close_time"])
    weekly_schedule(settings)
    schedule_overrides(settings)
    return settings


def validate_image_data_url(value: str, label: str, max_length: int) -> None:
    if not value:
        return
    if len(value) > max_length:
        raise AppError(400, f"{label} image is too large.")
    if not value.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")):
        raise AppError(400, f"{label} must be a PNG, JPEG, or WebP data URL.")
    try:
        base64.b64decode(value.split(",", 1)[1], validate=True)
    except Exception:
        raise AppError(400, f"{label} data is not valid.")


def as_int(value: object, label: str) -> int:
    try:
        return int(str(value))
    except ValueError:
        raise AppError(400, f"{label} must be a number.")


def parse_clock(value: str) -> time:
    try:
        hour_raw, minute_raw = value.split(":", 1)
        hour = int(hour_raw)
        minute = int(minute_raw)
        return time(hour=hour, minute=minute)
    except Exception:
        raise AppError(400, "Times must use HH:MM format.")


def parse_service_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise AppError(400, "Date must use YYYY-MM-DD format.")


def normalize_game_time(value: str) -> str:
    parsed = parse_clock(value)
    return parsed.strftime("%H:%M")


def format_display_time(value: str) -> str:
    parsed = parse_clock(value)
    return datetime.combine(date.today(), parsed).strftime("%I:%M %p").lstrip("0")


def current_effective_at() -> str:
    return datetime.now(app_zone()).replace(tzinfo=None, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def normalize_effective_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        raise AppError(400, "Effective time must use YYYY-MM-DDTHH:MM format.")


def slot_datetime(service_day: date, game_time: str, settings: dict[str, str]) -> datetime:
    first_game_clock = parse_clock(settings["first_game_time"])
    close_clock = parse_clock(settings["close_time"])
    slot_dt = datetime.combine(service_day, parse_clock(game_time))
    first_game_dt = datetime.combine(service_day, first_game_clock)
    close_dt = datetime.combine(service_day, close_clock)
    if close_dt <= first_game_dt and slot_dt < first_game_dt:
        slot_dt += timedelta(days=1)
    return slot_dt


def schedule_close_datetime(service_day: date, settings: dict[str, str]) -> datetime:
    open_dt = datetime.combine(service_day, parse_clock(settings["open_time"]))
    close_dt = datetime.combine(service_day, parse_clock(settings["close_time"]))
    if close_dt <= open_dt:
        close_dt += timedelta(days=1)
    return close_dt


def current_service_date_for_attraction(
    attraction_settings: dict[str, str],
    global_settings: dict[str, str],
    now: datetime | None = None,
) -> str:
    now = now or venue_now(global_settings)
    today = now.date()
    yesterday = today - timedelta(days=1)

    yesterday_settings = effective_schedule_settings(attraction_settings, yesterday.isoformat())
    if yesterday_settings.get("schedule_closed") != "yes":
        yesterday_open = datetime.combine(yesterday, parse_clock(yesterday_settings["open_time"]))
        yesterday_close = schedule_close_datetime(yesterday, yesterday_settings)
        if yesterday_close.date() > yesterday_open.date() and now < yesterday_close:
            return yesterday.isoformat()

    today_settings = effective_schedule_settings(attraction_settings, today.isoformat())
    if today_settings.get("schedule_closed") != "yes" and now >= schedule_close_datetime(today, today_settings):
        return (today + timedelta(days=1)).isoformat()

    return today.isoformat()


def slot_times(settings: dict[str, str]) -> list[str]:
    if settings.get("schedule_closed") == "yes":
        return []

    first_game_clock = parse_clock(settings["first_game_time"])
    close_clock = parse_clock(settings["close_time"])
    interval = as_int(settings["game_interval_minutes"], "Game interval")

    base = date.today()
    current = datetime.combine(base, first_game_clock)
    end = datetime.combine(base, close_clock)
    if end <= current:
        end += timedelta(days=1)

    slots: list[str] = []
    while current < end:
        slots.append(current.time().strftime("%H:%M"))
        current += timedelta(minutes=interval)
    return slots


def get_active_blasters_at(db: Any, attraction_id: int, effective_at: str, settings: dict[str, str]) -> int:
    row = execute(
        db,
        """
        SELECT active_blasters
        FROM capacity_events
        WHERE attraction_id = ? AND effective_at <= ?
        ORDER BY effective_at DESC, id DESC
        LIMIT 1
        """,
        (attraction_id, effective_at),
    ).fetchone()
    if row:
        return int(row["active_blasters"])
    return as_int(settings["default_blaster_count"], "Default blasters")


def get_latest_active_blasters(db: Any, attraction_id: int, settings: dict[str, str]) -> int:
    row = execute(
        db,
        """
        SELECT active_blasters
        FROM capacity_events
        WHERE attraction_id = ?
        ORDER BY effective_at DESC, id DESC
        LIMIT 1
        """,
        (attraction_id,),
    ).fetchone()
    if row:
        return int(row["active_blasters"])
    return as_int(settings["default_blaster_count"], "Default blasters")


def schedule_state(db: Any, service_date: str, attraction_id: int | str | None = None) -> dict[str, object]:
    service_day = parse_service_date(service_date)
    global_settings = get_settings(db)
    attractions = get_attractions(db, include_inactive=False)
    allow_inactive_selection = False
    if not attractions:
        attractions = get_attractions(db, include_inactive=True)
        allow_inactive_selection = True
    attraction = get_attraction(
        db,
        attraction_id or (attractions[0]["id"] if attractions else None),
        include_inactive=allow_inactive_selection,
    )
    attraction_id_int = int(attraction["id"])
    schedule_settings = effective_schedule_settings(attraction["settings"], service_date)
    schedule_settings["theme"] = global_settings["theme"]
    venue_current_time = venue_now(global_settings)
    current_service_date = current_service_date_for_attraction(
        attraction["settings"],
        global_settings,
        venue_current_time,
    )
    active_blasters = get_latest_active_blasters(db, attraction_id_int, schedule_settings)
    max_players = as_int(schedule_settings["max_players_per_game"], "Max players")

    rows = execute(
        db,
        """
        SELECT b.*, u.display_name AS created_by_name, a.name AS attraction_name
        FROM bookings b
        LEFT JOIN users u ON u.id = b.created_by
        LEFT JOIN attractions a ON a.id = b.attraction_id
        WHERE b.attraction_id = ? AND b.service_date = ? AND b.status != 'cancelled'
        ORDER BY b.game_time ASC, b.id ASC
        """,
        (attraction_id_int, service_date),
    ).fetchall()

    bookings_by_time: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        booking = row_to_booking(row)
        bookings_by_time.setdefault(booking["game_time"], []).append(booking)

    slots = []
    for game_time in slot_times(schedule_settings):
        slot_effective_at = slot_datetime(service_day, game_time, schedule_settings).strftime("%Y-%m-%dT%H:%M")
        slot_blasters = get_active_blasters_at(db, attraction_id_int, slot_effective_at, schedule_settings)
        capacity = min(max_players, slot_blasters)
        bookings = bookings_by_time.get(game_time, [])
        booked = sum(int(item["admitted"]) for item in bookings if item["status"] == "booked")
        open_spots = max(capacity - booked, 0)
        slots.append(
            {
                "game_time": game_time,
                "display_time": format_display_time(game_time),
                "starts_at": slot_effective_at,
                "active_blasters": slot_blasters,
                "capacity": capacity,
                "booked": booked,
                "available": open_spots,
                "status": "full" if open_spots == 0 else "open",
                "bookings": bookings,
            }
        )

    public_settings = {key: schedule_settings[key] for key in PUBLIC_SETTING_KEYS}
    return {
        "date": service_date,
        "current_service_date": current_service_date,
        "venue_now": venue_current_time.strftime("%Y-%m-%dT%H:%M"),
        "attraction": public_attraction(attraction),
        "attractions": [public_attraction(item) for item in attractions],
        "settings": public_settings,
        "active_blasters": active_blasters,
        "slots": slots,
    }


def row_to_booking(row: Any) -> dict[str, object]:
    return {
        "id": row["id"],
        "attraction_id": int(row_value(row, "attraction_id", 0) or 0),
        "attraction_name": str(row_value(row, "attraction_name", "") or ""),
        "ticket_code": row["ticket_code"],
        "ticket_pin": row["ticket_pin"],
        "date": row["service_date"],
        "game_time": row["game_time"],
        "display_time": format_display_time(row["game_time"]),
        "group_name": row["group_name"],
        "players": row["players"],
        "admitted": row["admitted"],
        "booking_type": row["booking_type"],
        "notes": row["notes"],
        "status": row["status"],
        "created_by": row["created_by_name"] or "",
        "created_at": row["created_at"],
    }


def create_booking(db: Any, payload: dict[str, object], actor: dict[str, object]) -> dict[str, object]:
    service_date = str(payload.get("date") or today_iso())
    parse_service_date(service_date)
    attraction = get_attraction(db, payload.get("attraction_id"), include_inactive=False)
    attraction_id = int(attraction["id"])
    game_time = normalize_game_time(str(payload.get("game_time") or ""))
    schedule_settings = effective_schedule_settings(attraction["settings"], service_date)
    if game_time not in slot_times(schedule_settings):
        raise AppError(400, "Choose a valid game time.")

    group_name = str(payload.get("group_name") or "").strip() or "Walk-in"
    if len(group_name) > 80:
        raise AppError(400, "Group name is too long.")

    players = as_int(payload.get("players", 0), "Players")
    admitted = players
    if players < 1 or players > 200:
        raise AppError(400, "Players must be between 1 and 200.")

    booking_type = str(payload.get("booking_type") or "walkup").strip()
    if booking_type not in {"walkup", "party"}:
        raise AppError(400, "Booking type must be walkup or party.")
    notes = str(payload.get("notes") or "").strip()[:400]

    available = slot_availability(db, attraction_id, service_date, game_time)
    if admitted > available:
        raise AppError(409, f"Only {available} spot(s) are available for that game.")

    now = utc_now()
    ticket_code = generate_ticket_code(db)
    ticket_pin = generate_ticket_pin()
    booking_params = (
        attraction_id,
        ticket_code,
        ticket_pin,
        service_date,
        game_time,
        group_name,
        players,
        admitted,
        booking_type,
        notes,
        int(actor["id"]),
        now,
        now,
    )
    if DB_BACKEND == "postgres":
        cursor = execute(
            db,
            """
            INSERT INTO bookings
                (attraction_id, ticket_code, ticket_pin, service_date, game_time, group_name, players, admitted, booking_type, notes, status, created_by, created_at, updated_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'booked', ?, ?, ?)
            RETURNING id
            """,
            booking_params,
        )
        booking_id = int(cursor.fetchone()["id"])
    else:
        cursor = execute(
            db,
            """
            INSERT INTO bookings
                (attraction_id, ticket_code, ticket_pin, service_date, game_time, group_name, players, admitted, booking_type, notes, status, created_by, created_at, updated_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'booked', ?, ?, ?)
            """,
            booking_params,
        )
        booking_id = int(cursor.lastrowid)
    write_audit(db, int(actor["id"]), "booking_created", f"booking_id={booking_id}")
    booking = get_booking(db, booking_id)

    print_result = None
    if payload.get("print_ticket", True):
        print_result = print_ticket(db, booking)

    return {"booking": booking, "print_result": print_result}


def slot_availability(db: Any, attraction_id: int, service_date: str, game_time: str) -> int:
    state = schedule_state(db, service_date, attraction_id)
    for slot in state["slots"]:
        if slot["game_time"] == game_time:
            return int(slot["available"])
    return 0


def slot_availability_excluding(db: Any, service_date: str, game_time: str, booking: dict[str, object]) -> int:
    available = slot_availability(db, int(booking["attraction_id"]), service_date, game_time)
    if (
        booking["status"] == "booked"
        and booking["date"] == service_date
        and booking["game_time"] == game_time
    ):
        available += int(booking["admitted"])
    return available


def is_same_booking_slot(booking: dict[str, object], service_date: str, game_time: str) -> bool:
    return booking["date"] == service_date and booking["game_time"] == game_time


def customer_can_reschedule_to_slot(settings: dict[str, str], booking: dict[str, object], service_date: str, game_time: str) -> bool:
    if settings.get("customer_reschedule_enabled") != "yes":
        return False
    if settings["customer_reschedule_last_game"] == "yes":
        return True
    if is_same_booking_slot(booking, service_date, game_time):
        return True
    slots = slot_times(settings)
    return not slots or game_time != slots[-1]


def get_booking(db: Any, booking_id: int) -> dict[str, object]:
    row = execute(
        db,
        """
        SELECT b.*, u.display_name AS created_by_name, a.name AS attraction_name
        FROM bookings b
        LEFT JOIN users u ON u.id = b.created_by
        LEFT JOIN attractions a ON a.id = b.attraction_id
        WHERE b.id = ?
        """,
        (booking_id,),
    ).fetchone()
    if not row:
        raise AppError(404, "Booking not found.")
    return row_to_booking(row)


def get_booking_by_ticket_code(db: Any, ticket_code: str) -> dict[str, object]:
    row = execute(
        db,
        """
        SELECT b.*, u.display_name AS created_by_name, a.name AS attraction_name
        FROM bookings b
        LEFT JOIN users u ON u.id = b.created_by
        LEFT JOIN attractions a ON a.id = b.attraction_id
        WHERE b.ticket_code = ?
        """,
        (normalize_ticket_code(ticket_code),),
    ).fetchone()
    if not row:
        raise AppError(404, "Ticket code was not found.")
    return row_to_booking(row)


def get_booking_by_ticket_credentials(db: Any, ticket_code: str, ticket_pin: str) -> dict[str, object]:
    booking = get_booking_by_ticket_code(db, ticket_code)
    expected_pin = normalize_ticket_pin(str(booking.get("ticket_pin") or ""))
    provided_pin = normalize_ticket_pin(ticket_pin)
    if not hmac.compare_digest(expected_pin, provided_pin):
        raise AppError(404, "Ticket code or PIN was not found.")
    return booking


def cancel_booking(db: Any, booking_id: int, actor_id: int) -> dict[str, object]:
    booking = get_booking(db, booking_id)
    if booking["status"] == "cancelled":
        return booking
    execute(
        db,
        "UPDATE bookings SET status = 'cancelled', updated_at = ? WHERE id = ?",
        (utc_now(), booking_id),
    )
    write_audit(db, actor_id, "booking_cancelled", f"booking_id={booking_id}")
    return get_booking(db, booking_id)


def available_reschedule_slots(db: Any, booking: dict[str, object], service_date: str) -> list[dict[str, object]]:
    attraction = get_attraction(db, int(booking["attraction_id"]), include_inactive=True)
    settings = effective_schedule_settings(attraction["settings"], service_date)
    if settings.get("customer_reschedule_enabled") != "yes":
        return []
    state = schedule_state(db, service_date, int(booking["attraction_id"]))
    service_day = parse_service_date(service_date)
    now = venue_now(settings)
    needed = int(booking["admitted"])
    options = []
    for slot in state["slots"]:
        slot_time = str(slot["game_time"])
        slot_dt = slot_datetime(service_day, slot_time, settings)
        if slot_dt < now:
            continue
        if not customer_can_reschedule_to_slot(settings, booking, service_date, slot_time):
            continue
        available = int(slot["available"])
        if is_same_booking_slot(booking, service_date, slot_time):
            available += needed
        if available >= needed:
            options.append(
                {
                    "game_time": slot_time,
                    "display_time": slot["display_time"],
                    "available": available,
                    "current": booking["date"] == service_date and booking["game_time"] == slot_time,
                }
            )
    return options


def move_booking_time(db: Any, booking: dict[str, object], service_date: str, game_time: str) -> dict[str, object]:
    parse_service_date(service_date)
    attraction = get_attraction(db, int(booking["attraction_id"]), include_inactive=True)
    settings = effective_schedule_settings(attraction["settings"], service_date)
    if settings.get("customer_reschedule_enabled") != "yes":
        raise AppError(400, "Online ticket changes are not available for this attraction.")
    game_time = normalize_game_time(game_time)
    if game_time not in slot_times(settings):
        raise AppError(400, "Choose a valid game time.")
    if not customer_can_reschedule_to_slot(settings, booking, service_date, game_time):
        raise AppError(400, "Choose an earlier game time. Online ticket changes are not available for the last game of the day.")
    target_dt = slot_datetime(parse_service_date(service_date), game_time, settings)
    if target_dt < venue_now(settings):
        raise AppError(400, "Choose a future game time.")
    available = slot_availability_excluding(db, service_date, game_time, booking)
    needed = int(booking["admitted"])
    if needed > available:
        raise AppError(409, f"Only {available} spot(s) are available for that game.")
    execute(
        db,
        "UPDATE bookings SET service_date = ?, game_time = ?, updated_at = ? WHERE id = ?",
        (service_date, game_time, utc_now(), int(booking["id"])),
    )
    write_audit(
        db,
        None,
        "booking_rescheduled_public",
        f"booking_id={booking['id']} {booking['date']} {booking['game_time']} -> {service_date} {game_time}",
    )
    return get_booking(db, int(booking["id"]))


def write_audit(db: Any, actor_id: int | None, action: str, details: str) -> None:
    execute(
        db,
        "INSERT INTO audit_log (actor_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (actor_id, action, details, utc_now()),
    )


def make_reschedule_token(booking_id: int) -> str:
    booking_text = str(booking_id)
    signature = hmac.new(APP_SECRET.encode("utf-8"), booking_text.encode("utf-8"), hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(signature[:18]).decode("ascii").rstrip("=")
    return f"{booking_text}.{encoded}"


def verify_reschedule_token(token: str) -> int:
    try:
        booking_raw, provided = token.split(".", 1)
        booking_id = int(booking_raw)
    except ValueError:
        raise AppError(404, "Reschedule link is invalid.")
    expected = make_reschedule_token(booking_id).split(".", 1)[1]
    if not hmac.compare_digest(provided, expected):
        raise AppError(404, "Reschedule link is invalid.")
    return booking_id


def ticket_settings_for_booking(db: Any, booking: dict[str, object]) -> dict[str, str]:
    settings = get_settings(db)
    try:
        attraction = get_attraction(db, int(booking["attraction_id"]), include_inactive=True)
        settings.update(attraction["settings"])
        settings["attraction_name"] = str(attraction["name"])
    except Exception:
        settings.update(DEFAULT_ATTRACTION_SETTINGS)
        settings["attraction_name"] = str(booking.get("attraction_name") or "Attraction")
    return settings


def booking_reschedule_url(settings: dict[str, str], booking: dict[str, object]) -> str:
    if settings["ticket_show_qr"] != "yes":
        return ""
    if settings.get("customer_reschedule_enabled") != "yes":
        return ""
    base_url = settings["public_base_url"].strip().rstrip("/")
    if not base_url:
        return ""
    ticket_code = str(booking.get("ticket_code") or "").strip()
    if ticket_code:
        ticket_pin = str(booking.get("ticket_pin") or "").strip()
        if ticket_pin:
            return f"{base_url}/ticket/{ticket_code}?pin={ticket_pin}"
        return f"{base_url}/ticket/{ticket_code}"
    booking_id = booking.get("id")
    if not isinstance(booking_id, int):
        return ""
    return f"{base_url}/reschedule?token={make_reschedule_token(booking_id)}"


def fallback_favicon_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#17191f"/>
  <path d="M32 12v40M12 32h40" stroke="#d7dce5" stroke-width="4" stroke-linecap="round" opacity=".72"/>
  <circle cx="32" cy="32" r="19" fill="none" stroke="#df1f35" stroke-width="5"/>
  <circle cx="32" cy="32" r="5" fill="#df1f35"/>
</svg>"""


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def raster_logo_data_url(settings: dict[str, str]) -> str:
    try:
        width = as_int(settings.get("ticket_logo_width", "0"), "Logo width")
        height = as_int(settings.get("ticket_logo_height", "0"), "Logo height")
        raster = settings.get("ticket_logo_raster", "").strip()
        if not raster or width < 8 or height < 1 or width % 8 != 0:
            return ""
        raw = base64.b64decode(raster, validate=True)
        row_bytes = width // 8
        if len(raw) != row_bytes * height:
            return ""

        rows = bytearray()
        for y in range(height):
            rows.append(0)
            for x in range(width):
                byte = raw[(y * row_bytes) + (x // 8)]
                is_black = bool(byte & (0x80 >> (x % 8)))
                rows.extend(b"\x11\x11\x11\xff" if is_black else b"\xff\xff\xff\xff")

        png = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + png_chunk(b"IEND", b"")
        )
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    except Exception:
        return ""


def favicon_svg(settings: dict[str, str]) -> str:
    preview = (
        settings.get("app_logo_image", "").strip()
        or settings.get("ticket_logo_preview", "").strip()
        or raster_logo_data_url(settings)
    )
    if not preview:
        return fallback_favicon_svg()
    safe_preview = html.escape(preview, quote=True)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#ffffff"/>
  <image href="{safe_preview}" x="6" y="6" width="52" height="52" preserveAspectRatio="xMidYMid meet"/>
</svg>"""


def wrap_ticket_lines(lines: list[str], width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if line == QR_CODE_MARKER:
            wrapped.append(line)
            continue
        if not line:
            wrapped.append("")
            continue
        wrapped.extend(
            textwrap.wrap(
                line,
                width=width,
                break_long_words=True,
                break_on_hyphens=False,
                replace_whitespace=False,
            )
            or [line]
        )
    return wrapped


def build_ticket_text(settings: dict[str, str], booking: dict[str, object], qr_url: str | None = None) -> str:
    service_date = date.fromisoformat(str(booking["date"])).strftime("%b %d, %Y")
    type_label = "Birthday Party" if booking["booking_type"] == "party" else "Walk-Up Group"
    game_time_label = format_display_time(str(booking["game_time"]))
    attraction_name = str(settings.get("attraction_name") or booking.get("attraction_name") or "Attraction")
    width = as_int(settings["ticket_width_chars"], "Ticket width")
    lines: list[str] = []
    if settings["ticket_logo_enabled"] == "yes":
        lines.append(settings["ticket_logo_text"].strip() or attraction_name)
    lines.extend(
        [
            settings["ticket_heading"].strip() or "GAME TICKET",
            "",
        ]
    )
    lines.extend(
        [
            f"Group: {booking['group_name']}",
            f"Attraction: {attraction_name}",
            f"Type: {type_label}",
            f"Date: {service_date}",
            f"Game Time: {game_time_label}",
            "",
            f"Players: {booking['admitted']}",
        ]
    )
    if booking.get("notes"):
        lines.extend(["", f"Notes: {booking['notes']}"])
    if settings["ticket_footer"].strip():
        lines.extend(["", settings["ticket_footer"].strip()])
    if qr_url:
        lines.extend(["", settings["ticket_qr_label"].strip() or FRIENDLY_QR_LABEL, QR_CODE_MARKER])
    ticket_code = booking.get("ticket_code") or booking["id"]
    if qr_url:
        lines.append(f"Ticket Code: {ticket_code}")
    else:
        lines.extend(["", f"Ticket Code: {ticket_code}"])
    if booking.get("ticket_pin"):
        lines.append(f"PIN: {booking['ticket_pin']}")
    lines.append("")
    return "\n".join(wrap_ticket_lines(lines, width))


def append_escpos_logo(payload: bytearray, settings: dict[str, str]) -> bool:
    if settings["ticket_logo_enabled"] != "yes" or not settings["ticket_logo_raster"].strip():
        return False
    width = as_int(settings["ticket_logo_width"], "Logo width")
    height = as_int(settings["ticket_logo_height"], "Logo height")
    raw = base64.b64decode(settings["ticket_logo_raster"])
    width_bytes = width // 8
    payload.extend(b"\x1ba\x01")
    payload.extend(b"\x1dv0\x00")
    payload.extend(bytes([width_bytes % 256, width_bytes // 256, height % 256, height // 256]))
    payload.extend(raw)
    payload.extend(b"\n")
    return True


def append_escpos_qr(payload: bytearray, qr_url: str) -> None:
    if not qr_url:
        return

    def qr_command(data: bytes) -> bytes:
        length = len(data)
        return b"\x1d(k" + bytes([length % 256, length // 256]) + data

    raw_url = qr_url.encode("utf-8")
    if len(raw_url) > 7000:
        return
    payload.extend(b"\x1ba\x01")
    payload.extend(qr_command(bytes([49, 65, 50, 0])))
    payload.extend(qr_command(bytes([49, 67, 6])))
    payload.extend(qr_command(bytes([49, 69, 48])))
    payload.extend(qr_command(bytes([49, 80, 48]) + raw_url))
    payload.extend(qr_command(bytes([49, 81, 48])))


def escpos_payload(ticket_text: str, settings: dict[str, str], qr_url: str = "") -> bytes:
    body = ticket_text.replace("\r\n", "\n").replace("\r", "\n")
    payload = bytearray()
    payload.extend(b"\x1b@")
    has_image_logo = append_escpos_logo(payload, settings)
    payload.extend(b"\x1ba\x01")
    lines = body.split("\n")
    logo_text = (settings["ticket_logo_text"].strip() or settings.get("attraction_name", "") or settings["venue_name"]).strip()
    if has_image_logo and lines and lines[0].strip() == logo_text:
        lines = lines[1:]
    printed_qr = False
    for index, line in enumerate(lines):
        if line == QR_CODE_MARKER:
            append_escpos_qr(payload, qr_url)
            printed_qr = True
            continue
        if index == 0:
            payload.extend(b"\x1d!\x11")
            payload.extend(line.encode("ascii", "replace"))
            payload.extend(b"\n")
            payload.extend(b"\x1d!\x00")
        else:
            payload.extend(line.encode("ascii", "replace"))
            payload.extend(b"\n")
    if qr_url and not printed_qr:
        append_escpos_qr(payload, qr_url)
    payload.extend(b"\n" * TICKET_BOTTOM_FEED_LINES)
    payload.extend(b"\x1dV\x00")
    return bytes(payload)


def printable_ticket_text(ticket_text: str) -> str:
    return ticket_text.replace(QR_CODE_MARKER, "[QR code prints here]")


def print_ticket(db: Any, booking: dict[str, object]) -> dict[str, str]:
    settings = ticket_settings_for_booking(db, booking)
    qr_url = booking_reschedule_url(settings, booking)
    ticket_text = build_ticket_text(settings, booking, qr_url)
    ticket_log_text = printable_ticket_text(ticket_text)
    mode = settings["printer_mode"]
    booking_id = booking["id"] if isinstance(booking.get("id"), int) else None

    try:
        if mode == "dry_run":
            message = "Dry run: ticket was logged but not sent to a printer."
        elif mode == "tcp":
            host = settings["printer_host"].strip()
            if not host:
                raise AppError(400, "Printer host is required for TCP printing.")
            port = as_int(settings["printer_port"], "Printer port")
            with socket.create_connection((host, port), timeout=6) as printer:
                printer.sendall(escpos_payload(ticket_text, settings, qr_url))
            message = f"Sent to {host}:{port}."
        elif mode == "cups":
            queue = settings["cups_queue"].strip()
            if not queue:
                raise AppError(400, "CUPS queue is required.")
            subprocess.run(
                ["lp", "-d", queue],
                input=(ticket_log_text + ("\n" * TICKET_BOTTOM_FEED_LINES)).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=10,
            )
            message = f"Sent to CUPS queue {queue}."
        else:
            raise AppError(400, "Unknown printer mode.")

        execute(
            db,
            """
            INSERT INTO print_logs (booking_id, mode, status, message, ticket_text, created_at)
            VALUES (?, ?, 'ok', ?, ?, ?)
            """,
            (booking_id, mode, message, ticket_log_text, utc_now()),
        )
        return {"status": "ok", "message": message, "ticket_text": ticket_log_text}
    except Exception as exc:
        message = exc.message if isinstance(exc, AppError) else str(exc)
        execute(
            db,
            """
            INSERT INTO print_logs (booking_id, mode, status, message, ticket_text, created_at)
            VALUES (?, ?, 'error', ?, ?, ?)
            """,
            (booking_id, mode, message, ticket_log_text, utc_now()),
        )
        return {"status": "error", "message": message, "ticket_text": ticket_log_text}


def create_session(user: Any) -> str:
    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "id": int(user["id"]),
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "expires": datetime.now(timezone.utc) + SESSION_TTL,
    }
    return token


def clear_expired_sessions() -> None:
    now = datetime.now(timezone.utc)
    expired = [token for token, session in sessions.items() if session["expires"] < now]
    for token in expired:
        sessions.pop(token, None)


def cookie_header(token: str, max_age: int | None = None) -> str:
    cookie = SimpleCookie()
    cookie[COOKIE_NAME] = token
    cookie[COOKIE_NAME]["path"] = "/"
    cookie[COOKIE_NAME]["httponly"] = True
    cookie[COOKIE_NAME]["samesite"] = "Lax"
    if max_age is not None:
        cookie[COOKIE_NAME]["max-age"] = str(max_age)
    return cookie.output(header="").strip()


class LaserTagHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        self.handle_request("GET")

    def do_POST(self) -> None:
        self.handle_request("POST")

    def do_DELETE(self) -> None:
        self.handle_request("DELETE")

    def handle_request(self, method: str) -> None:
        try:
            clear_expired_sessions()
            parsed = urlparse(self.path)
            if parsed.path == "/reschedule":
                self.handle_reschedule(method, parse_qs(parsed.query))
            elif parsed.path == "/ticket" or parsed.path.startswith("/ticket/"):
                self.handle_ticket(method, parsed.path, parse_qs(parsed.query))
            elif parsed.path == "/favicon.svg":
                self.serve_favicon()
            elif parsed.path.startswith("/api/"):
                self.handle_api(method, parsed.path, parse_qs(parsed.query))
            else:
                self.serve_static(parsed.path)
        except AppError as exc:
            self.write_json({"error": exc.message}, status=exc.status)
        except Exception as exc:
            traceback.print_exc()
            self.write_json({"error": f"Server error: {exc}"}, status=500)

    def serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            target = STATIC_DIR / "index.html"
        else:
            safe_path = path.lstrip("/")
            target = STATIC_DIR / safe_path
        target = target.resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists() or target.is_dir():
            raise AppError(404, "Not found.")

        content_type = "application/octet-stream"
        if target.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif target.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"

        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_favicon(self) -> None:
        with connect_db() as db:
            body = favicon_svg(get_settings(db)).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def reschedule_shell(self, title: str, content: str) -> str:
        safe_title = html.escape(title)
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <style>
      :root {{
        color-scheme: light;
        --ink: #17191f;
        --muted: #5d6470;
        --line: #d9dde5;
        --paper: #ffffff;
        --panel: #f4f6f9;
        --signal: #df1f35;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: var(--panel);
        color: var(--ink);
        display: grid;
        place-items: start center;
        padding: 28px 14px;
      }}
      main {{
        width: min(100%, 520px);
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 14px;
        box-shadow: 0 18px 45px rgba(23, 25, 31, 0.11);
        padding: 22px;
      }}
      h1 {{ margin: 0 0 6px; font-size: 1.8rem; line-height: 1.05; }}
      h2 {{ margin: 22px 0 10px; font-size: 1.05rem; }}
      p {{ color: var(--muted); line-height: 1.45; }}
      .ticket-meta {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        margin: 18px 0;
      }}
      .ticket-meta div {{
        border: 1px solid var(--line);
        border-radius: 9px;
        padding: 10px;
        background: var(--panel);
      }}
      .ticket-meta span {{
        display: block;
        color: var(--muted);
        font-size: 0.75rem;
        font-weight: 800;
        text-transform: uppercase;
      }}
      .ticket-meta strong {{ display: block; margin-top: 4px; }}
      form {{ display: grid; gap: 12px; margin-top: 12px; }}
      label {{ display: grid; gap: 6px; color: var(--muted); font-weight: 800; font-size: 0.82rem; }}
      input, select {{
        width: 100%;
        min-height: 44px;
        border: 1px solid var(--line);
        border-radius: 9px;
        padding: 0 12px;
        font: inherit;
        color: var(--ink);
        background: #fff;
      }}
      button {{
        min-height: 44px;
        border: 0;
        border-radius: 9px;
        background: var(--signal);
        color: white;
        font-weight: 900;
        cursor: pointer;
      }}
      .secondary {{
        background: var(--ink);
      }}
      .message {{
        border: 1px solid var(--line);
        border-radius: 9px;
        padding: 12px;
        background: var(--panel);
      }}
      .error {{
        border-color: #f0b8bf;
        background: #fff2f3;
        color: #a51022;
      }}
      @media (max-width: 460px) {{
        main {{ padding: 18px; }}
        .ticket-meta {{ grid-template-columns: 1fr; }}
      }}
    </style>
  </head>
  <body>
    <main>{content}</main>
  </body>
</html>"""

    def handle_ticket(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        if method not in {"GET", "POST"}:
            raise AppError(405, "Method not allowed.")

        try:
            parts = path.strip("/").split("/")
            ticket_code = ""
            ticket_pin = ""
            if len(parts) == 2 and parts[0] == "ticket":
                ticket_code = parts[1]
            elif path == "/ticket":
                ticket_code = query.get("code", [""])[0]
                ticket_pin = query.get("pin", [""])[0]
            if not ticket_code:
                self.write_html(self.render_ticket_lookup())
                return

            ticket_code = normalize_ticket_code(ticket_code)
            form = self.read_form() if method == "POST" else {}
            if method == "POST":
                ticket_pin = form.get("pin", [""])[0]
            else:
                ticket_pin = ticket_pin or query.get("pin", [""])[0]
            if not ticket_pin:
                self.write_html(self.render_ticket_pin_prompt(ticket_code))
                return
            with connect_db() as db:
                booking = get_booking_by_ticket_credentials(db, ticket_code, ticket_pin)
                if booking["status"] != "booked":
                    self.write_html(
                        self.reschedule_shell(
                            "Ticket unavailable",
                            "<h1>Ticket unavailable</h1><p class=\"message error\">This ticket is no longer active.</p>",
                        ),
                        status=410,
                    )
                    return
                if method == "POST":
                    updated = move_booking_time(db, booking, str(booking["date"]), form.get("game_time", [""])[0])
                    self.write_html(self.render_ticket_confirmation(db, updated))
                    return
                self.write_html(self.render_ticket_form(db, booking, ticket_pin))
        except AppError as exc:
            self.write_html(
                self.reschedule_shell(
                    "Ticket problem",
                    f"<h1>Ticket problem</h1><p class=\"message error\">{html.escape(exc.message)}</p>",
                ),
                status=exc.status,
            )

    def render_ticket_lookup(self) -> str:
        content = """
      <h1>Change game time</h1>
      <p>Enter the ticket code and PIN printed on your receipt.</p>
      <form method="get" action="/ticket">
        <label>
          Ticket code
          <input name="code" inputmode="numeric" autocomplete="off" required>
        </label>
        <label>
          PIN
          <input name="pin" inputmode="numeric" autocomplete="off" required>
        </label>
        <button type="submit">Find Ticket</button>
      </form>"""
        return self.reschedule_shell("Find ticket", content)

    def render_ticket_pin_prompt(self, ticket_code: str) -> str:
        safe_code = html.escape(ticket_code)
        content = f"""
      <h1>Change game time</h1>
      <p>Enter the PIN printed on your receipt.</p>
      <form method="get" action="/ticket/{safe_code}">
        <label>
          PIN
          <input name="pin" inputmode="numeric" autocomplete="off" required>
        </label>
        <button type="submit">Find Ticket</button>
      </form>"""
        return self.reschedule_shell("Ticket PIN", content)

    def render_ticket_form(self, db: Any, booking: dict[str, object], ticket_pin: str) -> str:
        settings = ticket_settings_for_booking(db, booking)
        options = available_reschedule_slots(db, booking, str(booking["date"]))
        ticket_code = html.escape(str(booking["ticket_code"]))
        safe_pin = html.escape(ticket_pin)
        service_date = date.fromisoformat(str(booking["date"])).strftime("%b %d, %Y")
        current_time = format_display_time(str(booking["game_time"]))
        group_name = html.escape(str(booking["group_name"]))
        attraction_name = html.escape(str(settings.get("attraction_name") or booking.get("attraction_name") or "Attraction"))
        players = html.escape(str(booking["admitted"]))
        option_markup = "\n".join(
            f"<option value=\"{html.escape(str(option['game_time']))}\" {'selected' if option['current'] else ''}>"
            f"{html.escape(str(option['display_time']))} - {option['available']} open"
            f"{' (current)' if option['current'] else ''}</option>"
            for option in options
        )
        if settings.get("customer_reschedule_enabled") != "yes":
            move_form = "<p class=\"message error\">Online ticket changes are not available for this attraction. Please see the front desk for help.</p>"
        elif options:
            move_form = f"""
      <form method="post" action="/ticket/{ticket_code}">
        <input type="hidden" name="pin" value="{safe_pin}">
        <label>
          New game time for {html.escape(service_date)}
          <select name="game_time" required>
            {option_markup}
          </select>
        </label>
        <button type="submit">Move Ticket</button>
      </form>"""
        else:
            move_form = "<p class=\"message error\">No game times have enough open spots for this ticket.</p>"

        content = f"""
      <h1>{attraction_name}</h1>
      <p>Change this ticket to another available game time.</p>
      <section class="ticket-meta" aria-label="Ticket details">
        <div><span>Ticket code</span><strong>{ticket_code}</strong></div>
        <div><span>PIN</span><strong>{safe_pin}</strong></div>
        <div><span>Group</span><strong>{group_name}</strong></div>
        <div><span>Players</span><strong>{players}</strong></div>
        <div><span>Current game</span><strong>{html.escape(service_date)} at {html.escape(current_time)}</strong></div>
      </section>
      {move_form}"""
        return self.reschedule_shell("Change game time", content)

    def render_ticket_confirmation(self, db: Any, booking: dict[str, object]) -> str:
        settings = ticket_settings_for_booking(db, booking)
        attraction_name = html.escape(str(settings.get("attraction_name") or booking.get("attraction_name") or "Attraction"))
        ticket_code = html.escape(str(booking["ticket_code"]))
        service_date = date.fromisoformat(str(booking["date"])).strftime("%b %d, %Y")
        game_time = format_display_time(str(booking["game_time"]))
        content = f"""
      <h1>{attraction_name}</h1>
      <p class="message">Ticket {ticket_code} was moved to <strong>{html.escape(service_date)} at {html.escape(game_time)}</strong>.</p>
      <p>Keep this page or your printed ticket handy when you arrive.</p>"""
        return self.reschedule_shell("Ticket moved", content)

    def handle_reschedule(self, method: str, query: dict[str, list[str]]) -> None:
        if method not in {"GET", "POST"}:
            raise AppError(405, "Method not allowed.")

        try:
            form = self.read_form() if method == "POST" else {}
            token = (form if method == "POST" else query).get("token", [""])[0]
            booking_id = verify_reschedule_token(token)
            requested_date = (form if method == "POST" else query).get("date", [""])[0]

            with connect_db() as db:
                booking = get_booking(db, booking_id)
                if booking["status"] != "booked":
                    self.write_html(
                        self.reschedule_shell(
                            "Ticket unavailable",
                            "<h1>Ticket unavailable</h1><p class=\"message error\">This booking is no longer active.</p>",
                        ),
                        status=410,
                    )
                    return

                selected_date = requested_date or str(booking["date"])
                try:
                    parse_service_date(selected_date)
                except AppError:
                    selected_date = str(booking["date"])

                if method == "POST":
                    updated = move_booking_time(db, booking, selected_date, form.get("game_time", [""])[0])
                    self.write_html(self.render_reschedule_confirmation(db, updated))
                    return

                self.write_html(self.render_reschedule_form(db, booking, token, selected_date))
        except AppError as exc:
            self.write_html(
                self.reschedule_shell(
                    "Ticket problem",
                    f"<h1>Ticket problem</h1><p class=\"message error\">{html.escape(exc.message)}</p>",
                ),
                status=exc.status,
            )

    def render_reschedule_form(
        self,
        db: Any,
        booking: dict[str, object],
        token: str,
        selected_date: str,
        message: str = "",
    ) -> str:
        settings = ticket_settings_for_booking(db, booking)
        options = available_reschedule_slots(db, booking, selected_date)
        safe_token = html.escape(token)
        safe_date = html.escape(selected_date)
        current_date = date.fromisoformat(str(booking["date"])).strftime("%b %d, %Y")
        selected_date_label = date.fromisoformat(selected_date).strftime("%b %d, %Y")
        current_time = format_display_time(str(booking["game_time"]))
        group_name = html.escape(str(booking["group_name"]))
        attraction_name = html.escape(str(settings.get("attraction_name") or booking.get("attraction_name") or "Attraction"))
        players = html.escape(str(booking["admitted"]))
        option_markup = "\n".join(
            f"<option value=\"{html.escape(str(option['game_time']))}\" {'selected' if option['current'] else ''}>"
            f"{html.escape(str(option['display_time']))} - {option['available']} open"
            f"{' (current)' if option['current'] else ''}</option>"
            for option in options
        )
        notice = f"<p class=\"message error\">{html.escape(message)}</p>" if message else ""
        if settings.get("customer_reschedule_enabled") != "yes":
            move_form = "<p class=\"message error\">Online ticket changes are not available for this attraction. Please see the front desk for help.</p>"
        elif options:
            move_form = f"""
      <form method="post" action="/reschedule">
        <input type="hidden" name="token" value="{safe_token}">
        <input type="hidden" name="date" value="{safe_date}">
        <label>
          New game time for {html.escape(selected_date_label)}
          <select name="game_time" required>
            {option_markup}
          </select>
        </label>
        <button type="submit">Move Ticket</button>
      </form>"""
        else:
            move_form = "<p class=\"message error\">No game times have enough open spots for this ticket on that date.</p>"

        content = f"""
      <h1>{attraction_name}</h1>
      <p>Change this ticket to another available game time.</p>
      {notice}
      <section class="ticket-meta" aria-label="Ticket details">
        <div><span>Ticket</span><strong>#{html.escape(str(booking['id']))}</strong></div>
        <div><span>Group</span><strong>{group_name}</strong></div>
        <div><span>Players</span><strong>{players}</strong></div>
        <div><span>Current game</span><strong>{html.escape(current_date)} at {html.escape(current_time)}</strong></div>
      </section>
      <form method="get" action="/reschedule">
        <input type="hidden" name="token" value="{safe_token}">
        <label>
          Date
          <input type="date" name="date" value="{safe_date}" min="{html.escape(today_iso())}">
        </label>
        <button class="secondary" type="submit">Show Times</button>
      </form>
      {move_form}"""
        return self.reschedule_shell("Change game time", content)

    def render_reschedule_confirmation(self, db: Any, booking: dict[str, object]) -> str:
        settings = ticket_settings_for_booking(db, booking)
        attraction_name = html.escape(str(settings.get("attraction_name") or booking.get("attraction_name") or "Attraction"))
        service_date = date.fromisoformat(str(booking["date"])).strftime("%b %d, %Y")
        game_time = format_display_time(str(booking["game_time"]))
        content = f"""
      <h1>{attraction_name}</h1>
      <p class="message">Ticket #{html.escape(str(booking['id']))} was moved to <strong>{html.escape(service_date)} at {html.escape(game_time)}</strong>.</p>
      <p>Keep this page or your printed ticket handy when you arrive.</p>"""
        return self.reschedule_shell("Ticket moved", content)

    def handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        if method == "POST" and path == "/api/login":
            self.login()
            return
        if method == "POST" and path == "/api/logout":
            self.logout()
            return
        if method == "GET" and path == "/api/public-settings":
            with connect_db() as db:
                settings = get_settings(db)
                self.write_json({"settings": {key: settings[key] for key in PUBLIC_BRANDING_KEYS}})
            return

        actor = self.require_user()

        if method == "GET" and path == "/api/me":
            self.write_json({"user": public_user(actor)})
            return
        if method == "GET" and path == "/api/state":
            requested_date = query.get("date", [today_iso()])[0]
            requested_attraction = query.get("attraction_id", [""])[0]
            with connect_db() as db:
                state = schedule_state(db, requested_date, requested_attraction)
                state["user"] = public_user(actor)
                self.write_json(state)
            return
        if method == "GET" and path == "/api/admin/settings":
            self.require_admin(actor)
            with connect_db() as db:
                self.write_json({"settings": get_settings(db), "attractions": get_attractions(db, include_inactive=True)})
            return
        if method == "POST" and path == "/api/admin/settings":
            self.require_admin(actor)
            payload = self.read_json()
            with connect_db() as db:
                update_settings(db, payload.get("settings", {}), int(actor["id"]))
                if isinstance(payload.get("attraction"), dict):
                    update_attraction(db, payload["attraction"], int(actor["id"]))
                self.write_json({"settings": get_settings(db), "attractions": get_attractions(db, include_inactive=True)})
            return
        if method == "POST" and path == "/api/admin/attractions":
            self.require_admin(actor)
            payload = self.read_json()
            with connect_db() as db:
                attraction = create_attraction(db, payload, int(actor["id"]))
                self.write_json({"attraction": attraction, "attractions": get_attractions(db, include_inactive=True)})
            return
        if method == "POST" and path == "/api/admin/password":
            self.require_admin(actor)
            self.change_password(actor)
            return
        if method == "POST" and path == "/api/blasters":
            self.update_blasters(actor)
            return
        if method == "POST" and path == "/api/bookings":
            payload = self.read_json()
            with connect_db() as db:
                result = create_booking(db, payload, actor)
                state = schedule_state(db, str(payload.get("date") or today_iso()), result["booking"]["attraction_id"])
                self.write_json({"result": result, "state": state})
            return
        if method == "POST" and path.startswith("/api/bookings/"):
            self.booking_action(path, actor)
            return
        if method == "POST" and path == "/api/admin/printer-test":
            self.require_admin(actor)
            with connect_db() as db:
                fake_booking = {
                    "id": "TEST",
                    "attraction_id": default_attraction_id(db),
                    "attraction_name": "Printer Test",
                    "date": today_iso(),
                    "game_time": datetime.now().strftime("%H:%M"),
                    "display_time": datetime.now().strftime("%I:%M %p").lstrip("0"),
                    "group_name": "Printer Test",
                    "players": 1,
                    "admitted": 1,
                    "booking_type": "walkup",
                    "notes": "Test ticket",
                    "status": "booked",
                }
                self.write_json({"print_result": print_ticket(db, fake_booking)})
            return

        raise AppError(404, "API route not found.")

    def login(self) -> None:
        payload = self.read_json()
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        with connect_db() as db:
            row = execute(db, "SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                raise AppError(401, "Invalid username or password.")
            token = create_session(row)
            write_audit(db, int(row["id"]), "login", "success")
            self.write_json({"user": public_user(sessions[token])}, headers={"Set-Cookie": cookie_header(token)})

    def logout(self) -> None:
        token = self.session_token()
        if token:
            sessions.pop(token, None)
        self.write_json({"ok": True}, headers={"Set-Cookie": cookie_header("", 0)})

    def update_blasters(self, actor: dict[str, object]) -> None:
        payload = self.read_json()
        service_date = str(payload.get("date") or today_iso())
        parse_service_date(service_date)
        effective_at = normalize_effective_at(str(payload.get("effective_at") or current_effective_at()))
        active_blasters = as_int(payload.get("active_blasters", 0), "Active blasters")
        if active_blasters < 1 or active_blasters > 200:
            raise AppError(400, "Active blasters must be between 1 and 200.")

        with connect_db() as db:
            attraction = get_attraction(db, payload.get("attraction_id"), include_inactive=False)
            attraction_id = int(attraction["id"])
            execute(db, "DELETE FROM capacity_events WHERE attraction_id = ? AND effective_at > ?", (attraction_id, effective_at))
            execute(
                db,
                """
                INSERT INTO capacity_events (attraction_id, effective_at, active_blasters, updated_by, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(attraction_id, effective_at) DO UPDATE SET
                    active_blasters=excluded.active_blasters,
                    updated_by=excluded.updated_by,
                    created_at=excluded.created_at
                """,
                (attraction_id, effective_at, active_blasters, int(actor["id"]), utc_now()),
            )
            write_audit(db, int(actor["id"]), "capacity_updated", f"attraction_id={attraction_id} {effective_at}={active_blasters}")
            self.write_json(schedule_state(db, service_date, attraction_id))

    def booking_action(self, path: str, actor: dict[str, object]) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 4:
            raise AppError(404, "Booking action not found.")
        try:
            booking_id = int(parts[2])
        except ValueError:
            raise AppError(404, "Booking action not found.")
        action = parts[3]
        with connect_db() as db:
            booking = get_booking(db, booking_id)
            if action == "cancel":
                updated = cancel_booking(db, booking_id, int(actor["id"]))
                self.write_json({"booking": updated, "state": schedule_state(db, str(updated["date"]), int(updated["attraction_id"]))})
                return
            if action == "reprint":
                if booking["status"] != "booked":
                    raise AppError(400, "Cannot reprint a cancelled booking.")
                print_result = print_ticket(db, booking)
                self.write_json({"booking": booking, "print_result": print_result})
                return
        raise AppError(404, "Booking action not found.")

    def change_password(self, actor: dict[str, object]) -> None:
        payload = self.read_json()
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        if username not in {"admin", "marshal"}:
            raise AppError(400, "Only admin and marshal passwords can be changed in this version.")
        if len(password) < 6:
            raise AppError(400, "Password must be at least 6 characters.")
        with connect_db() as db:
            execute(db, "UPDATE users SET password_hash = ? WHERE username = ?", (hash_password(password), username))
            write_audit(db, int(actor["id"]), "password_changed", username)
            self.write_json({"ok": True})

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except ValueError:
            raise AppError(400, "Invalid JSON body.")

    def read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        return parse_qs(raw.decode("utf-8"), keep_blank_values=True)

    def session_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie") or ""
        cookie = SimpleCookie(raw_cookie)
        morsel = cookie.get(COOKIE_NAME)
        return morsel.value if morsel else None

    def current_user(self) -> dict[str, object] | None:
        token = self.session_token()
        if not token:
            return None
        session = sessions.get(token)
        if not session:
            return None
        if session["expires"] < datetime.now(timezone.utc):
            sessions.pop(token, None)
            return None
        session["expires"] = datetime.now(timezone.utc) + SESSION_TTL
        return session

    def require_user(self) -> dict[str, object]:
        user = self.current_user()
        if not user:
            raise AppError(401, "Login required.")
        return user

    def require_admin(self, actor: dict[str, object]) -> None:
        if actor.get("role") != "admin":
            raise AppError(403, "Admin access required.")

    def write_json(self, payload: dict[str, object], status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def public_user(user: dict[str, object]) -> dict[str, object]:
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


def main() -> None:
    initialize_db()
    host = os.environ.get("LASERTAG_HOST", "127.0.0.1")
    port = int(os.environ.get("LASERTAG_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), LaserTagHandler)
    print(f"ArenaFlow running at http://{host}:{port}")
    if DB_BACKEND == "postgres":
        print("Database: PostgreSQL")
    else:
        print(f"Database: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
