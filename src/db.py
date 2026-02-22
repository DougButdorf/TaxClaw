from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import load_config


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  file_path TEXT NOT NULL,
  file_hash TEXT NOT NULL UNIQUE,
  original_filename TEXT,
  tax_year INTEGER,
  doc_type TEXT,
  filer TEXT,
  payer_name TEXT,
  payer_tin TEXT,
  recipient_name TEXT,
  recipient_tin TEXT,
  account_number TEXT,
  page_count INTEGER,
  extracted_at DATETIME,
  overall_confidence REAL,
  status TEXT DEFAULT 'received',
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions_1099da (
  id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(id),
  asset_code TEXT,
  asset_name TEXT,
  units TEXT,
  date_acquired TEXT,
  date_sold TEXT,
  proceeds TEXT,
  cost_basis TEXT,
  accrued_market_discount TEXT,
  wash_sale_disallowed TEXT,
  basis_reported_to_irs INTEGER,
  proceeds_type TEXT,
  qof_proceeds INTEGER,
  federal_withheld TEXT,
  loss_not_allowed INTEGER,
  gain_loss_term TEXT,
  cash_only INTEGER,
  customer_info_used INTEGER,
  noncovered INTEGER,
  aggregate_flag TEXT,
  transaction_count INTEGER,
  nft_first_sale_proceeds TEXT,
  units_transferred_in TEXT,
  transfer_in_date TEXT,
  form_8949_code TEXT,
  state_name TEXT,
  state_id TEXT,
  state_withheld TEXT,
  confidence REAL,
  raw_json TEXT
);

CREATE TABLE IF NOT EXISTS form_extractions (
  id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(id),
  form_type TEXT NOT NULL,
  raw_json TEXT,
  confidence REAL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def _db_path() -> Path:
    cfg = load_config()
    return cfg.db_path


def connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def init_db() -> None:
    con = connect()
    try:
        con.executescript(SCHEMA)
        con.commit()
    finally:
        con.close()


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def row_to_dict(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {k: r[k] for k in r.keys()}


def json_dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
