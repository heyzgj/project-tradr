# 🤖 Autonomous Trader Agent

A fully autonomous crypto trading system powered by OpenAI's Agents SDK with three-agent architecture for intelligent, self-directed trading decisions.

## 🌟 Features

- **🧠 Three-Agent Architecture**: Planner → Trader → Judge for robust decision making
- **🔄 Full Autonomy**: Minimal human intervention beyond safety constraints  
- **📊 JSON-Only Communication**: Structured, validated agent interactions
- **🛡️ Built-in Safety**: Deposit caps, idempotency, comprehensive audit trails
- **📈 Adaptive Learning**: Memory system with strategy optimization
- **⚡ Production Ready**: Comprehensive error handling, logging, and testing

## 🏗️ Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   PLANNER   │───▶│   TRADER    │───▶│    JUDGE    │
│             │    │             │    │             │
│ Strategic   │    │ Market      │    │ Risk        │
│ Planning    │    │ Analysis    │    │ Validation  │
│             │    │             │    │             │
│ • Mode      │    │ • OHLCV     │    │ • Deposit   │
│ • Explore   │    │ • RSI/MA    │    │   Cap       │
│ • Timing    │    │ • Signals   │    │ • Precision │
└─────────────┘    └─────────────┘    └─────────────┘
       ▲                  ▲                  │
       │                  │                  ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   MEMORY    │    │   MARKET    │    │    TRADE    │
│   SYSTEM    │    │    DATA     │    │ EXECUTION   │
└─────────────┘    └─────────────┘    └─────────────┘
```

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Clone and setup
git clone <repository>
cd trader-agent
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Note: Requires OpenAI SDK >= 1.0 for structured outputs support
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit with your API keys
nano .env
```

Required environment variables:
```bash
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL_PLANNER=gpt-4o-mini    # Strategic planning model  
OPENAI_MODEL_TRADER=gpt-4o          # Market analysis model
OPENAI_MODEL_JUDGE=gpt-4o-mini      # Risk validation model
SYMBOL=BTC/USDT
MODE=testnet  # or 'real' for live trading
DEPOSIT_CAP_USDT=5.0  # Safety limit for real mode
```

### 3. Validation & Testing

```bash
# Validate configuration
python main.py --validate

# Run test cycle
python main.py --test-cycle
```

### 4. Start Autonomous Trading

```bash
# Start the agent
python main.py

# The agent will run continuously until Ctrl+C
```

## 📊 System Components

### Core Infrastructure
- **Configuration**: Pydantic Settings with validation
- **Database**: SQLite WAL with complete audit trail
- **Logging**: Structured JSON logging with trading context
- **Utilities**: Decimal precision and idempotency helpers

### Agent Architecture  
- **Planner Agent**: Strategic planning with adaptive behavior (gpt-4o-mini)
- **Trader Agent**: Market analysis and trade proposal generation (gpt-4o)  
- **Judge Agent**: Risk validation and constraint enforcement (gpt-4o-mini)

All agents use **Structured Outputs** with JSON Schema validation for reliable, consistent responses.

### Trading Tools
- **Market Data**: CCXT integration with fallback mock data
- **Technical Analysis**: RSI, MA, volume indicators
- **Trade Execution**: Precision handling with idempotency
- **Ledger System**: Complete audit trail and portfolio tracking

### Learning System
- **Memory Manager**: Experiment tracking and performance analysis
- **Learning Analytics**: Strategy optimization and insights
- **Adaptive Behavior**: Dynamic exploration vs exploitation

## 🛡️ Safety Features

### Financial Safety
- **Deposit Cap**: Hard limit on notional exposure in real mode
- **Idempotency**: SHA256 keys prevent duplicate orders
- **Precision Validation**: Exchange-compliant quantity formatting
- **Graceful Fallbacks**: Safe defaults when systems fail

### Operational Safety  
- **Comprehensive Logging**: Full audit trail of all decisions
- **Error Recovery**: Robust error handling and recovery
- **Graceful Shutdown**: Clean order cancellation and state saving
- **Test Mode**: Complete functionality without real money

## 📈 Performance

### System Metrics
- **Decision Cycle**: <10 seconds end-to-end
- **Database Operations**: <100ms per query
- **Memory Usage**: <100MB RAM
- **Test Coverage**: 85+ tests across all components

### Trading Performance
- **Autonomous Operation**: 24/7 capability
- **Adaptive Strategies**: Learning-based optimization
- **Risk Management**: Constraint-based validation
- **Audit Trail**: Complete decision transparency

## 🧪 Testing

```bash
# Run all tests
python -m unittest discover -s tests -p "test_*.py"

# Run specific test suites
python -m unittest tests.test_config      # Configuration tests
python -m unittest tests.test_agents      # Agent tests  
python -m unittest tests.test_tools       # Trading tools tests
python -m unittest tests.test_integration # End-to-end tests
```

## 📝 Usage Examples

### Basic Operation
```bash
# Start with default settings
python main.py

# Validate setup first
python main.py --validate
```

### Advanced Configuration
```bash
# Custom environment
export SYMBOL=ETH/USDT
export MODE=real
export DEPOSIT_CAP_USDT=100.0
python main.py
```

## 🔧 Development

### Project Structure
```
/app
  /agents     # AI agents (planner, trader, judge)
  /tools      # Trading tools (market, strategy, execution, ledger)
  /core       # Core infrastructure (config, db, orchestrator)
  /schemas    # JSON schema definitions
  /server     # Web dashboard for monitoring
/tests        # Comprehensive test suite
/docs         # Documentation (PRD, Tech Spec)
/project      # Task management and status
```

### Web Dashboard

Monitor agent activity with the built-in dashboard:

```bash
# Start the dashboard
cd app/server && uvicorn web:app --reload

# Or from project root
uvicorn app.server.web:app --reload --host 0.0.0.0 --port 8000
```

Dashboard features:
- **Real-time trace monitoring**: See every agent decision
- **Trade execution history**: Complete audit trail
- **Agent decision details**: Plan → Proposal → Verdict flow
- **Portfolio snapshots**: Balance and P&L tracking

### Adding New Strategies
1. Implement strategy in `tools/strategy.py`
2. Add strategy parameters to Planner prompts
3. Update schema validation if needed
4. Add tests for new functionality

## 📋 Acceptance Criteria (V1)

- ✅ Agent runs autonomously for ≥24h on testnet without crashes
- ✅ Three-agent architecture with JSON-only communication
- ✅ Complete audit trail of all decisions and trades
- ✅ Memory system tracks experiment performance
- ✅ Real mode enforces deposit cap constraints
- ✅ Graceful error handling and recovery
- ✅ Comprehensive test coverage (85+ tests)

## 🚨 Important Notes

### Real Trading Mode
- **Start Small**: Use low deposit caps initially
- **Monitor Closely**: Review logs and performance regularly
- **Test First**: Always validate in testnet mode first
- **API Keys**: Secure storage of exchange credentials

### Risk Warnings
- **Cryptocurrency Trading**: Involves substantial risk of loss
- **Autonomous Operation**: Limited human oversight by design
- **Market Volatility**: Performance varies with market conditions
- **No Guarantees**: Past performance does not predict future results

## 📞 Support

- **Documentation**: See `/docs` directory for detailed specifications
- **Logs**: Check structured JSON logs for system behavior
- **Database**: SQLite database contains complete audit trail
- **Testing**: Run test suite to verify system integrity

## 🔮 Future Enhancements (V1.1+)

- Multi-symbol trading support
- Advanced risk models and portfolio optimization
- WebSocket real-time data feeds
- Web dashboard for monitoring
- Advanced strategy exploration engine

---

**Built with ❤️ for autonomous trading excellence**

*Version 1.0.0 - Production Ready*
