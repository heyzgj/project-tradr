# Product Requirements Document (PRD)
# Autonomous Trader Agent

## 1. Executive Summary

The Autonomous Trader Agent is a fully autonomous crypto trading system that leverages OpenAI's latest Agents SDK and Responses API to make intelligent trading decisions. The system operates with minimal human intervention, using a three-agent architecture (Planner, Trader, Judge) to plan, execute, and validate trades in real-time. The agent is designed for maximum autonomy with only essential safety constraints: a deposit cap for real trading and structured JSON-only outputs.

**Key Value Proposition**: Complete trading autonomy with AI-driven decision making, minimal configuration, and built-in safety through structured validation.

## 2. Problem Statement

Current crypto trading bots require extensive manual configuration, lack true intelligence, and often fail due to rigid rule-based systems. Traders need:
- **Autonomous Decision Making**: Systems that can adapt and learn without constant rule updates
- **Minimal Configuration**: Set-and-forget operation with basic safety parameters
- **Transparent AI Logic**: Clear visibility into AI reasoning without hallucinated outputs
- **Real-time Adaptation**: Ability to adjust strategy based on market conditions

**Target Users**: Individual crypto traders who want intelligent automation without the complexity of traditional trading bots.

## 3. Core Features & User Stories

### 3.1 Autonomous Planning System

**What**: AI-powered planning agent that determines trading mode, exploration ratio, and strategy selection
**Why**: Enables adaptive trading behavior based on market conditions and historical performance

**Acceptance Criteria**:
- Planner agent produces valid JSON conforming to Plan schema
- Supports OBSERVE and TRADE modes based on market analysis
- Adjusts explore_ratio (0-1) for strategy experimentation
- Sets dynamic wakeup intervals (30-3600 seconds)

### User Story: Strategy Planning
- **As a**: Autonomous trading system
- **I want to**: Dynamically plan trading strategies based on current market conditions
- **So that**: I can maximize returns while managing risk appropriately

| Given | When | Then |
|-------|------|------|
| Agent has access to historical performance data and market indicators | Planner agent is invoked with memory context | Valid Plan JSON is generated with mode, explore_ratio, next_wakeup_secs, and strategies array |

### 3.2 Intelligent Trade Execution

**What**: AI trader agent that analyzes market data and proposes specific trading actions
**Why**: Provides intelligent trade execution beyond simple rule-based systems

**Acceptance Criteria**:
- Trader agent calls market data tools to get OHLCV data
- Computes technical indicators (RSI, MA) via tools
- Produces structured Proposal JSON with BUY/SELL/HOLD actions
- Includes quantity, confidence level, and hypothesis reasoning

### User Story: Trade Decision Making
- **As a**: Trading agent
- **I want to**: Analyze current market conditions and propose optimal trades
- **So that**: I can capture profit opportunities while avoiding losses

| Given | When | Then |
|-------|------|------|
| Current Plan specifies TRADE mode and market data is available | Trader agent analyzes indicators and market context | Proposal JSON is generated with action, qty, policy_id, hypothesis, and confidence |

### 3.3 Risk Management & Validation

**What**: Judge agent that validates trade proposals against safety constraints
**Why**: Ensures trades comply with deposit caps and exchange limits before execution

**Acceptance Criteria**:
- Judge validates proposals against deposit_cap_usdt in real mode
- Checks exchange precision and minNotional requirements
- Returns APPROVE/REVISE/REJECT decisions with revised quantities
- Logs violation reasons for audit trail

### User Story: Trade Validation
- **As a**: Risk management system
- **I want to**: Validate proposed trades against safety constraints
- **So that**: I prevent losses exceeding configured limits

| Given | When | Then |
|-------|------|------|
| Trader proposes a trade that exceeds deposit cap | Judge agent reviews the proposal | Verdict JSON returned with REVISE decision and corrected qty |

### 3.4 Complete Audit Trail

**What**: Comprehensive logging of all agent decisions and trade executions
**Why**: Provides transparency and enables performance analysis

**Acceptance Criteria**:
- All agent outputs logged to decisions table with timestamps
- Trade executions recorded with idempotency keys
- Portfolio snapshots captured after each trade
- Memory system tracks experiment results and posteriors

### User Story: Decision Transparency
- **As a**: System operator
- **I want to**: Review all AI decisions and trade executions
- **So that**: I can understand system behavior and optimize performance

| Given | When | Then |
|-------|------|------|
| Agent completes a full trading cycle | Decision logging is triggered | decisions table contains PLANNER, TRADER, and JUDGE entries with trace_id linkage |

## 4. Non-Functional Requirements (NFRs)

**Performance**:
- Agent decisions complete within 10 seconds per cycle
- Database operations use WAL mode for concurrent access
- System runs continuously for 24+ hours without crashes

**Security**:
- API keys stored in environment variables only
- All monetary values use Decimal precision for accuracy
- Idempotency keys prevent duplicate trade execution

**Reliability**:
- Graceful error handling for API failures
- System recovery from network interruptions
- Database integrity maintained through SQLite WAL

**Scalability**:
- Single-process, single-worker design for v1
- Configurable sleep intervals for rate limiting
- Memory-efficient operation under 100MB RAM

## 5. Out of Scope (V1)

- **Token usage metering/budgeting**: No cost tracking in initial version
- **Multiple symbol trading**: Single BTC/USDT pair only
- **WebSocket real-time data**: REST API polling sufficient
- **Advanced risk models**: Simple deposit cap constraint only
- **Web UI/dashboard**: Command-line operation only
- **Backtesting framework**: Live trading focused
- **Multiple exchange support**: Binance-only via CCXT

## 6. Dependencies and Risks

**Dependencies**:
- OpenAI API availability and rate limits
- Binance API connectivity and stability  
- CCXT library for exchange integration
- SQLite for local data persistence

**Technical Risks**:
- OpenAI API downtime affecting decision making
- Exchange API failures during order execution
- Network connectivity issues in production
- SQLite database corruption under high load

**Business Risks**:
- Regulatory changes affecting crypto trading
- Exchange policy changes impacting API access
- Model performance degradation over time

**Mitigation Strategies**:
- Graceful API failure handling with fallback behaviors
- Comprehensive error logging for debugging
- Conservative deposit caps in real trading mode
- Thorough testnet validation before real money deployment

## 7. Technical Constraints

**Model Requirements**:
- All AI outputs must be valid JSON conforming to predefined schemas
- No prose or explanation text in model responses
- Structured validation via OpenAI Responses API

**Financial Constraints**:
- Real mode limited by DEPOSIT_CAP_USDT setting
- All monetary calculations use Decimal arithmetic
- Mandatory idempotency for trade execution

**Operational Constraints**:
- Single symbol (BTC/USDT) trading only
- 5-minute minimum cycle intervals
- Testnet validation required before real trading

## 8. Appendix

**Reference Materials**:
- OpenAI Agents SDK documentation
- CCXT library documentation for Binance
- SQLite WAL mode performance characteristics
- Binance API rate limiting policies

**Schema Definitions**:
- Plan JSON Schema (planning decisions)
- Proposal JSON Schema (trade proposals) 
- Verdict JSON Schema (validation decisions)

**Environment Configuration**:
- Complete .env template with all required variables
- Pydantic Settings validation rules
- Database initialization and migration scripts
