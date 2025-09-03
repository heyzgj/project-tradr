# Technical Specification
# Autonomous Trader Agent

## 1. Technology Stack

**Core Platform**:
- **Python**: 3.11+ (required for latest OpenAI SDK features)
- **OpenAI Python SDK**: ≥ 1.40 (Responses API + Agents SDK)
- **CCXT**: ≥ 4.4 (REST only, no WebSockets)
- **SQLite**: WAL mode for concurrent access
- **FastAPI**: Optional read-only HTTP endpoints
- **Pydantic**: Settings validation and data modeling

**Key Libraries**:
- `decimal`: Precise financial calculations
- `uuid`: Trace ID generation for request tracking  
- `json`: Schema validation and serialization
- `time`: Sleep intervals and timestamps
- `logging`: Structured application logging

**Architecture Principles**:
- Single process, single worker design
- Tools over prompts (no hallucinated side-effects)
- JSON-only model outputs with strict schema validation
- Decimal precision for all monetary calculations
- Idempotency for trade execution safety

## 2. System Architecture

### 2.1 Repository Structure

```
/app
  /agents
    planner.py      # Planner Agent (Plan schema output)
    trader.py       # Trader Agent (Proposal schema output)  
    judge.py        # Judge Agent (Verdict schema output)
  /tools
    market.py       # get_ohlcv() via CCXT REST
    strategy.py     # compute_indicators() RSI/MA
    trade.py        # place_market_order() with Decimal precision
    ledger.py       # log_decision(), log_trade(), snapshot_portfolio()
    memory.py       # write_experiment(), read_posteriors()
  /core
    orchestrator.py # Main run_forever() loop
    config.py       # Pydantic Settings + env validation  
    db.py          # SQLite WAL init + migrations
    util.py        # Decimal helpers, idempotency, time utils
  /schemas
    planner.py     # Plan JSON Schema definition
    trader.py      # Proposal JSON Schema definition
    judge.py       # Verdict JSON Schema definition
  main.py          # Application entrypoint
```

### 2.2 Agent Architecture

**Three-Agent Design Pattern**:

1. **Planner Agent**
   - **Input**: Memory posteriors, market regime features
   - **Output**: Plan JSON (mode, explore_ratio, strategies, wakeup timing)
   - **Model**: gpt-5-mini (cost optimization for planning)
   - **Goal**: Maximize long-term equity through adaptive strategy selection

2. **Trader Agent**  
   - **Input**: Current Plan, market indicators from tools
   - **Output**: Proposal JSON (action, qty, policy_id, hypothesis, confidence)
   - **Model**: gpt-5 (full capability for decision making)
   - **Goal**: Generate optimal trade proposals under current Plan constraints

3. **Judge Agent**
   - **Input**: Trade Proposal from Trader
   - **Output**: Verdict JSON (decision, revised_qty, violations, notes)
   - **Model**: gpt-5-mini (simple validation logic)
   - **Goal**: Enforce deposit cap and exchange precision limits

### 2.3 Data Flow

```
Memory/History → Planner → Plan
     ↓
Market Data → Trader → Proposal  
     ↓
Exchange Limits → Judge → Verdict
     ↓
Trade Execution → Ledger → Portfolio Snapshot
```

## 3. Database Design

### 3.1 SQLite Configuration

```sql
PRAGMA journal_mode=WAL;  -- Concurrent read/write access
PRAGMA synchronous=NORMAL;  -- Balance safety/performance
PRAGMA cache_size=10000;    -- 10MB cache for performance
PRAGMA temp_store=memory;   -- In-memory temporary tables
```

### 3.2 Schema Design

**decisions table**: All agent outputs with full audit trail
```sql
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,                    -- ISO timestamp
  agent TEXT CHECK(agent IN ('PLANNER','TRADER','JUDGE')) NOT NULL,
  trace_id TEXT,                           -- Links related decisions
  payload_json TEXT NOT NULL,              -- Full agent output
  plan_id INTEGER,                         -- FK to plan decision
  proposal_id INTEGER                      -- FK to proposal decision
);
```

**trades table**: Executed orders with idempotency
```sql
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT CHECK(side IN ('BUY','SELL')) NOT NULL,
  qty TEXT NOT NULL,                       -- Decimal as string
  price TEXT NOT NULL,                     -- Decimal as string  
  fee TEXT,                               -- Decimal as string
  order_id TEXT,                          -- Exchange order ID
  idempotency_key TEXT UNIQUE,            -- Prevents duplicates
  proposal_id INTEGER,                    -- Links to proposal
  status TEXT DEFAULT 'FILLED'
);
```

**portfolio table**: Mark-to-market snapshots
```sql
CREATE TABLE IF NOT EXISTS portfolio (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  balance_usdt TEXT NOT NULL,             -- Decimal as string
  balance_btc TEXT NOT NULL,              -- Decimal as string
  unrealized_pnl_usdt TEXT NOT NULL,      -- Decimal as string
  realized_pnl_usdt TEXT NOT NULL         -- Decimal as string
);
```

**memory table**: Experiment tracking and learning
```sql
CREATE TABLE IF NOT EXISTS memory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  key TEXT NOT NULL,                      -- Experiment identifier
  value_json TEXT NOT NULL                -- Results and parameters
);
```

## 4. JSON Schema Definitions

### 4.1 Plan Schema (Planner Output)

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

### 4.2 Proposal Schema (Trader Output)

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

### 4.3 Verdict Schema (Judge Output)

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

## 5. OpenAI Integration

### 5.1 Responses API Configuration

**Key Requirements**:
- Use `response_format={"type":"json_schema","json_schema": SCHEMA}`
- Set `max_output_tokens` appropriately for each agent (120-200)
- Configure `temperature=0.5` for balanced determinism/creativity
- No streaming; single response per call

**Implementation Pattern**:
```python
def call_agent(prompt: dict, schema: dict, model: str) -> dict:
    r = client.responses.create(
        model=model,
        input=[
            {"role":"system","content":"Output JSON only per schema."},
            prompt
        ],
        response_format={"type":"json_schema","json_schema": schema},
        temperature=0.5,
        max_output_tokens=200
    )
    return json.loads(r.output[0].content[0].text)
```

### 5.2 Agent Prompting Strategy

**Common Prelude** (all agents):
- "Output JSON only. No prose. Conform to the provided schema exactly."
- "If unclear, choose the safest minimal behavior."

**Planner System Prompt**:
- Goal: maximize long-term equity with tiny experiments
- Inputs: memory/posteriors, regime features, recent outcomes
- Output: Plan with mode, explore_ratio, strategies, wakeup timing

**Trader System Prompt**: 
- Goal: produce compact action proposal under current Plan
- Must call tools to get OHLCV and compute indicators
- Prefer HOLD when edge is weak; use tiny quantities in real mode

**Judge System Prompt**:
- Enforce only: deposit cap (real mode) and exchange precision/minNotional
- Approve if constraints satisfied; REVISE qty or REJECT otherwise

## 6. Tool Implementation

### 6.1 Market Data Tools

```python
# /tools/market.py
def get_ohlcv(symbol: str, timeframe: str, limit: int) -> Dict[str, List[List[float]]]:
    """
    Return OHLCV data via CCXT REST API
    Format: {"ohlcv": [[timestamp,open,high,low,close,volume], ...]}
    Fallback to mock data if exchange unavailable
    """
```

### 6.2 Technical Analysis Tools

```python
# /tools/strategy.py  
def compute_indicators(ohlcv: Dict) -> Dict:
    """
    Compute RSI(14), MA(20), volume_avg
    Handle NaN/Inf gracefully, clip RSI to [0,100]
    Return: {"rsi": float, "ma20": float, "volume_avg": float}
    """
```

### 6.3 Trade Execution Tools

```python
# /tools/trade.py
def place_market_order(side: str, qty: str, idem_key: str) -> Dict:
    """
    Execute market order with Decimal precision
    Quantize to step size, enforce minNotional
    Return: {"order_id": str, "price": str, "fee": str}
    """
```

## 7. Configuration Management

### 7.1 Environment Variables

```bash
# Core OpenAI Settings
OPENAI_API_KEY=sk-...
OPENAI_MODEL_PLANNER=gpt-5-mini
OPENAI_MODEL_TRADER=gpt-5
OPENAI_MODEL_JUDGE=gpt-5-mini

# Trading Configuration  
SYMBOL=BTC/USDT
TIMEFRAME=5m
OHLCV_LIMIT=100

# Safety & Limits
DEPOSIT_CAP_USDT=5.0
MODE=testnet            # testnet | real

# System Configuration
DB_PATH=/data/agent.db
LOG_LEVEL=INFO
```

### 7.2 Pydantic Settings

```python
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    # OpenAI Configuration
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    model_planner: str = Field("gpt-5-mini", env="OPENAI_MODEL_PLANNER")
    model_trader: str = Field("gpt-5", env="OPENAI_MODEL_TRADER")  
    model_judge: str = Field("gpt-5-mini", env="OPENAI_MODEL_JUDGE")
    
    # Trading Parameters
    symbol: str = Field("BTC/USDT", env="SYMBOL")
    timeframe: str = Field("5m", env="TIMEFRAME")
    ohlcv_limit: int = Field(100, env="OHLCV_LIMIT")
    
    # Safety Configuration
    deposit_cap_usdt: float = Field(5.0, env="DEPOSIT_CAP_USDT")
    mode: str = Field("testnet", env="MODE")  # testnet | real
    
    # System Configuration  
    db_path: str = Field("/data/agent.db", env="DB_PATH")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        validate_assignment = True
```

## 8. Orchestrator Logic

### 8.1 Main Execution Loop

```python
def run_forever():
    while True:
        trace = str(uuid.uuid4())
        
        # 1) Plan Phase
        posteriors = memory.read_posteriors()
        plan = planner.plan(posteriors)
        plan_id = ledger.log_decision('PLANNER', json.dumps(plan), trace)
        
        # 2) Analysis Phase  
        ohlcv = market.get_ohlcv(settings.symbol, settings.timeframe, settings.ohlcv_limit)
        indicators = strategy.compute_indicators(ohlcv)
        
        # 3) Proposal Phase
        proposal = trader.propose(plan, indicators)
        proposal_id = ledger.log_decision('TRADER', json.dumps(proposal), trace, plan_id=plan_id)
        
        # 4) Validation Phase
        verdict = judge.review(proposal)  
        ledger.log_decision('JUDGE', json.dumps(verdict), trace, proposal_id=proposal_id)
        
        # 5) Execution Phase
        if verdict["decision"] in ("APPROVE", "REVISE"):
            final_qty = verdict.get("revised_qty", proposal.get("qty"))
            idem_key = make_idempotency_key(trace, settings.symbol, proposal["action"], final_qty)
            
            order = trade.place_market_order(proposal["action"], final_qty, idem_key)
            ledger.log_trade(proposal["action"], order["filled_qty"], order["price"], 
                           order.get("fee","0"), idem_key, proposal_id)
            ledger.snapshot_portfolio(order["price"])
            
            # Store experiment results
            memory.write_experiment(proposal["policy_id"], 
                                  json.dumps({"result": "executed", "qty": final_qty}))
        
        # 6) Sleep Phase
        time.sleep(plan["next_wakeup_secs"])
```

## 9. Error Handling & Recovery

### 9.1 API Failure Scenarios

**OpenAI API Failures**:
- Implement exponential backoff with jitter
- Fallback to default minimal actions (OBSERVE mode, HOLD decisions)
- Log all API errors for debugging

**Exchange API Failures**:
- Graceful degradation to observation mode  
- Retry with exponential backoff for transient failures
- Emergency order cancellation on critical errors

**Database Failures**:
- WAL mode provides resilience to concurrent access
- Automatic retry for lock timeouts
- Backup/restore procedures for data recovery

### 9.2 Data Integrity

**Idempotency Implementation**:
```python
def make_idempotency_key(trace_id: str, symbol: str, side: str, qty: str, price_bucket: str) -> str:
    """Generate SHA256 hash for duplicate prevention"""
    content = f"{get_minute_bucket()}|{symbol}|{side}|{qty}|{price_bucket}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]
```

**Decimal Precision**:
- All monetary values stored as string representation of Decimal
- Quantization to exchange step sizes before order submission
- Validation against minNotional requirements

## 10. Security Considerations

### 10.1 API Key Management

- Environment variable storage only (never hardcoded)
- Runtime validation of API key formats
- Secure handling in logging (redaction of sensitive data)

### 10.2 Financial Safety

- Mandatory deposit cap enforcement in real mode
- Idempotency prevents accidental duplicate orders
- All trade decisions logged with full audit trail
- Emergency stop capability via configuration

### 10.3 System Isolation

- Single-symbol trading reduces attack surface
- No external network dependencies beyond required APIs
- Local SQLite storage minimizes data exposure

## 11. Performance Characteristics

### 11.1 Expected Performance

**Latency Targets**:
- End-to-end decision cycle: < 10 seconds
- Database operations: < 100ms per query
- Memory usage: < 100MB resident
- CPU usage: Minimal between cycles

**Scalability Limits**:
- Single-process design limits to one symbol/timeframe
- SQLite WAL supports concurrent reads during cycles
- Memory usage grows linearly with trade history

### 11.2 Monitoring Metrics

**System Health**:
- Cycle completion rate and timing
- API success/failure rates  
- Database query performance
- Memory and CPU utilization

**Trading Performance**:
- Decision confidence distributions
- Trade execution success rates
- Portfolio value and P&L tracking
- Strategy performance by policy_id

## 12. Deployment Architecture

### 12.1 Environment Setup

**Development Environment**:
- Python 3.11+ virtual environment
- Local SQLite database for testing
- Testnet API credentials for safe testing
- Complete .env configuration template

**Production Environment**:  
- Single-container deployment
- Persistent volume for SQLite database
- Real API credentials with deposit cap protection
- Automated backup and monitoring

### 12.2 Operational Requirements

**Startup Sequence**:
1. Configuration validation and API key testing
2. Database initialization and schema migration
3. Exchange connection testing and market loading
4. Agent model validation and first cycle execution

**Shutdown Sequence**:
1. Graceful cycle completion
2. Emergency order cancellation if needed  
3. Final portfolio snapshot
4. Database connection cleanup

**Health Checks**:
- API connectivity validation
- Database write capability
- Recent decision timestamp verification
- Portfolio balance sanity checks
