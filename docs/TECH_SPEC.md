# Technical Specification
# Autonomous Trader Agent

## 1. Technology Stack

**Core Platform**:
- **Python**: 3.11+ (required for latest OpenAI SDK features)
- **OpenAI Python SDK**: ≥ 1.50 (GPT-5-mini support with structured outputs)
- **CCXT**: ≥ 4.4 (REST only, no WebSockets)
- **SQLite**: WAL mode for concurrent access
- **FastAPI**: Modern web dashboard with real-time updates
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

## 5. Context Engineering & GPT-5-Mini Integration

### 5.1 GPT-5-Mini Enhanced Reasoning Framework

**GPT-5-Mini Capabilities & Implementation**:
- **Enhanced reasoning**: 400k context window for deep market analysis
- **Native structured outputs**: Perfect JSON compliance without post-processing  
- **Cost optimization**: 90% cheaper than GPT-4o while maintaining quality
- **Speed optimization**: 3-4 second response times vs 30+ seconds previously
- **Reasoning effort control**: Adjustable depth based on agent complexity

**Model Assignment Strategy**:
```python
# Optimized model mapping for capability vs cost efficiency
OPENAI_MODEL_PLANNER = "gpt-5-mini"  # Strategic reasoning, cost-optimized
OPENAI_MODEL_TRADER = "gpt-5-mini"   # Market analysis, enhanced reasoning 
OPENAI_MODEL_JUDGE = "gpt-5-mini"    # Risk validation, fast decisions
```

### 5.2 Context Engineering Architecture

**Context Construction Pipeline**:
Each agent receives precisely engineered context optimized for its decision domain:

1. **Memory Context Aggregation** → Planner receives historical performance data
2. **Market Context Synthesis** → Trader receives real-time market indicators  
3. **Risk Context Validation** → Judge receives proposal + constraint parameters
4. **Decision Context Logging** → All contexts preserved with full audit trail

**JSON Data Flow Architecture**:
```
[Memory Store] ──→ [Planner Context] ──→ Plan JSON
      ↓
[Market Data] ──→ [Trader Context] ──→ Proposal JSON
      ↓  
[Constraints] ──→ [Judge Context] ──→ Verdict JSON
      ↓
[Trade Execution] ──→ [Audit Trail] ──→ [Updated Memory]
```

### 5.3 Planner Agent Context Engineering

**Strategic Reasoning System Prompt**:
```python
PLANNER_SYSTEM_PROMPT = """You are an advanced strategic trading planner with sophisticated reasoning capabilities. Your mission is to maximize long-term portfolio growth through intelligent strategy selection and risk management.

STRATEGIC REASONING FRAMEWORK:
1. ASSESS: Evaluate current market regime, volatility, and trend conditions
2. ANALYZE: Review recent performance data and strategy effectiveness  
3. ADAPT: Adjust strategy selection based on changing market dynamics
4. OPTIMIZE: Balance exploration of new approaches vs exploitation of proven strategies

DECISION MATRIX:
- OBSERVE Mode: Use during high uncertainty, major news events, or after significant losses
- TRADE Mode: Use during stable conditions with clear market signals and proven strategies

EXPLORATION STRATEGY:
- Low (0.0-0.3): Exploit proven strategies in stable, profitable conditions
- Medium (0.3-0.7): Balanced approach during normal market conditions  
- High (0.7-1.0): Explore new strategies during poor performance or changing regimes

OUTPUT JSON ONLY. Think strategically about market dynamics and performance optimization."""
```

**Memory Context Construction**:
```python
def create_planner_context(memory_posteriors: Dict[str, Any]) -> str:
    """Constructs rich context for strategic planning decisions"""
    
    # Aggregate memory insights
    experiment_count = len(memory_posteriors)
    recent_strategies = list(memory_posteriors.keys())[:3]
    executed_trades = sum(1 for exp in memory_posteriors.values() 
                         if exp.get("result") == "executed")
    
    # Performance summary for strategic assessment
    context_summary = f"""Recent experiments: {experiment_count}
Recent strategies: {', '.join(recent_strategies)}  
Executed trades: {executed_trades}"""
    
    # Complete context assembly
    return f"""Current Context:
{context_summary}

Symbol: {settings.symbol}
Mode: {settings.mode}
Deposit Cap: {settings.deposit_cap_usdt} USDT

Generate a strategic plan considering:
- Recent strategy performance from memory
- Current market regime and volatility
- Risk management and position sizing  
- Exploration vs exploitation balance

Output valid Plan JSON only."""
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

### 5.4 Trader Agent Context Engineering

**Market Analysis System Prompt**:
```python
TRADER_SYSTEM_PROMPT = """You are an advanced AI trading agent with deep reasoning capabilities. Your goal is to generate optimal trade proposals through comprehensive market analysis.

REASONING APPROACH:
1. ANALYZE: Thoroughly examine all market indicators, price patterns, and technical signals
2. SYNTHESIZE: Connect patterns across different timeframes and indicators  
3. EVALUATE: Assess risk-reward ratios and probability of success
4. DECIDE: Make data-driven trading decisions with clear rationale

MARKET ANALYSIS FRAMEWORK:
- Technical Indicators: RSI levels, moving average relationships, volume patterns
- Price Action: Support/resistance, trend strength, momentum shifts  
- Market Context: Volatility regime, correlation patterns, sentiment indicators
- Risk Assessment: Position sizing, stop-loss levels, maximum drawdown scenarios

DECISION CRITERIA:
- BUY: Strong bullish signals, favorable risk/reward (>2:1), high confidence (>0.7)
- SELL: Strong bearish signals, favorable risk/reward (>2:1), high confidence (>0.7)  
- HOLD: Mixed signals, unfavorable risk/reward, uncertainty, or risk management

Think deeply about market dynamics before making decisions."""
```

**Market Context Construction**:
```python
def create_trader_context(plan: Dict[str, Any], indicators: Dict[str, Any]) -> str:
    """Constructs comprehensive market context for trading decisions"""
    
    # Strategic plan summary
    mode = plan.get("mode", "UNKNOWN")
    strategies = plan.get("strategies", [])
    explore_ratio = plan.get("explore_ratio", 0.0)
    strategy_names = [s.get("policy_id", "unknown") for s in strategies]
    plan_summary = f"Mode: {mode} | Strategies: {', '.join(strategy_names)} | Exploration: {explore_ratio:.2f}"
    
    # Market indicators synthesis
    indicators_parts = []
    if "rsi" in indicators:
        rsi_level = "Oversold" if indicators["rsi"] < 30 else "Overbought" if indicators["rsi"] > 70 else "Neutral"
        indicators_parts.append(f"RSI: {indicators['rsi']:.1f} ({rsi_level})")
    if "ma20" in indicators:
        indicators_parts.append(f"MA20: ${indicators['ma20']:,.2f}")
    if "price" in indicators:
        indicators_parts.append(f"Price: ${indicators['price']:,.2f}")
    if "volume_avg" in indicators:
        indicators_parts.append(f"Volume: {indicators['volume_avg']:,.0f}")
    
    indicators_summary = " | ".join(indicators_parts) if indicators_parts else "Limited market data"
    
    # Complete context assembly  
    return f"""Strategic Plan:
{plan_summary}

Market Indicators:
{indicators_summary}

Trading Parameters:
Symbol: {settings.symbol}
Mode: {settings.mode}
Deposit Cap: ${settings.deposit_cap_usdt}

Generate a trade proposal by analyzing:
- Technical indicators and market signals
- Strategic plan guidance and exploration requirements
- Appropriate position sizing for current mode
- Risk-reward assessment with clear hypothesis
- Confidence level based on signal strength

Output valid Proposal JSON only."""
```

### 5.5 Judge Agent Context Engineering

**Risk Validation System Prompt**:
```python
JUDGE_SYSTEM_PROMPT = """You are a risk management judge responsible for validating trade proposals against safety constraints.

RISK VALIDATION FRAMEWORK:
1. ASSESS: Evaluate proposed trade against deposit caps and precision limits
2. CALCULATE: Determine if trade size exceeds safety parameters
3. REVISE: Adjust quantities while preserving trade intent if possible
4. DECIDE: APPROVE safe trades, REVISE oversized trades, REJECT violations

CONSTRAINT PRIORITIES:
1. Deposit Cap: Hard limit on notional exposure in real mode
2. Exchange Precision: Quantity must conform to step size requirements
3. Minimum Notional: Trade size must meet exchange minimums
4. Risk Management: Conservative approach when uncertain

DECISION LOGIC:
- APPROVE: All constraints satisfied, trade can execute as proposed
- REVISE: Trade viable but requires quantity adjustment for safety
- REJECT: Fundamental constraint violations that cannot be resolved"""
```

**Constraint-Based Context (Rule-Based, Not AI)**:
```python
def validate_trade_constraints(proposal: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    """Judge uses deterministic rule-based validation rather than AI context"""
    
    violations = []
    revised_qty = None
    
    if proposal["action"] != "HOLD":
        qty = Decimal(proposal["qty"])
        price = Decimal(str(current_price))
        notional = qty * price
        
        # Deposit cap validation (real mode only)
        if settings.mode == "real":
            deposit_cap = Decimal(str(settings.deposit_cap_usdt))
            if notional > deposit_cap:
                violations.append(f"Notional ${notional} exceeds cap ${deposit_cap}")
                # Calculate revised quantity
                safe_qty = (deposit_cap * Decimal("0.9")) / price  # 90% of max for safety
                revised_qty = str(safe_qty.quantize(Decimal("0.00001")))
        
        # Minimum quantity validation
        min_qty = Decimal("0.00001")
        if qty < min_qty:
            violations.append(f"Quantity {qty} below minimum {min_qty}")
        
        # Precision validation
        if qty.as_tuple().exponent < -8:
            violations.append("Quantity precision exceeds 8 decimal places")
    
    # Decision logic
    if not violations:
        return {"decision": "APPROVE", "notes": "All constraints satisfied"}
    elif revised_qty and float(revised_qty) > 0:
        return {"decision": "REVISE", "revised_qty": revised_qty, 
                "violations": violations, "notes": "Quantity adjusted for safety"}
    else:
        return {"decision": "REJECT", "violations": violations, 
                "notes": "Constraints cannot be satisfied"}
```

### 5.6 Trigger Mechanisms & Event System

**Cycle Trigger Logic**:
```python
class TradingCycleTriggers:
    
    def determine_next_wakeup(self, plan: Dict[str, Any]) -> int:
        """Dynamic sleep intervals based on plan output and market conditions"""
        base_wakeup = plan.get("next_wakeup_secs", 300)
        mode = plan.get("mode", "OBSERVE")
        
        # Mode-based timing adjustments
        if mode == "OBSERVE":
            return base_wakeup  # Use planner's recommendation
        elif mode == "TRADE":
            return max(30, base_wakeup // 2)  # More frequent in active trading
        
        return 300  # Default 5-minute fallback
    
    def check_emergency_triggers(self, portfolio_data: Dict[str, Any]) -> bool:
        """Emergency stop conditions that override normal cycle timing"""
        
        # Maximum drawdown trigger
        realized_pnl = float(portfolio_data.get("realized_pnl_usdt", 0))
        unrealized_pnl = float(portfolio_data.get("unrealized_pnl_usdt", 0))
        total_pnl = realized_pnl + unrealized_pnl
        
        max_loss_threshold = -0.20 * settings.deposit_cap_usdt  # 20% max loss
        if total_pnl < max_loss_threshold:
            return True
        
        return False
    
    def should_force_immediate_cycle(self, market_conditions: Dict[str, Any]) -> bool:
        """Conditions that trigger immediate trading cycle"""
        
        # High volatility trigger
        if "volatility" in market_conditions:
            if market_conditions["volatility"] > 0.05:  # 5% volatility spike
                return True
        
        # Major price movement trigger  
        if "price_change_1h" in market_conditions:
            if abs(market_conditions["price_change_1h"]) > 0.03:  # 3% hourly move
                return True
        
        return False
```

### 5.2 Agent Prompting Strategy

**Context Engineering Principles**:
- Each agent receives precisely crafted context optimized for its decision domain
- System prompts establish clear reasoning frameworks and decision criteria
- User prompts provide current state and specific parameters for decision making
- All outputs conform to strict JSON schemas with no prose or explanations

**Error Recovery & Context Preservation**:
```python
class ContextRecoveryManager:
    
    def preserve_context_on_failure(self, agent_type: str, context_data: Dict[str, Any], error: Exception):
        """Save context state for analysis and recovery"""
        recovery_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent_type": agent_type,
            "trace_id": context_data.get("trace_id"),
            "error_type": type(error).__name__,
            "error_message": str(error)[:500],  # Truncate long errors
            "context_snapshot": context_data
        }
        
        # Store for debugging and recovery
        self.ledger.log_recovery_event(recovery_record)
    
    def generate_fallback_context(self, agent_type: str) -> Dict[str, Any]:
        """Generate minimal safe context when normal context construction fails"""
        
        if agent_type == "planner":
            return create_observe_plan(600)  # Conservative 10-minute observation
        elif agent_type == "trader":
            return create_hold_proposal("fallback", "System recovery mode", 0.1)
        elif agent_type == "judge":
            return {"decision": "REJECT", "notes": "Recovery mode - safety first"}
        
        return {}
```

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

## 12. Dashboard & Web Interface

### 12.1 Ultra-Minimal Dashboard Design

**Design Philosophy**:
The dashboard follows modern design principles with emphasis on clarity and actionability:
- **Ultra-minimal**: Only session status + decision history (all noise removed)
- **Modern aesthetics**: Glassmorphism, animated gradients, smooth hover effects
- **Auto-refresh**: 15-second intervals for real-time monitoring
- **Mobile-responsive**: Optimized for all screen sizes

**Visual Design Features**:
```css
/* Modern gradient background with smooth animations */
background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
background-size: 400% 400%;
animation: gradientShift 8s ease infinite;

/* Glassmorphism cards with backdrop blur */
background: rgba(255, 255, 255, 0.15);
backdrop-filter: blur(15px);
border: 1px solid rgba(255, 255, 255, 0.2);

/* Smooth hover animations */
transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
transform: translateY(-2px) scale(1.02);
```

### 12.2 Dashboard Implementation Architecture

**FastAPI Web Server Integration**:
```python
# /app/server/web.py - Complete dashboard implementation
class TradingDashboard:
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.app = FastAPI(title="AI Trader Dashboard")
        self.setup_routes()
    
    def setup_routes(self):
        """Configure dashboard routes and auto-refresh"""
        
        @self.app.get("/", response_class=HTMLResponse)
        def dashboard_home():
            """Ultra-minimal dashboard with session status + decision history"""
            
            # Get current system status
            status_data = self._get_system_status()
            decision_history = self._get_decision_history(limit=10)
            
            # Render beautiful minimal dashboard
            return self._render_dashboard(status_data, decision_history)
        
        @self.app.get("/api/status")  
        def api_status():
            """JSON API for dashboard auto-refresh"""
            return {
                "status": self._get_system_status(),
                "decisions": self._get_decision_history(limit=5),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _get_system_status(self) -> Dict[str, Any]:
        """Get current system status for dashboard display"""
        
        with _connect(self.settings.db_path) as conn:
            cur = conn.cursor()
            
            # Latest activity timestamp
            cur.execute("SELECT ts_utc FROM decisions ORDER BY id DESC LIMIT 1")
            latest_row = cur.fetchone()
            last_activity = latest_row["ts_utc"] if latest_row else None
            
            # Calculate system status
            if last_activity:
                time_since = (datetime.utcnow() - datetime.fromisoformat(last_activity.replace('Z', '+00:00'))).total_seconds()
                if time_since < 600:  # 10 minutes
                    status = "🚀 WORKING"
                    status_class = "status-working"
                elif time_since < 3600:  # 1 hour  
                    status = "💤 IDLE"
                    status_class = "status-idle"
                else:
                    status = "⏰ DORMANT"
                    status_class = "status-dormant"
            else:
                status = "🔄 STARTING"
                status_class = "status-starting"
            
            # Portfolio summary
            cur.execute("SELECT * FROM portfolio ORDER BY id DESC LIMIT 1")
            portfolio = cur.fetchone()
            
            if portfolio:
                total_pnl = float(portfolio["realized_pnl_usdt"]) + float(portfolio["unrealized_pnl_usdt"])
                balance_usdt = float(portfolio["balance_usdt"])
                balance_btc = float(portfolio["balance_btc"])
            else:
                total_pnl = 0.0
                balance_usdt = settings.deposit_cap_usdt
                balance_btc = 0.0
            
            return {
                "status": status,
                "status_class": status_class, 
                "last_activity": last_activity,
                "total_pnl": total_pnl,
                "balance_usdt": balance_usdt,
                "balance_btc": balance_btc,
                "symbol": settings.symbol,
                "mode": settings.mode.upper()
            }
    
    def _get_decision_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent decision history for timeline display"""
        
        with _connect(self.settings.db_path) as conn:
            cur = conn.cursor()
            
            # Get recent decisions with context
            cur.execute("""
                SELECT ts_utc, agent, payload_json, trace_id
                FROM decisions 
                ORDER BY id DESC 
                LIMIT ?
            """, (limit,))
            
            decisions = []
            for row in cur.fetchall():
                decision_item = self._format_decision_for_timeline(row)
                if decision_item:
                    decisions.append(decision_item)
            
            return decisions
    
    def _format_decision_for_timeline(self, row) -> Optional[Dict[str, Any]]:
        """Format database row into timeline-friendly format"""
        
        agent = row["agent"]
        ts = row["ts_utc"] 
        time_str = self._format_relative_time(ts)
        
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            return None
        
        if agent == "PLANNER":
            mode = payload.get("mode", "UNKNOWN")
            strategy_count = len(payload.get("strategies", []))
            
            return {
                "time": time_str,
                "agent": "🧠 PLANNER", 
                "action": f"Decided: {mode} mode",
                "details": f"Using {strategy_count} strateg{'ies' if strategy_count != 1 else 'y'} • {'Active trading' if mode == 'TRADE' else 'Market observation'}",
                "status_class": "decision-planner"
            }
            
        elif agent == "TRADER":
            action = payload.get("action", "UNKNOWN")
            qty = payload.get("qty", "0")
            confidence = payload.get("confidence", 0)
            
            if action == "HOLD":
                return {
                    "time": time_str,
                    "agent": "🤖 TRADER",
                    "action": "Decided: HOLD position", 
                    "details": f"Market analysis complete • Confidence: {confidence:.1%}",
                    "status_class": "decision-hold"
                }
            else:
                return {
                    "time": time_str,
                    "agent": "🤖 TRADER",
                    "action": f"Proposed: {action} {qty} BTC",
                    "details": f"Confidence: {confidence:.1%} • Awaiting risk validation",
                    "status_class": f"decision-{action.lower()}"
                }
                
        elif agent == "JUDGE":
            decision = payload.get("decision", "UNKNOWN")
            
            if decision == "APPROVE":
                return {
                    "time": time_str,
                    "agent": "⚖️ JUDGE",
                    "action": "✅ APPROVED trade",
                    "details": "All risk constraints satisfied • Trade executed",
                    "status_class": "decision-approve"
                }
            elif decision == "REVISE": 
                revised_qty = payload.get("revised_qty", "unknown")
                return {
                    "time": time_str,
                    "agent": "⚖️ JUDGE", 
                    "action": f"📝 REVISED to {revised_qty} BTC",
                    "details": "Quantity adjusted for safety • Trade executed",
                    "status_class": "decision-revise"
                }
            elif decision == "REJECT":
                return {
                    "time": time_str,
                    "agent": "⚖️ JUDGE",
                    "action": "❌ REJECTED trade",
                    "details": "Risk constraints violated • Trade cancelled",
                    "status_class": "decision-reject"
                }
        
        return None
    
    def _format_relative_time(self, ts_utc: str) -> str:
        """Convert UTC timestamp to human-friendly relative time"""
        try:
            dt = datetime.fromisoformat(ts_utc.replace('Z', '+00:00'))
            now = datetime.utcnow().replace(tzinfo=timezone.utc)
            diff = (now - dt).total_seconds()
            
            if diff < 60:
                return f"{int(diff)}s ago"
            elif diff < 3600:
                return f"{int(diff//60)}m ago" 
            elif diff < 86400:
                return f"{int(diff//3600)}h ago"
            else:
                return f"{int(diff//86400)}d ago"
        except (ValueError, TypeError):
            return "Unknown"
```

### 12.3 Auto-Refresh & Real-Time Updates

**JavaScript Auto-Refresh Implementation**:
```javascript
// Client-side auto-refresh for real-time dashboard updates
class DashboardUpdater {
    constructor() {
        this.refreshInterval = 15000; // 15 seconds
        this.isActive = true;
        this.startAutoRefresh();
    }
    
    async startAutoRefresh() {
        while (this.isActive) {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                this.updateDashboard(data);
            } catch (error) {
                console.log('Refresh failed:', error);
            }
            
            await this.sleep(this.refreshInterval);
        }
    }
    
    updateDashboard(data) {
        // Update status display
        const statusElement = document.querySelector('.system-status');
        if (statusElement) {
            statusElement.textContent = data.status.status;
            statusElement.className = `system-status ${data.status.status_class}`;
        }
        
        // Update decision timeline
        this.updateDecisionTimeline(data.decisions);
        
        // Update last refresh timestamp
        document.querySelector('.last-updated').textContent = 
            `Updated: ${new Date().toLocaleTimeString()}`;
    }
    
    updateDecisionTimeline(decisions) {
        const timeline = document.querySelector('.decision-timeline');
        if (!timeline) return;
        
        // Clear existing timeline
        timeline.innerHTML = '';
        
        // Add new decisions with smooth animations
        decisions.forEach((decision, index) => {
            const item = document.createElement('div');
            item.className = `timeline-item ${decision.status_class}`;
            item.innerHTML = `
                <div class="timeline-time">${decision.time}</div>
                <div class="timeline-agent">${decision.agent}</div>
                <div class="timeline-action">${decision.action}</div>
                <div class="timeline-details">${decision.details}</div>
            `;
            
            // Animate item entrance
            item.style.opacity = '0';
            item.style.transform = 'translateY(20px)';
            timeline.appendChild(item);
            
            setTimeout(() => {
                item.style.transition = 'all 0.3s ease';
                item.style.opacity = '1';
                item.style.transform = 'translateY(0)';
            }, index * 100); // Stagger animations
        });
    }
    
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', () => {
    new DashboardUpdater();
});
```

### 12.4 Database Connection Optimization

**Concurrent Access & Performance**:
```python
def _connect(db_path: str) -> sqlite3.Connection:
    """Optimized database connection for dashboard concurrent access"""
    
    conn = sqlite3.Connection(
        db_path,
        timeout=5.0,  # 5 second timeout prevents hanging
        check_same_thread=False  # Allow FastAPI thread sharing
    )
    conn.row_factory = sqlite3.Row  # Dict-like row access
    
    # WAL mode for concurrent reads during trading cycles
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")  # 5 second busy timeout
    conn.execute("PRAGMA cache_size=-20000")  # 20MB cache for performance
    
    return conn

def _bulk_fetch_decisions(limit: int = 20) -> List[Dict[str, Any]]:
    """Optimized bulk query to eliminate race conditions"""
    
    with _connect(settings.db_path) as conn:
        cur = conn.cursor()
        
        # Single bulk query prevents inconsistent data 
        cur.execute("""
            SELECT 
                d.ts_utc,
                d.agent, 
                d.payload_json,
                d.trace_id,
                t.side,
                t.qty as trade_qty,
                t.price as trade_price
            FROM decisions d
            LEFT JOIN trades t ON d.id = t.proposal_id
            ORDER BY d.id DESC
            LIMIT ?
        """, (limit,))
        
        return [dict(row) for row in cur.fetchall()]
```

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
