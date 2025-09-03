# Autonomous Trader Agent — Greenfield Spec (from‑scratch v1.0)

> **Intent:** Build a fully autonomous, research‑first crypto trading agent from scratch using **OpenAI Agents SDK + Responses API**. Minimal guardrails: only a tiny **deposit cap** for real mode; otherwise let the agent plan/act/evaluate/learn on its own. **Do not track token cost** in v1. All model outputs must be **JSON‑only** (no prose), strictly validated via JSON Schemas.

---

## 0) Principles

* **Autonomy first:** The agent decides **when** to wake, **what** to try (explore vs exploit), **whether** to trade, and **how** to revise itself via experiments.
* **Tools over prompts:** Market data, execution, ledger, and memory are **tools**; models never hallucinate side‑effects.
* **Ultra‑terse I/O:** Models output **JSON only** per schema. No filler words. No explanations.
* **Safety by bankroll:** Real‑mode hard cap in USDT; otherwise no extra guardrails in v1.
* **Deterministic compute path:** Decimal for all money/qty; idempotency; SQLite WAL for audit.

---

## 1) Tech Stack & Versions

* Python 3.11+
* OpenAI Python SDK ≥ 1.40 (Responses API + Agents SDK)
* CCXT ≥ 4.4 (REST only)
* FastAPI (optional, read‑only HTTP later)
* SQLite (WAL), `pydantic` for settings, `decimal` for math

> Single process, single worker. No external schedulers.

---

## 2) Repository Layout

```
/app
  /agents
    planner.py      # Planner Agent (produces Plan)
    trader.py       # Trader Agent (produces Action Proposal)
    judge.py        # Judge Agent (produces Verdict)
  /tools
    market.py       # get_ohlcv(); REST via CCXT
    strategy.py     # compute_indicators(); tiny RSI/MA features
    trade.py        # place_market_order(); cancel_all(); Decimal + idempotency
    ledger.py       # log_decision(); log_trade(); snapshot_portfolio()
    memory.py       # write_experiment(); read_posteriors(); store plan/results
  /core
    orchestrator.py # runs: plan → propose → judge → (execute) → log → sleep
    config.py       # Pydantic Settings + env validation
    db.py           # SQLite init (WAL) + migrations + DAL helpers
    util.py         # Decimal helpers; idempotency; time utils
  /schemas
    planner.py      # Plan JSON Schema
    trader.py       # Proposal JSON Schema
    judge.py        # Verdict JSON Schema
  main.py           # entrypoint: boot, reconcile, start loop
```

---

## 3) Environment & Settings

**.env (example)**

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL_PLANNER=gpt-5-mini
OPENAI_MODEL_TRADER=gpt-5
OPENAI_MODEL_JUDGE=gpt-5-mini
SYMBOL=BTC/USDT
TIMEFRAME=5m
OHLCV_LIMIT=100
DEPOSIT_CAP_USDT=5
MODE=testnet            # testnet | real
DB_PATH=/data/agent.db
LOG_LEVEL=INFO
```

**Pydantic Settings skeleton**

```python
# /core/config.py
from pydantic import BaseSettings, Field
class Settings(BaseSettings):
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    model_planner: str = Field("gpt-5-mini", env="OPENAI_MODEL_PLANNER")
    model_trader: str = Field("gpt-5", env="OPENAI_MODEL_TRADER")
    model_judge: str = Field("gpt-5-mini", env="OPENAI_MODEL_JUDGE")
    symbol: str = Field("BTC/USDT", env="SYMBOL")
    timeframe: str = Field("5m", env="TIMEFRAME")
    ohlcv_limit: int = Field(100, env="OHLCV_LIMIT")
    deposit_cap_usdt: float = Field(5.0, env="DEPOSIT_CAP_USDT")
    mode: str = Field("testnet", env="MODE")
    db_path: str = Field("/data/agent.db", env="DB_PATH")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    class Config:
        env_file = ".env"
```

---

## 4) Database Schema (SQLite, WAL)

```sql
PRAGMA journal_mode=WAL;

-- 4.1 decisions: one per agent output (planner/trader/judge)
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  agent TEXT CHECK(agent IN ('PLANNER','TRADER','JUDGE')) NOT NULL,
  trace_id TEXT,
  payload_json TEXT NOT NULL,
  plan_id INTEGER,
  proposal_id INTEGER
);

-- 4.2 trades: one row per executed order
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT CHECK(side IN ('BUY','SELL')) NOT NULL,
  qty TEXT NOT NULL,       -- Decimal(str)
  price TEXT NOT NULL,     -- Decimal(str)
  fee TEXT,                -- Decimal(str)
  order_id TEXT,
  idempotency_key TEXT UNIQUE,
  proposal_id INTEGER,
  status TEXT DEFAULT 'FILLED'
);

-- 4.3 portfolio snapshots
CREATE TABLE IF NOT EXISTS portfolio (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  balance_usdt TEXT NOT NULL,
  balance_btc TEXT NOT NULL,
  unrealized_pnl_usdt TEXT NOT NULL,
  realized_pnl_usdt TEXT NOT NULL
);

-- 4.4 memory: research logs & posterior params
CREATE TABLE IF NOT EXISTS memory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL
);
```

---

## 5) Schemas (JSON Only)

**Absolute rule:** All model outputs must be valid JSON conforming to these.

### 5.1 Plan (Planner → Orchestrator)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["mode","explore_ratio","next_wakeup_secs","strategies"],
  "properties": {
    "mode": {"enum": ["OBSERVE","TRADE"]},
    "explore_ratio": {"type": "number", "minimum": 0, "maximum": 1},
    "next_wakeup_secs": {"type": "integer", "minimum": 30, "maximum": 3600},
    "strategies": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["policy_id","params"],
        "properties": {
          "policy_id": {"type": "string"},
          "params": {"type": "object"}
        },
        "additionalProperties": false
      },
      "minItems": 1, "maxItems": 3
    }
  },
  "additionalProperties": false
}
```

### 5.2 Proposal (Trader → Judge)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["action","qty","policy_id","hypothesis","confidence"],
  "properties": {
    "action": {"enum": ["BUY","SELL","HOLD"]},
    "qty": {"type": "string", "pattern": "^\\d+(\\.\\d+)?$"},
    "policy_id": {"type": "string"},
    "hypothesis": {"type": "string", "maxLength": 120},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
  },
  "additionalProperties": false
}
```

### 5.3 Verdict (Judge → Orchestrator)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["decision"],
  "properties": {
    "decision": {"enum": ["APPROVE","REVISE","REJECT"]},
    "revised_qty": {"type": "string", "pattern": "^\\d+(\\.\\d+)?$"},
    "violations": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    "notes": {"type": "string", "maxLength": 120}
  },
  "additionalProperties": false
}
```

---

## 6) Agent Prompts (System)

**Common prelude (all agents):**

* Output **JSON only**. No prose. Conform to the provided schema exactly.
* If unclear, choose the safest minimal behavior (OBSERVE, HOLD, or extend sleep).

**Planner**

* Goal: maximize long‑term equity with tiny experiments.
* Inputs: last memory/posteriors, simple regime features (vol/trend), recent outcomes.
* Output: a Plan with `mode`, `explore_ratio`, `strategies`, and `next_wakeup_secs`.

**Trader**

* Goal: produce a compact action proposal under the current Plan.
* Must call tools to get OHLCV and compute indicators.
* Prefer HOLD when edge is weak. Use tiny quantities in real mode.

**Judge**

* Enforce only two constraints: **deposit cap** (real mode) and **exchange precision/minNotional**.
* Approve if both satisfied; otherwise REVISE qty or REJECT.

---

## 7) Tools (Interfaces & Notes)

```python
# /tools/market.py
from typing import Dict, List

def get_ohlcv(symbol: str, timeframe: str, limit: int) -> Dict[str, List[List[float]]]:
    """Return {"ohlcv": [[ts,o,h,l,c,v], ...]} via CCXT REST; fallback to mock if needed."""

# /tools/strategy.py
from typing import Dict

def compute_indicators(ohlcv: Dict) -> Dict:
    """Compute RSI(14), MA(20), volume_avg. Handle NaN/Inf, clip RSI to [0,100]."""

# /tools/trade.py
from decimal import Decimal

def place_market_order(side: str, qty: str, idem_key: str) -> Dict:
    """Quantize to step; enforce minNotional; return {order_id, price, fee} as strings."""

def cancel_all() -> Dict: ...

# /tools/ledger.py

def log_decision(agent: str, payload_json: str, trace_id: str, plan_id=None, proposal_id=None) -> int: ...

def log_trade(side: str, qty: str, price: str, fee: str, idem_key: str, proposal_id: int) -> int: ...

def snapshot_portfolio(mark_price: str) -> None: ...

# /tools/memory.py

def write_experiment(key: str, value_json: str) -> None: ...

def read_posteriors() -> Dict: ...
```

Implementation notes:

* Use `Decimal` for price/qty/fee; store as strings.
* Load CCXT markets once; cache step/precision/minNotional.
* Idempotency key: sha256 of `minute_bucket|symbol|side|qty|price_bucket`.
* In `MODE=real`, hard‑cap notional exposure by `DEPOSIT_CAP_USDT`.

---

## 8) Agents SDK Wiring (Skeleton)

```python
# /agents/trader.py
from openai import OpenAI
client = OpenAI()

TRADER_SCHEMA = {...}  # from /schemas/trader.py

def propose(plan: dict, indicators: dict) -> dict:
    prompt = {
        "role": "user",
        "content": {
          "type": "text",
          "text": f"Plan={plan}; Indicators={indicators}. Output JSON only."
        }
    }
    r = client.responses.create(
        model=settings.model_trader,
        input=[{"role":"system","content":"Output JSON only per schema."}, prompt],
        response_format={"type":"json_schema","json_schema": TRADER_SCHEMA},
        temperature=0.5,
        max_output_tokens=120,
    )
    return r.output[0].content[0].text  # parse to dict in code
```

> Repeat similarly for Planner (Plan schema) and Judge (Verdict schema). Tools are invoked from Python (pre/post steps); keep agents **stateless** beyond inputs provided each cycle.

---

## 9) Orchestrator Loop (Core)

```python
# /core/orchestrator.py
import time, uuid
from core.config import Settings
from tools import market, strategy, trade, ledger, memory
from agents import planner, trader, judge

settings = Settings()

def run_forever():
    while True:
        trace = str(uuid.uuid4())
        # 1) Plan
        plan = planner.plan(memory.read_posteriors())
        plan_id = ledger.log_decision('PLANNER', json.dumps(plan), trace)

        # 2) Propose
        ohlcv = market.get_ohlcv(settings.symbol, settings.timeframe, settings.ohlcv_limit)
        ind = strategy.compute_indicators(ohlcv)
        prop = trader.propose(plan, ind)
        proposal_id = ledger.log_decision('TRADER', json.dumps(prop), trace, plan_id=plan_id)

        # 3) Judge
        verdict = judge.review(prop)
        ledger.log_decision('JUDGE', json.dumps(verdict), trace, proposal_id=proposal_id)

        # 4) Act
        if verdict["decision"] in ("APPROVE", "REVISE"):
            final_qty = verdict.get("revised_qty", prop.get("qty"))
            idem = make_idem(trace, settings.symbol, prop["action"], final_qty, price_bucket(...))
            ord = trade.place_market_order(prop["action"], final_qty, idem)
            ledger.log_trade(prop["action"], ord["filled_qty"], ord["price"], ord.get("fee","0"), idem, proposal_id)
            ledger.snapshot_portfolio(ord["price"])  # mark-to-market
            memory.write_experiment(prop["policy_id"], json.dumps({"result":"executed"}))

        # 5) Sleep per plan
        time.sleep(plan["next_wakeup_secs"])
```

---

## 10) main.py

```python
from core.orchestrator import run_forever
if __name__ == "__main__":
    run_forever()
```

---

## 11) Bring‑Up Checklist

* `pip install -U openai ccxt pydantic` (+ others as needed)
* Create `.env`; run `python main.py` in `MODE=testnet`.
* Verify:

  * decisions table accumulating PLANNER/TRADER/JUDGE rows
  * at least 10 executed trades on testnet
  * Planner varies `next_wakeup_secs` over time
  * All model outputs are valid JSON (no prose)

---

## 12) Acceptance Criteria (V1)

* Agent runs autonomously for ≥ 24h on testnet without crash.
* Produces continuous decisions; executes ≥ 10 trades with unique idempotency.
* No model output contains extra text; all conform to schemas.
* Memory table contains at least one experiment record.
* Real mode enforces deposit cap on notional (hard stop inside trade tool).

---

## 13) Out‑of‑Scope (V1)

* Token usage metering/budgeting
* Personality/UX layer
* WebSockets, multiple symbols, advanced risk
* External competitions/leaderboards integration (plan later)

---

## 14) Next (V1.1 → V2)

* Add exploration engine (e.g., Thompson Sampling over strategy families)
* Add weekly evaluator/report agent
* Optional read‑only HTTP for logs/portfolio
* Switch to micro‑real with sub‑account + deposit cap

```
```
