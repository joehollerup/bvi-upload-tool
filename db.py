#!/usr/bin/env python3
"""Persistence layer for the BVI upload app.

Uses Supabase Postgres when SUPABASE_URL is set in the environment (the
Render deployment). Falls back to a local SQLite file when it is unset, so
local development keeps working with zero credentials.

Supabase access uses the SERVICE ROLE key (SUPABASE_SERVICE_ROLE_KEY), never
the anon key: this module runs server-side only and needs full table access,
bypassing Row Level Security by design (RLS is still enabled on both tables
in the DDL below, so the anon/authenticated roles get no access at all).

Table names are prefixed bvi_ (bvi_clients, bvi_score_runs) so they can't
collide with anything else in a shared Supabase project.

This module never creates tables programmatically against Supabase. Run
SUPABASE_SCHEMA_SQL once in the Supabase SQL editor before first use
against Supabase (`python3 db.py` prints it; init_db() also prints it as a
reminder whenever Supabase mode is active).
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

USE_SUPABASE = bool(SUPABASE_URL)

CLIENTS_TABLE = "bvi_clients"
SCORE_RUNS_TABLE = "bvi_score_runs"

_SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bvi.db")

_supabase_client = None


SUPABASE_SCHEMA_SQL = f"""\
-- BVI persistence schema — run once in the Supabase SQL editor.
-- Prefixed bvi_ so these tables can't collide with anything else in
-- this project. RLS is enabled with no policies: only the service role
-- key (used server-side by the app) can read/write; anon/authenticated
-- get zero access by default.

CREATE TABLE IF NOT EXISTS {CLIENTS_TABLE} (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    brand_key   TEXT NOT NULL,
    config_json JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {SCORE_RUNS_TABLE} (
    id                   BIGSERIAL PRIMARY KEY,
    client_id            BIGINT NOT NULL REFERENCES {CLIENTS_TABLE}(id) ON DELETE CASCADE,
    month                TEXT NOT NULL,
    bvi_score            DOUBLE PRECISION,
    momentum             TEXT,
    tier                 TEXT,
    dimensions_json      JSONB,
    flags                TEXT,
    dashboard_data_json  JSONB NOT NULL,
    scored_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (client_id, month)
);

CREATE INDEX IF NOT EXISTS {SCORE_RUNS_TABLE}_client_id_idx
    ON {SCORE_RUNS_TABLE} (client_id);

ALTER TABLE {CLIENTS_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {SCORE_RUNS_TABLE} ENABLE ROW LEVEL SECURITY;
"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── Supabase ─────────────────────────────────────────────────────────────

def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        if not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError(
                "SUPABASE_URL is set but SUPABASE_SERVICE_ROLE_KEY is missing. "
                "Server-side access requires the service role key, not the anon key."
            )
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _supabase_client


# ── SQLite (local dev fallback — no credentials required) ────────────────

def _sqlite_connect():
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_init():
    with _sqlite_connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                brand_key   TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS score_runs (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id            INTEGER NOT NULL REFERENCES clients(id),
                month                TEXT NOT NULL,
                bvi_score            REAL,
                momentum             TEXT,
                tier                 TEXT,
                dimensions_json      TEXT,
                flags                TEXT,
                dashboard_data_json  TEXT NOT NULL,
                scored_at            TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(client_id, month)
            );
        """)


# ── Public API — same signatures regardless of backend ───────────────────

def init_db():
    """Ensure local SQLite storage is ready. No-op against Supabase — this
    module never creates tables there programmatically. Prints the one-time
    DDL as a reminder whenever Supabase mode is active."""
    if USE_SUPABASE:
        print(
            "[db] Supabase mode (SUPABASE_URL set). If bvi_clients / "
            "bvi_score_runs don't exist yet, run this once in the Supabase "
            "SQL editor:\n" + SUPABASE_SCHEMA_SQL,
            file=sys.stderr,
        )
        return
    _sqlite_init()


def upsert_client(client_config):
    """Insert or update a client row (matched by brand_key). Returns client_id."""
    name = client_config["client_name"]
    brand_key = client_config["brand_key"]

    if USE_SUPABASE:
        sb = _get_supabase()
        existing = (
            sb.table(CLIENTS_TABLE).select("id").eq("brand_key", brand_key).execute()
        )
        if existing.data:
            client_id = existing.data[0]["id"]
            sb.table(CLIENTS_TABLE).update({
                "name": name,
                "config_json": client_config,  # JSONB column — pass the dict directly
                "updated_at": _now_iso(),
            }).eq("id", client_id).execute()
        else:
            resp = sb.table(CLIENTS_TABLE).insert({
                "name": name,
                "brand_key": brand_key,
                "config_json": client_config,
            }).execute()
            client_id = resp.data[0]["id"]
        return client_id

    config_json = json.dumps(client_config)
    with _sqlite_connect() as conn:
        row = conn.execute(
            "SELECT id FROM clients WHERE brand_key = ?", (brand_key,)
        ).fetchone()

        if row:
            client_id = row["id"]
            conn.execute(
                "UPDATE clients SET name=?, config_json=?, updated_at=datetime('now') WHERE id=?",
                (name, config_json, client_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO clients (name, brand_key, config_json) VALUES (?, ?, ?)",
                (name, brand_key, config_json),
            )
            client_id = cur.lastrowid

    return client_id


def save_score_runs(client_id, month_rows, results):
    """Upsert one row per month into score_runs.

    month_rows: list of (month_str, storage_dict) from generate_dashboard.generate()
    results: dict keyed by month from score_bvi.compute() (already computed inside generate)
    """
    if USE_SUPABASE:
        sb = _get_supabase()
        records = []
        for month, storage in month_rows:
            r = results.get(month, {})
            flags = r.get("flags")
            records.append({
                "client_id": client_id,
                "month": month,
                "bvi_score": r.get("bvi_score"),
                "momentum": r.get("momentum"),
                "tier": r.get("tier"),
                "dimensions_json": r.get("dimensions") or None,  # JSONB
                "flags": json.dumps(flags) if flags else None,
                "dashboard_data_json": storage,  # JSONB
                "scored_at": _now_iso(),
            })
        if records:
            sb.table(SCORE_RUNS_TABLE).upsert(
                records, on_conflict="client_id,month"
            ).execute()
        return

    with _sqlite_connect() as conn:
        for month, storage in month_rows:
            r = results.get(month, {})
            bvi_score = r.get("bvi_score")
            momentum = r.get("momentum")
            tier = r.get("tier")
            dimensions = r.get("dimensions")
            flags = r.get("flags")

            conn.execute(
                """INSERT INTO score_runs
                       (client_id, month, bvi_score, momentum, tier,
                        dimensions_json, flags, dashboard_data_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(client_id, month) DO UPDATE SET
                       bvi_score=excluded.bvi_score,
                       momentum=excluded.momentum,
                       tier=excluded.tier,
                       dimensions_json=excluded.dimensions_json,
                       flags=excluded.flags,
                       dashboard_data_json=excluded.dashboard_data_json,
                       scored_at=datetime('now')
                """,
                (
                    client_id,
                    month,
                    bvi_score,
                    momentum,
                    tier,
                    json.dumps(dimensions) if dimensions else None,
                    json.dumps(flags) if flags else None,
                    json.dumps(storage),
                ),
            )


def get_all_clients_with_latest_run():
    """Return all clients joined with their most recent score_run, ordered by name."""
    if USE_SUPABASE:
        sb = _get_supabase()
        clients = sb.table(CLIENTS_TABLE).select(
            "id,name,brand_key,config_json,created_at"
        ).execute().data
        runs = (
            sb.table(SCORE_RUNS_TABLE)
            .select("client_id,month,bvi_score,momentum,tier,scored_at")
            .order("month", desc=True)
            .execute()
            .data
        )

        # First hit per client wins — runs are already sorted month desc.
        latest_by_client = {}
        for run in runs:
            latest_by_client.setdefault(run["client_id"], run)

        rows = []
        for c in clients:
            latest = latest_by_client.get(c["id"], {})
            rows.append({
                "id": c["id"],
                "name": c["name"],
                "brand_key": c["brand_key"],
                "config_json": (
                    json.dumps(c["config_json"]) if c["config_json"] is not None else None
                ),
                "created_at": c["created_at"],
                "month": latest.get("month"),
                "bvi_score": latest.get("bvi_score"),
                "momentum": latest.get("momentum"),
                "tier": latest.get("tier"),
                "scored_at": latest.get("scored_at"),
            })
        rows.sort(key=lambda r: r["name"] or "")
        return rows

    with _sqlite_connect() as conn:
        return conn.execute("""
            SELECT c.id, c.name, c.brand_key, c.config_json, c.created_at,
                   sr.month, sr.bvi_score, sr.momentum, sr.tier, sr.scored_at
            FROM clients c
            LEFT JOIN score_runs sr ON sr.id = (
                SELECT id FROM score_runs
                WHERE client_id = c.id
                ORDER BY month DESC
                LIMIT 1
            )
            ORDER BY c.name
        """).fetchall()


def get_client(client_id):
    if USE_SUPABASE:
        sb = _get_supabase()
        resp = sb.table(CLIENTS_TABLE).select("*").eq("id", client_id).execute()
        if not resp.data:
            return None
        row = dict(resp.data[0])
        if row.get("config_json") is not None:
            row["config_json"] = json.dumps(row["config_json"])  # match SQLite: a JSON string
        return row

    with _sqlite_connect() as conn:
        return conn.execute(
            "SELECT * FROM clients WHERE id = ?", (client_id,)
        ).fetchone()


def get_score_runs(client_id):
    """Return list of score_run rows for a client, sorted by month."""
    if USE_SUPABASE:
        sb = _get_supabase()
        resp = (
            sb.table(SCORE_RUNS_TABLE)
            .select("*")
            .eq("client_id", client_id)
            .order("month")
            .execute()
        )
        rows = []
        for r in resp.data:
            row = dict(r)
            # Re-serialize JSONB columns to JSON strings, matching SQLite's
            # TEXT storage, so callers' json.loads(...) keeps working unchanged.
            if row.get("dashboard_data_json") is not None:
                row["dashboard_data_json"] = json.dumps(row["dashboard_data_json"])
            if row.get("dimensions_json") is not None:
                row["dimensions_json"] = json.dumps(row["dimensions_json"])
            rows.append(row)
        return rows

    with _sqlite_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM score_runs WHERE client_id = ? ORDER BY month",
            (client_id,),
        ).fetchall()
    return rows


if __name__ == "__main__":
    print(SUPABASE_SCHEMA_SQL)
