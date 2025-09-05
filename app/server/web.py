from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from app.core.config import Settings
from app.core.db import initialize_database
from dotenv import load_dotenv; load_dotenv()


def _connect(db_path: str) -> sqlite3.Connection:
    """Create database connection with optimal settings for concurrent access."""
    conn = sqlite3.connect(
        db_path,
        timeout=5.0,  # 5 second timeout to prevent hanging
        check_same_thread=False  # Allow connection sharing (FastAPI is thread-safe)
    )
    conn.row_factory = sqlite3.Row
    
    # Enable WAL mode for better concurrent access (idempotent)
    conn.execute("PRAGMA journal_mode=WAL")
    # Set reasonable busy timeout
    conn.execute("PRAGMA busy_timeout=5000")  # 5 seconds
    
    return conn


def _pretty_time(ts_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts_iso


def _safe_json_load(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        return {"raw": s[:2000]}


def _badge(text: str, color: str) -> str:
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;background:{color};color:#111;font-weight:600;font-size:12px">{text}</span>'


def _css() -> str:
    return """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
      
      * { 
        margin: 0; 
        padding: 0; 
        box-sizing: border-box; 
      }
      
      body { 
        font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif; 
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #0f3460 100%);
        color: #ffffff;
        min-height: 100vh;
        overflow-x: hidden;
        position: relative;
      }
      
      body::before {
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: 
          radial-gradient(circle at 20% 30%, rgba(0, 255, 136, 0.1) 0%, transparent 70%),
          radial-gradient(circle at 80% 70%, rgba(255, 64, 129, 0.1) 0%, transparent 70%),
          radial-gradient(circle at 40% 80%, rgba(64, 224, 255, 0.1) 0%, transparent 70%);
        pointer-events: none;
        z-index: 0;
      }
      
      .container { 
        max-width: 1000px; 
        margin: 0 auto; 
        padding: 40px 20px;
        position: relative;
        z-index: 1;
      }
      
      .session-status {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 24px;
        padding: 40px;
        text-align: center;
        margin-bottom: 40px;
        position: relative;
        overflow: hidden;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
      }
      
      .session-status::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
        transition: left 0.8s ease;
      }
      
      .session-status:hover::before {
        left: 100%;
      }
      
      .session-status:hover {
        transform: translateY(-5px);
        box-shadow: 0 20px 60px rgba(0, 255, 136, 0.2);
        border-color: rgba(0, 255, 136, 0.3);
      }
      
      .ai-title {
        font-size: clamp(32px, 5vw, 56px);
        font-weight: 700;
        background: linear-gradient(135deg, #00ff88, #40e0ff, #ff4081);
        background-size: 200% 200%;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 16px;
        animation: gradientShift 4s ease-in-out infinite;
      }
      
      @keyframes gradientShift {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
      }
      
      .session-info {
        font-size: 18px;
        opacity: 0.8;
        margin-bottom: 32px;
        letter-spacing: 0.5px;
      }
      
      .status-indicator {
        display: inline-flex;
        align-items: center;
        gap: 12px;
        font-size: 28px;
        font-weight: 600;
        padding: 16px 32px;
        border-radius: 50px;
        margin-bottom: 20px;
        position: relative;
        overflow: hidden;
      }
      
      .status-working {
        background: linear-gradient(135deg, #00ff88, #00d4aa);
        color: #000;
        box-shadow: 0 8px 32px rgba(0, 255, 136, 0.3);
        animation: pulse 2s infinite;
      }
      
      .status-idle {
        background: linear-gradient(135deg, #ffb347, #ff9500);
        color: #000;
        box-shadow: 0 8px 32px rgba(255, 179, 71, 0.3);
      }
      
      .status-error {
        background: linear-gradient(135deg, #ff4081, #ff1744);
        color: #fff;
        box-shadow: 0 8px 32px rgba(255, 64, 129, 0.3);
      }
      
      @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
      }
      
      .status-detail {
        font-size: 16px;
        opacity: 0.7;
      }
      
      .history-section {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 24px;
        padding: 32px;
        position: relative;
        overflow: hidden;
      }
      
      .history-title {
        font-size: 28px;
        font-weight: 600;
        text-align: center;
        margin-bottom: 32px;
        color: #fff;
      }
      
      .decision-timeline {
        max-height: 500px;
        overflow-y: auto;
        padding-right: 8px;
      }
      
      .decision-timeline::-webkit-scrollbar {
        width: 6px;
      }
      
      .decision-timeline::-webkit-scrollbar-track {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 3px;
      }
      
      .decision-timeline::-webkit-scrollbar-thumb {
        background: linear-gradient(45deg, #00ff88, #40e0ff);
        border-radius: 3px;
      }
      
      .decision-item {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 16px;
        position: relative;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        cursor: pointer;
      }
      
      .decision-item:hover {
        background: rgba(255, 255, 255, 0.08);
        border-color: rgba(0, 255, 136, 0.3);
        transform: translateX(8px);
        box-shadow: 0 12px 40px rgba(0, 255, 136, 0.15);
      }
      
      .decision-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
      }
      
      .decision-agent {
        font-size: 18px;
        font-weight: 600;
        background: linear-gradient(45deg, #00ff88, #40e0ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
      }
      
      .decision-time {
        font-size: 12px;
        opacity: 0.6;
        font-weight: 500;
      }
      
      .decision-action {
        font-size: 16px;
        margin-bottom: 8px;
        line-height: 1.5;
      }
      
      .decision-details {
        font-size: 14px;
        opacity: 0.7;
        line-height: 1.4;
      }
      
      .empty-state {
        text-align: center;
        padding: 60px 20px;
        opacity: 0.6;
      }
      
      .empty-state-emoji {
        font-size: 48px;
        margin-bottom: 16px;
        display: block;
      }
      
      @media (max-width: 768px) {
        .container { padding: 20px 16px; }
        .session-status { padding: 24px; }
        .ai-title { font-size: 36px; }
        .history-section { padding: 20px; }
      }
    </style>
    """


app = FastAPI(title="Trader Agent Dashboard", docs_url=None, redoc_url=None)
settings = Settings()

# Ensure database exists with required tables to avoid runtime errors
try:
    initialize_database(settings.db_path)
except Exception:
    # Non-fatal for dashboard; pages will render with empty state
    pass


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _get_system_status() -> Dict[str, Any]:
    """Get current system status and key metrics."""
    try:
        with _connect(settings.db_path) as conn:
            cur = conn.cursor()
            
            # Get latest activity
            cur.execute("""
                SELECT ts_utc, agent FROM decisions 
                ORDER BY id DESC LIMIT 1
            """)
            latest = cur.fetchone()
            
            # Get total trades today
            cur.execute("""
                SELECT COUNT(*) as count FROM trades 
                WHERE date(ts_utc) = date('now')
            """)
            trades_today = cur.fetchone()["count"]
            
            # Get portfolio snapshot
            cur.execute("""
                SELECT balance_usdt, balance_btc, realized_pnl_usdt, unrealized_pnl_usdt 
                FROM portfolio ORDER BY id DESC LIMIT 1
            """)
            portfolio = cur.fetchone()
            
            # Determine system status
            if latest:
                last_activity = datetime.fromisoformat(latest["ts_utc"].replace("Z", "+00:00"))
                minutes_ago = (datetime.now(last_activity.tzinfo) - last_activity).total_seconds() / 60
                
                if minutes_ago < 15:  # Active if activity within 15 minutes
                    status = "WORKING"
                    status_detail = f"Last activity: {minutes_ago:.0f} minutes ago"
                elif minutes_ago < 60:
                    status = "IDLE"
                    status_detail = f"Quiet for {minutes_ago:.0f} minutes"
                else:
                    status = "STOPPED"
                    status_detail = f"No activity for {minutes_ago/60:.1f} hours"
            else:
                status = "STOPPED"
                status_detail = "No trading activity found"
            
            # Calculate total P&L
            total_pnl = 0.0
            if portfolio:
                realized = float(portfolio["realized_pnl_usdt"] or 0)
                unrealized = float(portfolio["unrealized_pnl_usdt"] or 0)
                total_pnl = realized + unrealized
            
            return {
                "status": status,
                "status_detail": status_detail,
                "trades_today": trades_today,
                "total_pnl": total_pnl,
                "portfolio": dict(portfolio) if portfolio else {},
                "last_activity": latest["ts_utc"] if latest else None
            }
    except Exception as e:
        return {
            "status": "ERROR",
            "status_detail": f"Database error: {str(e)}",
            "trades_today": 0,
            "total_pnl": 0.0,
            "portfolio": {},
            "last_activity": None
        }

def _get_simple_activity(limit: int = 5) -> List[Dict[str, Any]]:
    """Get recent activity in simple, human-readable format."""
    try:
        with _connect(settings.db_path) as conn:
            cur = conn.cursor()
            
            # Get recent decisions with readable descriptions
            cur.execute("""
                SELECT d.ts_utc, d.agent, d.payload_json,
                       t.side, t.qty, t.price
                FROM decisions d
                LEFT JOIN trades t ON d.id = t.proposal_id
                ORDER BY d.id DESC LIMIT ?
            """, (limit * 2,))  # Get more to filter for interesting ones
            
            activities = []
            for row in cur.fetchall():
                activity = _format_activity_item(row)
                if activity:
                    activities.append(activity)
                    if len(activities) >= limit:
                        break
            
            return activities
    except Exception:
        return [{"time": "Error", "action": "Could not load activity", "details": "Database connection failed"}]

def _format_activity_item(row) -> Optional[Dict[str, Any]]:
    """Format a database row into a simple activity item."""
    try:
        agent = row["agent"]
        ts = row["ts_utc"]
        time_str = _pretty_time(ts)
        
        if agent == "PLANNER":
            payload = _safe_json_load(row["payload_json"])
            mode = payload.get("mode", "unknown")
            return {
                "time": time_str,
                "action": f"🧠 Brain decided: {mode} mode",
                "details": f"AI is {'actively looking for trades' if mode == 'TRADE' else 'watching the market carefully'}"
            }
            
        elif agent == "TRADER" and row["side"]:  # Only if there was an actual trade
            return {
                "time": time_str,
                "action": f"💰 {row['side'].upper()}: {row['qty']} BTC",
                "details": f"Price: ${float(row['price']):,.2f} per BTC"
            }
            
        elif agent == "JUDGE":
            payload = _safe_json_load(row["payload_json"])
            decision = payload.get("decision", "unknown")
            if decision == "APPROVE":
                return {
                    "time": time_str,
                    "action": "✅ Risk check: APPROVED",
                    "details": "Trade passed all safety checks"
                }
            elif decision == "REJECT":
                return {
                    "time": time_str,
                    "action": "🚫 Risk check: BLOCKED",
                    "details": "Trade blocked for safety reasons"
                }
    except Exception:
        pass
    return None

def _get_decision_history(limit: int = 20) -> List[Dict[str, Any]]:
    """Get decision history for the timeline."""
    try:
        with _connect(settings.db_path) as conn:
            cur = conn.cursor()
            
            cur.execute("""
                SELECT d.ts_utc, d.agent, d.payload_json,
                       t.side, t.qty, t.price
                FROM decisions d
                LEFT JOIN trades t ON d.id = t.proposal_id
                ORDER BY d.id DESC LIMIT ?
            """, (limit,))
            
            decisions = []
            for row in cur.fetchall():
                decision = _format_decision_item(row)
                if decision:
                    decisions.append(decision)
            
            return decisions
    except Exception:
        return []

def _format_decision_item(row) -> Optional[Dict[str, Any]]:
    """Format a database row into a decision timeline item."""
    try:
        agent = row["agent"]
        ts = row["ts_utc"]
        time_str = _pretty_time(ts)
        
        if agent == "PLANNER":
            payload = _safe_json_load(row["payload_json"])
            mode = payload.get("mode", "unknown")
            strategies = payload.get("strategies", [])
            strategy_count = len(strategies)
            
            return {
                "agent": "🧠 PLANNER",
                "time": time_str,
                "action": f"Decided: {mode} mode",
                "details": f"Using {strategy_count} strateg{'ies' if strategy_count != 1 else 'y'} • {'Active trading' if mode == 'TRADE' else 'Market observation'}"
            }
            
        elif agent == "TRADER":
            payload = _safe_json_load(row["payload_json"])
            action = payload.get("action", "unknown")
            qty = payload.get("qty", "0")
            confidence = payload.get("confidence", 0)
            hypothesis = payload.get("hypothesis", "")
            
            if row["side"]:  # Actual trade executed
                return {
                    "agent": "💰 TRADER",
                    "time": time_str,
                    "action": f"Executed: {row['side'].upper()} {row['qty']} BTC",
                    "details": f"Price: ${float(row['price']):,.2f} • {hypothesis[:60]}..." if len(hypothesis) > 60 else f"Price: ${float(row['price']):,.2f} • {hypothesis}"
                }
            else:
                return {
                    "agent": "🤖 TRADER", 
                    "time": time_str,
                    "action": f"Proposed: {action} {qty}",
                    "details": f"Confidence: {confidence:.0%} • {hypothesis[:80]}..." if len(hypothesis) > 80 else f"Confidence: {confidence:.0%} • {hypothesis}"
                }
            
        elif agent == "JUDGE":
            payload = _safe_json_load(row["payload_json"])
            decision = payload.get("decision", "unknown")
            violations = payload.get("violations", [])
            notes = payload.get("notes", "")
            
            if decision == "APPROVE":
                return {
                    "agent": "✅ JUDGE",
                    "time": time_str, 
                    "action": "Approved trade",
                    "details": notes or "All risk checks passed"
                }
            elif decision == "REJECT":
                return {
                    "agent": "🚫 JUDGE",
                    "time": time_str,
                    "action": "Rejected trade",
                    "details": f"{len(violations)} violation(s) • {notes or 'Safety constraints failed'}"
                }
            elif decision == "REVISE":
                return {
                    "agent": "⚠️ JUDGE", 
                    "time": time_str,
                    "action": "Revised trade",
                    "details": notes or "Trade modified for safety"
                }
    except Exception:
        pass
    return None

def _fetch_recent_traces(limit: int = 20) -> List[Dict[str, Any]]:
    with _connect(settings.db_path) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT trace_id, MIN(ts_utc) AS start_ts, MAX(ts_utc) AS end_ts
                FROM decisions
                WHERE trace_id IS NOT NULL AND trace_id != ''
                GROUP BY trace_id
                ORDER BY start_ts DESC
                LIMIT ?
                """,
                (limit,),
            )
        except sqlite3.OperationalError:
            # Likely no tables yet
            return []
        rows = cur.fetchall()

        # Use a single query to fetch all decisions for all traces to avoid race conditions
        if not rows:
            return []
        
        trace_ids = [r["trace_id"] for r in rows]
        placeholders = ",".join(["?" for _ in trace_ids])
        
        # Fetch all decisions at once
        cur.execute(
            f"""
            SELECT trace_id, agent, id, payload_json 
            FROM decisions 
            WHERE trace_id IN ({placeholders}) 
            ORDER BY trace_id, agent, id DESC
            """,
            trace_ids
        )
        all_decisions = cur.fetchall()
        
        # Group decisions by trace_id and agent (taking latest for each)
        decision_map: Dict[str, Dict[str, Dict]] = {}
        trader_ids: Dict[str, Optional[int]] = {}
        
        for decision in all_decisions:
            trace_id = decision["trace_id"]
            agent = decision["agent"]
            
            if trace_id not in decision_map:
                decision_map[trace_id] = {}
            
            if agent not in decision_map[trace_id]:  # Take first (most recent due to ORDER BY)
                decision_map[trace_id][agent] = {
                    "id": decision["id"],
                    "payload": _safe_json_load(decision["payload_json"])
                }
                
                if agent == "TRADER":
                    trader_ids[trace_id] = decision["id"]
        
        # Fetch all trades at once for all trader IDs
        valid_trader_ids = [tid for tid in trader_ids.values() if tid is not None]
        trades_map: Dict[int, List[Dict]] = {}
        
        if valid_trader_ids:
            trade_placeholders = ",".join(["?" for _ in valid_trader_ids])
            cur.execute(
                f"""
                SELECT proposal_id, ts_utc, side, qty, price, fee, order_id 
                FROM trades 
                WHERE proposal_id IN ({trade_placeholders})
                ORDER BY proposal_id, id DESC
                """,
                valid_trader_ids
            )
            for trade in cur.fetchall():
                pid = trade["proposal_id"]
                if pid not in trades_map:
                    trades_map[pid] = []
                trades_map[pid].append(dict(trade))

        traces: List[Dict[str, Any]] = []
        for r in rows:
            trace_id = r["trace_id"]
            
            # Get decisions for this trace
            decisions = decision_map.get(trace_id, {})
            plan = decisions.get("PLANNER", {}).get("payload", {})
            trader = decisions.get("TRADER", {}).get("payload", {})
            judge = decisions.get("JUDGE", {}).get("payload", {})
            
            # Get trades for this trace
            trader_id = trader_ids.get(trace_id)
            trade_list = trades_map.get(trader_id, []) if trader_id else []
            trade_count = len(trade_list)
            last_trade = trade_list[0] if trade_list else None

            traces.append(
                {
                    "trace_id": trace_id,
                    "start_ts": r["start_ts"],
                    "end_ts": r["end_ts"],
                    "plan": plan,
                    "trader": trader,
                    "judge": judge,
                    "trade_count": trade_count,
                    "last_trade": last_trade,
                }
            )

        return traces


@app.get("/", response_class=HTMLResponse)
def home():
    # Get system status and decision history
    status_data = _get_system_status()
    decisions = _get_decision_history(20)
    
    # Determine status styling
    status = status_data["status"]
    if status == "WORKING":
        status_class = "status-working"
        status_emoji = "🚀"
    elif status == "IDLE":
        status_class = "status-idle"
        status_emoji = "⏱️" 
    elif status == "ERROR":
        status_class = "status-error"
        status_emoji = "⚠️"
    else:  # STOPPED
        status_class = "status-idle"
        status_emoji = "⏸️"
    
    # Build decision timeline
    decision_html = ""
    for decision in decisions:
        decision_html += f"""
        <div class="decision-item">
            <div class="decision-header">
                <div class="decision-agent">{decision['agent']}</div>
                <div class="decision-time">{decision['time']}</div>
            </div>
            <div class="decision-action">{decision['action']}</div>
            <div class="decision-details">{decision['details']}</div>
        </div>
        """
    
    if not decision_html:
        decision_html = '''
        <div class="empty-state">
            <div class="empty-state-emoji">🤖</div>
            <div>No decisions yet. Start the AI to see activity.</div>
        </div>
        '''
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>🤖 AI Crypto Trader</title>
        <meta http-equiv="refresh" content="15">
        {_css()}
    </head>
    <body>
        <div class="container">
            <div class="session-status">
                <h1 class="ai-title">AI CRYPTO TRADER</h1>
                <div class="session-info">Trading {settings.symbol} • {settings.mode.upper()} Mode</div>
                
                <div class="status-indicator {status_class}">
                    <span>{status_emoji}</span>
                    <span>{status}</span>
                </div>
                
                <div class="status-detail">{status_data['status_detail']}</div>
            </div>
            
            <div class="history-section">
                <h2 class="history-title">Decision History</h2>
                <div class="decision-timeline">
                    {decision_html}
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


def _fetch_trace_details(trace_id: str) -> Dict[str, Any]:
    with _connect(settings.db_path) as conn:
        cur = conn.cursor()

        try:
            cur.execute(
                "SELECT ts_utc, agent, payload_json, id FROM decisions WHERE trace_id=? ORDER BY id ASC",
                (trace_id,),
            )
        except sqlite3.OperationalError:
            raise HTTPException(status_code=404, detail="No data yet. Run a cycle first.")
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Trace not found")

        plan: Dict[str, Any] = {}
        trader: Dict[str, Any] = {}
        judge: Dict[str, Any] = {}
        first_ts = rows[0]["ts_utc"]

        trader_decision_id: Optional[int] = None

        for r in rows:
            agent = r["agent"]
            payload = _safe_json_load(r["payload_json"])  # type: ignore
            if agent == "PLANNER":
                plan = payload
            elif agent == "TRADER":
                trader = payload
                trader_decision_id = r["id"]
            elif agent == "JUDGE":
                judge = payload

        # trades for this trace (join on proposal_id)
        trades: List[Dict[str, Any]] = []
        if trader_decision_id:
            cur.execute(
                "SELECT ts_utc, side, qty, price, fee, order_id, idempotency_key FROM trades WHERE proposal_id=? ORDER BY id ASC",
                (trader_decision_id,),
            )
            trades = [dict(row) for row in cur.fetchall()]

        # latest portfolio snapshot
        cur.execute(
            "SELECT ts_utc, balance_usdt, balance_btc, unrealized_pnl_usdt, realized_pnl_usdt FROM portfolio ORDER BY id DESC LIMIT 1"
        )
        snap = cur.fetchone()
        snapshot = dict(snap) if snap else {}

        return {
            "start_ts": first_ts,
            "plan": plan,
            "trader": trader,
            "judge": judge,
            "trades": trades,
            "snapshot": snapshot,
        }


@app.get("/advanced", response_class=HTMLResponse)
def advanced_view():
    """Advanced technical view for developers."""
    traces = _fetch_recent_traces(20)

    cards = []
    for t in traces:
        mode = t.get("plan", {}).get("mode", "?")
        action = t.get("trader", {}).get("action", "?")
        qty = t.get("trader", {}).get("qty", "0")
        conf = t.get("trader", {}).get("confidence", 0)
        hypo = t.get("trader", {}).get("hypothesis", "")
        decision = t.get("judge", {}).get("decision", "—")

        # Simple badges
        mode_badge = _badge(mode, "#ffaa00" if mode == "OBSERVE" else "#00ff88")
        if decision == "APPROVE":
            dec_badge = _badge("APPROVE", "#00ff88")
        elif decision == "REVISE":
            dec_badge = _badge("REVISE", "#ffaa00")
        elif decision == "REJECT":
            dec_badge = _badge("REJECT", "#ff4444")
        else:
            dec_badge = _badge("—", "#e5e7eb")

        trade_info = "No trade"
        if t["trade_count"]:
            lt = t.get("last_trade") or {}
            trade_info = f"{lt.get('side','')} {lt.get('qty','')} @ {lt.get('price','')}"

        cards.append(
            f"""
            <div style="background:#2a2a2a; border-radius:8px; padding:16px; margin-bottom:16px;">
              <div style="display:flex; gap:12px; align-items:center; margin-bottom:12px;">
                <div style="font-weight:700;">#{t['trace_id'][:8]}</div>
                <div style="font-size:12px; opacity:0.7;">{_pretty_time(t['start_ts'])}</div>
                <div>{mode_badge}</div>
                <div>{dec_badge}</div>
              </div>
              <div style="margin:8px 0; font-size:14px;"><span style="opacity:0.7;">Proposal:</span> <b>{action}</b> {qty} <span style="opacity:0.7;">(conf {conf:.2f})</span></div>
              <div style="margin:8px 0; font-size:14px;"><span style="opacity:0.7;">Why:</span> {hypo or '<span style="opacity:0.5;">—</span>'}</div>
              <div style="margin:8px 0; font-size:14px;"><span style="opacity:0.7;">Trade:</span> {trade_info}</div>
              <a href="/trace/{t['trace_id']}" style="color:#00aaff; text-decoration:none; font-size:14px;">View details →</a>
            </div>
            """
        )

    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Advanced Trader View</title>
        <style>
            body {{ 
                margin:0; padding:20px; 
                font-family: monospace; 
                background:#1a1a1a; color:#ffffff; 
            }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            h1 {{ color: #00aaff; }}
            .back-btn {{ 
                display: inline-block;
                padding: 8px 16px;
                background: #333;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/" class="back-btn">← Back to Simple View</a>
            <h1>🤖 Advanced Trader Timeline</h1>
            <p>Symbol {settings.symbol} • Mode {settings.mode} • Deposit Cap {settings.deposit_cap_usdt} USDT</p>
            {''.join(cards) if cards else '<div>No activity yet. Run a cycle to see decisions here.</div>'}
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)

@app.get("/trace/{trace_id}", response_class=HTMLResponse)
def trace_page(trace_id: str):
    d = _fetch_trace_details(trace_id)

    def _json_block(o: Any) -> str:
        try:
            txt = json.dumps(o, indent=2, ensure_ascii=False)
        except Exception:
            txt = str(o)
        return f"<pre class=mono>{txt}</pre>"

    plan = d.get("plan", {})
    trader = d.get("trader", {})
    judge = d.get("judge", {})
    trades = d.get("trades", [])
    snapshot = d.get("snapshot", {})

    decision = judge.get("decision", "—")
    if decision == "APPROVE":
        dec_badge = _badge("APPROVE", "var(--good)")
    elif decision == "REVISE":
        dec_badge = _badge("REVISE", "var(--warn)")
    elif decision == "REJECT":
        dec_badge = _badge("REJECT", "var(--bad)")
    else:
        dec_badge = _badge("—", "#e5e7eb")

    trades_html = []
    for t in trades:
        trades_html.append(
            f"<div class=kv><span class=k>{_pretty_time(t['ts_utc'])}</span> <b>{t['side']}</b> {t['qty']} @ {t['price']} <span class=muted>fee {t['fee']}</span></div>"
        )

    html = f"""
    <html><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1">{_css()}</head>
    <body>
      <div class=wrap>
        <div class=title>🧠 Trace {trace_id[:8]}</div>
        <div class=subtitle>{_pretty_time(d['start_ts'])} • {settings.symbol} • {settings.mode}</div>

        <div class=grid>
          <div class=card>
            <h3>1) Plan</h3>
            <div class=kv><span class=k>Mode</span><b>{plan.get('mode','—')}</b></div>
            <div class=kv><span class=k>Explore</span>{plan.get('explore_ratio','—')}</div>
            <div class=kv><span class=k>Next Wake</span>{plan.get('next_wakeup_secs','—')}s</div>
            <div class=kv><span class=k>Strategies</span>{', '.join([s.get('policy_id','?') for s in plan.get('strategies', [])]) or '—'}</div>
            {_json_block(plan)}
          </div>

          <div class=card>
            <h3>2) Trade Idea</h3>
            <div class=kv><span class=k>Action</span><b>{trader.get('action','—')}</b></div>
            <div class=kv><span class=k>Qty</span>{trader.get('qty','—')}</div>
            <div class=kv><span class=k>Confidence</span>{trader.get('confidence','—')}</div>
            <div class=kv><span class=k>Why</span>{trader.get('hypothesis','—')}</div>
            {_json_block(trader)}
          </div>

          <div class=card>
            <h3>3) Risk Check</h3>
            <div class=row>{dec_badge}</div>
            <div class=kv><span class=k>Revised Qty</span>{judge.get('revised_qty','—')}</div>
            <div class=kv><span class=k>Violations</span>{', '.join(judge.get('violations',[]) or []) or '—'}</div>
            <div class=kv><span class=k>Notes</span>{judge.get('notes','—')}</div>
            {_json_block(judge)}
          </div>

          <div class=card>
            <h3>4) Execution</h3>
            {''.join(trades_html) if trades_html else '<div class=muted>No trades executed.</div>'}
          </div>

          <div class=card>
            <h3>Portfolio</h3>
            <div class=kv><span class=k>USDT</span>{snapshot.get('balance_usdt','—')}</div>
            <div class=kv><span class=k>BTC</span>{snapshot.get('balance_btc','—')}</div>
            {_json_block(snapshot)}
          </div>
        </div>

        <div class=section><a href="/">← Back to timeline</a></div>
      </div>
    </body></html>
    """
    return HTMLResponse(html)