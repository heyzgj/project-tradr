#!/usr/bin/env python3
"""
Autonomous Trader Agent - Production Entry Point

A fully autonomous crypto trading agent using OpenAI Agents SDK with 
three-agent architecture (Planner → Trader → Judge) for intelligent
decision making with minimal human intervention.

Usage:
    python main.py                    # Start autonomous trading
    python main.py --validate        # Validate configuration only
    python main.py --test-cycle      # Run single test cycle
"""

import sys
import argparse
import signal
from pathlib import Path
from dotenv import load_dotenv; load_dotenv()

# Add app directory to Python path
app_dir = Path(__file__).parent / "app"
sys.path.insert(0, str(app_dir))

from core.orchestrator import TradingOrchestrator
from core.config import load_settings
from core.logging import setup_logging, get_logger


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    logger = get_logger(__name__)
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    sys.exit(0)


def validate_configuration():
    """Validate configuration and dependencies."""
    print("🔧 Validating configuration...")
    
    try:
        settings = load_settings(check_connectivity=False)
        print(f"✅ Configuration loaded successfully")
        print(f"   • Mode: {settings.mode}")
        print(f"   • Symbol: {settings.symbol}")
        print(f"   • Deposit Cap: {settings.deposit_cap_usdt} USDT")
        print(f"   • Database: {settings.db_path}")
        
        # Check OpenAI API key format
        if settings.validate_api_keys():
            print("✅ OpenAI API key format valid")
        else:
            print("❌ OpenAI API key invalid")
            return False
        
        # Test database initialization
        from core.db import initialize_database
        initialize_database(settings.db_path)
        print("✅ Database initialization successful")
        
        print("\n🎉 All validation checks passed!")
        return True
        
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        return False


def run_test_cycle():
    """Run a single test cycle to verify system operation."""
    print("🧪 Running test cycle...")
    
    try:
        settings = load_settings(check_connectivity=False)
        setup_logging(settings.log_level)
        
        orchestrator = TradingOrchestrator(settings)
        
        print("✅ Orchestrator initialized")
        print("🚀 Executing test cycle...")
        
        # Run one cycle
        orchestrator.run_cycle()
        
        print("✅ Test cycle completed successfully!")
        print(f"   • Cycle count: {orchestrator.cycle_count}")
        
        # Show recent activity
        recent_trades = orchestrator.ledger.get_recent_trades(5)
        print(f"   • Recent trades: {len(recent_trades)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test cycle failed: {e}")
        return False


def main():
    """Main application entry point with command-line interface."""
    parser = argparse.ArgumentParser(
        description="Autonomous Trader Agent - AI-powered crypto trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Start autonomous trading
  python main.py --validate        # Validate configuration
  python main.py --test-cycle      # Run single test cycle
  
Environment Variables:
  OPENAI_API_KEY     OpenAI API key (required)
  SYMBOL             Trading symbol (default: BTC/USDT)
  MODE               Trading mode: testnet|real (default: testnet)
  DEPOSIT_CAP_USDT   Max deposit in real mode (default: 5.0)
  
For full configuration options, see .env.example
        """
    )
    
    parser.add_argument('--validate', action='store_true',
                       help='Validate configuration and exit')
    parser.add_argument('--test-cycle', action='store_true',
                       help='Run single test cycle and exit')
    parser.add_argument('--version', action='version', version='Autonomous Trader Agent v1.0.0')
    
    args = parser.parse_args()
    
    # Handle command-line options
    if args.validate:
        success = validate_configuration()
        sys.exit(0 if success else 1)
    
    if args.test_cycle:
        success = run_test_cycle()
        sys.exit(0 if success else 1)
    
    # Main autonomous trading mode
    print("🤖 Autonomous Trader Agent v1.0.0")
    print("🚀 Initializing autonomous trading system...")
    
    try:
        # Load and validate configuration
        settings = load_settings(check_connectivity=False)
        
        # Setup structured logging
        setup_logging(settings.log_level)
        logger = get_logger(__name__)
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        
        logger.info("=== AUTONOMOUS TRADER AGENT STARTING ===")
        logger.info(f"Mode: {settings.mode} | Symbol: {settings.symbol} | "
                   f"Deposit Cap: {settings.deposit_cap_usdt} USDT")
        
        print(f"✅ Configuration validated")
        print(f"✅ Logging configured ({settings.log_level})")
        print(f"📊 Trading {settings.symbol} in {settings.mode} mode")
        print(f"🛡️  Deposit cap: {settings.deposit_cap_usdt} USDT")
        print(f"🤖 Three-agent architecture: Planner → Trader → Judge")
        print()
        print("🚀 Starting autonomous operation...")
        print("   Press Ctrl+C for graceful shutdown")
        print()
        
        # Create and run orchestrator
        orchestrator = TradingOrchestrator(settings)
        orchestrator.run_forever()
        
    except KeyboardInterrupt:
        print("\n🛑 Shutdown requested by user")
        logger.info("Graceful shutdown completed")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        print("Check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
