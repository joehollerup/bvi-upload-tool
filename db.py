#!/usr/bin/env python3
"""SQLite persistence layer for BVI upload app."""

import json
import os
import sqlite3

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bvi.db")


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
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


def upsert_client(client_config):
    """Insert or update a client row. Returns client_id."""
    name = client_config["client_name"]
    brand_key = client_config["brand_key"]
    config_json = json.dumps(client_config)

    with _connect() as conn:
        # Look for existing client with same brand_key
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
    with _connect() as conn:
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
    with _connect() as conn:
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
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM clients WHERE id = ?", (client_id,)
        ).fetchone()


def get_score_runs(client_id):
    """Return list of score_run rows for a client, sorted by month."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM score_runs WHERE client_id = ? ORDER BY month",
            (client_id,),
        ).fetchall()
    return rows
