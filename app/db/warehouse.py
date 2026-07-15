"""SQLite warehouse — products, pricing, accounts (structured evidence)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Generator

from app.settings import get_settings

_FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "truncate", "create",
    "attach", "pragma", "replace",
)


def connect() -> sqlite3.Connection:
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db() -> Generator[sqlite3.Connection, None, None]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
              sku TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              family TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS price_list (
              sku TEXT NOT NULL,
              tier TEXT NOT NULL,
              unit_price_usd REAL NOT NULL,
              currency TEXT NOT NULL DEFAULT 'USD',
              effective_from TEXT NOT NULL,
              PRIMARY KEY (sku, tier),
              FOREIGN KEY (sku) REFERENCES products(sku)
            );
            CREATE TABLE IF NOT EXISTS accounts (
              account_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              segment TEXT NOT NULL,
              region TEXT NOT NULL,
              arr_usd REAL NOT NULL,
              champion TEXT
            );
            CREATE TABLE IF NOT EXISTS entitlements (
              account_id TEXT NOT NULL,
              sku TEXT NOT NULL,
              seats INTEGER NOT NULL,
              discount_pct REAL NOT NULL,
              PRIMARY KEY (account_id, sku)
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
        if count:
            return
        conn.executemany(
            "INSERT INTO products(sku, name, family) VALUES (?, ?, ?)",
            [
                ("CS-ENT", "Cloud Shield", "Security"),
                ("DF-ENT", "Data Fabric", "Data"),
                ("OBS-SU", "Observability Suite", "Ops"),
            ],
        )
        conn.executemany(
            "INSERT INTO price_list(sku, tier, unit_price_usd, currency, effective_from) VALUES (?, ?, ?, ?, ?)",
            [
                ("CS-ENT", "Enterprise", 120.0, "USD", "2024-01-01"),
                ("CS-ENT", "SMB", 80.0, "USD", "2024-01-01"),
                ("DF-ENT", "Enterprise", 220.0, "USD", "2024-01-01"),
                ("DF-ENT", "SMB", 150.0, "USD", "2024-01-01"),
                ("OBS-SU", "Enterprise", 95.0, "USD", "2024-03-01"),
                ("OBS-SU", "SMB", 60.0, "USD", "2024-03-01"),
            ],
        )
        conn.executemany(
            "INSERT INTO accounts(account_id, name, segment, region, arr_usd, champion) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("ACC-NS", "Northstar Manufacturing", "Enterprise", "North America", 820000, "Priya Nair"),
                ("ACC-HE", "Helios Energy", "Enterprise", "EMEA", 540000, "Jonas Berg"),
                ("ACC-OR", "Orbit Retail", "SMB", "APAC", 120000, "Mei Chen"),
            ],
        )
        conn.executemany(
            "INSERT INTO entitlements(account_id, sku, seats, discount_pct) VALUES (?, ?, ?, ?)",
            [
                ("ACC-NS", "CS-ENT", 400, 18.0),
                ("ACC-NS", "DF-ENT", 120, 12.0),
                ("ACC-HE", "OBS-SU", 200, 10.0),
                ("ACC-OR", "CS-ENT", 40, 5.0),
            ],
        )


def run_sql(query: str) -> dict[str, Any]:
    cleaned = query.strip().rstrip(";")
    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return {"ok": False, "error": "Only SELECT/WITH allowed", "rows": []}
    if any(tok in lowered for tok in _FORBIDDEN):
        return {"ok": False, "error": "Forbidden SQL keyword", "rows": []}
    if ";" in cleaned:
        return {"ok": False, "error": "Multiple statements not allowed", "rows": []}
    try:
        with db() as conn:
            cur = conn.execute(cleaned)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(zip(cols, row, strict=True)) for row in cur.fetchmany(50)]
        return {"ok": True, "columns": cols, "rows": rows, "citation_ids": _row_citations(rows)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "rows": []}


def _row_citations(rows: list[dict]) -> list[str]:
    cites = []
    for r in rows:
        if "account_id" in r:
            cites.append(f"sql:accounts:{r['account_id']}")
        if "sku" in r and "tier" in r:
            cites.append(f"sql:price_list:{r['sku']}:{r['tier']}")
        elif "sku" in r and "discount_pct" in r:
            cites.append(f"sql:entitlements:{r.get('account_id', 'x')}:{r['sku']}")
        elif "sku" in r and "tier" not in r and "account_id" not in r:
            cites.append(f"sql:products:{r['sku']}")
        if not any(k in r for k in ("account_id", "sku")):
            cites.append("sql:query_result")
    seen = set()
    out = []
    for c in cites:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def schema_text() -> str:
    return (
        "TABLE products(sku, name, family)\n"
        "TABLE price_list(sku, tier, unit_price_usd, currency, effective_from)\n"
        "TABLE accounts(account_id, name, segment, region, arr_usd, champion)\n"
        "TABLE entitlements(account_id, sku, seats, discount_pct)\n"
        "Sample: SELECT * FROM price_list WHERE sku='CS-ENT';\n"
        "Sample: SELECT a.name, e.sku, e.discount_pct FROM accounts a "
        "JOIN entitlements e ON a.account_id=e.account_id WHERE a.name LIKE '%Northstar%';"
    )
