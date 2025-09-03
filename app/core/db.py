"""
SQLite database layer with WAL mode and complete schema
"""
from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from decimal import Decimal


def initialize_database(db_path: str) -> None:
    """Initialize database with WAL mode and create all application tables."""
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(str(path)) as conn:
        cur = conn.cursor()
        
        # Enable WAL mode and performance optimizations
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        cur.execute("PRAGMA cache_size=10000;")
        
        # Create application tables per spec
        create_schema(cur)
        conn.commit()


def create_schema(cur: sqlite3.Cursor) -> None:
    """Create all application tables."""
    
    # decisions: agent audit trail
    cur.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            agent TEXT CHECK(agent IN ('PLANNER','TRADER','JUDGE')) NOT NULL,
            trace_id TEXT,
            payload_json TEXT NOT NULL,
            plan_id INTEGER,
            proposal_id INTEGER
        )
    """)
    
    # trades: executed orders with idempotency
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT CHECK(side IN ('BUY','SELL')) NOT NULL,
            qty TEXT NOT NULL,
            price TEXT NOT NULL,
            fee TEXT,
            order_id TEXT,
            idempotency_key TEXT UNIQUE,
            proposal_id INTEGER,
            status TEXT DEFAULT 'FILLED'
        )
    """)
    
    # portfolio: mark-to-market snapshots
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            balance_usdt TEXT NOT NULL,
            balance_btc TEXT NOT NULL,
            unrealized_pnl_usdt TEXT NOT NULL,
            realized_pnl_usdt TEXT NOT NULL
        )
    """)
    
    # memory: experiment tracking
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            key TEXT NOT NULL,
            value_json TEXT NOT NULL
        )
    """)
    
    # Create indexes for performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts_utc);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_decisions_trace ON decisions(trace_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts_utc);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_ts ON portfolio(ts_utc);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(key);")


class DatabaseManager:
    """Simple database access layer with connection management."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path).expanduser().resolve()
        initialize_database(str(self.db_path))
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def log_decision(self, agent: str, payload: Dict[Any, Any], trace_id: str, 
                    plan_id: Optional[int] = None, proposal_id: Optional[int] = None) -> int:
        """Log agent decision to audit trail."""
        ts = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload, default=str)
        
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO decisions (ts_utc, agent, trace_id, payload_json, plan_id, proposal_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ts, agent, trace_id, payload_json, plan_id, proposal_id))
            return cur.lastrowid
    
    def log_trade(self, symbol: str, side: str, qty: str, price: str, 
                  idempotency_key: str, proposal_id: int, 
                  fee: str = "0", order_id: Optional[str] = None) -> int:
        """Log executed trade."""
        ts = datetime.now(timezone.utc).isoformat()
        
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO trades (ts_utc, symbol, side, qty, price, fee, order_id, 
                                  idempotency_key, proposal_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ts, symbol, side, qty, price, fee, order_id, idempotency_key, proposal_id))
            return cur.lastrowid
    
    def snapshot_portfolio(self, balance_usdt: str, balance_btc: str, 
                          unrealized_pnl: str, realized_pnl: str) -> int:
        """Create portfolio snapshot."""
        ts = datetime.now(timezone.utc).isoformat()
        
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO portfolio (ts_utc, balance_usdt, balance_btc, 
                                     unrealized_pnl_usdt, realized_pnl_usdt)
                VALUES (?, ?, ?, ?, ?)
            """, (ts, balance_usdt, balance_btc, unrealized_pnl, realized_pnl))
            return cur.lastrowid
    
    def write_experiment(self, key: str, value: Dict[Any, Any]) -> int:
        """Store experiment result."""
        ts = datetime.now(timezone.utc).isoformat()
        value_json = json.dumps(value, default=str)
        
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO memory (ts_utc, key, value_json)
                VALUES (?, ?, ?)
            """, (ts, key, value_json))
            return cur.lastrowid
    
    def read_posteriors(self) -> Dict[str, Any]:
        """Read recent experiment results for agent context."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT key, value_json, ts_utc 
                FROM memory 
                ORDER BY ts_utc DESC 
                LIMIT 50
            """)
            
            results = {}
            for row in cur.fetchall():
                try:
                    results[row['key']] = json.loads(row['value_json'])
                except json.JSONDecodeError:
                    continue
            return results


def decimal_to_str(value: Decimal) -> str:
    """Convert Decimal to string for database storage."""
    return str(value)


def str_to_decimal(value: str) -> Decimal:
    """Convert string from database to Decimal."""
    return Decimal(value)


