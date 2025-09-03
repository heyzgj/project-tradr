"""
Complete orchestrator integrating all components for autonomous operation
"""
import time
import uuid
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from core.config import Settings, load_settings
from core.openai_client import create_openai_client
from core.logging import (
    setup_logging,
    get_logger,
    PerformanceTimer,
    log_agent_decision,
    log_trade_execution,
)
from core.util import make_idempotency_key

from agents.planner import create_planner_agent
from agents.trader import create_trader_agent  
from agents.judge import create_judge_agent

from tools.market import create_market_client
from tools.strategy import create_technical_analysis
from tools.trade import create_trade_client
from tools.ledger import create_ledger_manager
from tools.memory import create_memory_manager


class TradingOrchestrator:
    """Complete autonomous trading orchestrator."""
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or load_settings()
        
        # Setup logging first
        setup_logging(self.settings.log_level, self.settings.log_file)
        self.logger = get_logger(__name__)
        
        # Initialize all components
        self._initialize_components()
        
        # Runtime state
        self.is_running = False
        self.cycle_count = 0
        
        self.logger.info("Trading orchestrator initialized successfully")
    
    def _initialize_components(self):
        """Initialize all system components."""
        try:
            # Core clients
            self.openai_client = create_openai_client(self.settings)
            self.market_client = create_market_client(self.settings)
            self.trade_client = create_trade_client(self.settings)
            self.ledger = create_ledger_manager(self.settings)
            self.memory = create_memory_manager(self.settings)
            
            # Analysis tools
            self.technical_analysis = create_technical_analysis()
            
            # AI Agents
            self.planner = create_planner_agent(self.openai_client, self.settings)
            self.trader = create_trader_agent(self.openai_client, self.settings)
            self.judge = create_judge_agent(self.openai_client, self.settings)
            
            self.logger.info("All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Component initialization failed: {e}")
            raise
    
    def run_forever(self):
        """Main execution loop - runs until interrupted."""
        self.logger.info(f"Starting autonomous trading loop in {self.settings.mode} mode")
        self.is_running = True
        
        try:
            while self.is_running:
                self.run_cycle()
                
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested by user")
            self.shutdown_gracefully()
        except Exception as e:
            self.logger.error(f"Fatal error in main loop: {e}", exc_info=True)
            self.shutdown_gracefully()
            raise
    
    def run_cycle(self):
        """Execute one complete autonomous trading cycle."""
        cycle_start = time.time()
        trace_id = str(uuid.uuid4())
        self.cycle_count += 1
        
        self.logger.info(f"=== CYCLE {self.cycle_count} START === (trace: {trace_id})")
        
        try:
            with PerformanceTimer(self.logger, "complete trading cycle", trace_id=trace_id):
                # Phase 1: Strategic Planning
                plan = self._planning_phase(trace_id)
                
                # Phase 2: Market Analysis (if trading mode)
                if plan['mode'] == 'TRADE':
                    proposal = self._analysis_phase(plan, trace_id)
                    
                    # Phase 3: Risk Validation (if not HOLD)
                    if proposal['action'] != 'HOLD':
                        verdict = self._validation_phase(proposal, trace_id)
                        
                        # Phase 4: Trade Execution (if approved)
                        if verdict['decision'] in ('APPROVE', 'REVISE'):
                            self._execution_phase(proposal, verdict, trace_id)
                    else:
                        self.logger.info("HOLD decision - no trade execution needed")
                else:
                    self.logger.info("OBSERVE mode - skipping trading phases")
                
                # Phase 5: Learning & Memory Update
                self._learning_phase(trace_id)
                
                # Phase 6: Sleep until next cycle
                sleep_duration = plan.get('next_wakeup_secs', 300)
                self._sleep_phase(sleep_duration, cycle_start)
                
        except Exception as e:
            self.logger.error(f"Cycle {self.cycle_count} failed: {e}", exc_info=True)
            # Sleep longer on error to avoid rapid failures
            time.sleep(60)
    
    def _planning_phase(self, trace_id: str) -> Dict[str, Any]:
        """Phase 1: Strategic planning with adaptive behavior."""
        self.logger.info("Phase 1: Strategic Planning")
        
        try:
            # Get memory context for planning
            memory_context = self.memory.read_posteriors()
            
            # Generate plan
            plan = self.planner.plan(memory_context)
            
            # Log planning decision (with trace)
            plan_id = self.ledger.log_decision('PLANNER', plan, trace_id)
            plan['_plan_id'] = plan_id  # Store for later reference
            # Structured log for audit trail
            try:
                log_agent_decision(self.logger, 'PLANNER', plan, trace_id)
            except Exception:
                pass
            
            self.logger.info(f"Plan generated: {plan['mode']} mode, "
                           f"{len(plan['strategies'])} strategies, "
                           f"next wakeup: {plan['next_wakeup_secs']}s")
            
            return plan
            
        except Exception as e:
            self.logger.error(f"Planning phase failed: {e}")
            # Return safe fallback plan
            return {
                'mode': 'OBSERVE',
                'explore_ratio': 0.0,
                'next_wakeup_secs': 600,
                'strategies': [{'policy_id': 'fallback_observe', 'params': {}}],
                '_plan_id': -1
            }
    
    def _analysis_phase(self, plan: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        """Phase 2: Market analysis and trade proposal generation."""
        self.logger.info("Phase 2: Market Analysis & Proposal")
        
        try:
            # Get market data
            ohlcv_data = self.market_client.get_ohlcv(
                self.settings.symbol, 
                self.settings.timeframe,
                self.settings.ohlcv_limit
            )
            
            # Compute technical indicators
            indicators = self.technical_analysis.compute_indicators(ohlcv_data)
            
            # Generate trade proposal
            proposal = self.trader.propose(plan, indicators)
            
            # Log trading decision (with trace)
            proposal_id = self.ledger.log_decision(
                'TRADER', proposal, trace_id, plan_id=plan.get('_plan_id')
            )
            proposal['_proposal_id'] = proposal_id  # Store for later reference
            try:
                log_agent_decision(self.logger, 'TRADER', proposal, trace_id)
            except Exception:
                pass
            
            self.logger.info(f"Proposal generated: {proposal['action']} "
                           f"{proposal['qty']} (confidence: {proposal['confidence']:.2f})")
            
            return proposal
            
        except Exception as e:
            self.logger.error(f"Analysis phase failed: {e}")
            # Return safe fallback proposal
            return {
                'action': 'HOLD',
                'qty': '0',
                'policy_id': 'fallback_hold',
                'hypothesis': 'Analysis failed - maintaining safe position',
                'confidence': 0.1,
                '_proposal_id': -1
            }
    
    def _validation_phase(self, proposal: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        """Phase 3: Risk validation and constraint enforcement."""
        self.logger.info("Phase 3: Risk Validation")
        
        try:
            # Get current market price for validation
            ticker = self.market_client.get_ticker(self.settings.symbol)
            current_price = ticker.get('last', 50000.0)
            
            # Review proposal against constraints
            verdict = self.judge.review(proposal, current_price)
            
            # Log judge decision (with trace)
            self.ledger.log_decision(
                'JUDGE', verdict, trace_id, proposal_id=proposal.get('_proposal_id')
            )
            try:
                log_agent_decision(self.logger, 'JUDGE', verdict, trace_id)
            except Exception:
                pass
            
            self.logger.info(f"Verdict: {verdict['decision']}")
            if verdict['decision'] == 'REVISE':
                self.logger.info(f"Revised quantity: {verdict.get('revised_qty')}")
            elif verdict['decision'] == 'REJECT':
                violations = verdict.get('violations', [])
                self.logger.info(f"Rejection reasons: {violations}")
            
            return verdict
            
        except Exception as e:
            self.logger.error(f"Validation phase failed: {e}")
            # Return safe rejection
            return {
                'decision': 'REJECT',
                'violations': ['Validation system error'],
                'notes': 'Judge agent failure - rejecting for safety'
            }
    
    def _execution_phase(self, proposal: Dict[str, Any], verdict: Dict[str, Any], trace_id: str):
        """Phase 4: Trade execution with full audit trail."""
        self.logger.info("Phase 4: Trade Execution")
        
        try:
            # Determine final quantity
            final_qty = verdict.get('revised_qty', proposal.get('qty'))
            action = proposal['action']
            
            # Generate idempotency key
            ticker = self.market_client.get_ticker(self.settings.symbol)
            current_price = ticker.get('last', 50000.0)
            idempotency_key = make_idempotency_key(
                trace_id, self.settings.symbol, action, final_qty
            )
            
            # Execute trade
            order_result = self.trade_client.place_market_order(
                side=action,
                qty=final_qty,
                idempotency_key=idempotency_key
            )
            
            # Log trade execution
            trade_id = self.ledger.log_trade(
                side=action,
                qty=order_result['filled_qty'],
                price=order_result['price'],
                fee=order_result.get('fee', '0'),
                idempotency_key=idempotency_key,
                proposal_id=proposal.get('_proposal_id', -1),
                order_id=order_result.get('order_id')
            )
            try:
                log_trade_execution(
                    self.logger,
                    self.settings.symbol,
                    action,
                    order_result['filled_qty'],
                    order_result['price'],
                    trade_id,
                    trace_id,
                )
            except Exception:
                pass
            
            # Update portfolio snapshot
            balance_data = self.trade_client.get_account_balance()
            self.ledger.snapshot_portfolio(order_result['price'], balance_data)
            
            # Store experiment result
            experiment_result = {
                'result': 'executed',
                'action': action,
                'qty': order_result['filled_qty'],
                'price': order_result['price'],
                'fee': order_result.get('fee', '0'),
                'confidence': proposal.get('confidence', 0.5),
                'trade_id': trade_id
            }
            
            self.memory.write_experiment(
                proposal.get('policy_id', 'unknown'), 
                experiment_result
            )
            
            self.logger.info(f"Trade executed successfully: {action} {final_qty} @ {order_result['price']}")
            
        except Exception as e:
            self.logger.error(f"Execution phase failed: {e}")
            # Log failed execution as experiment
            self.memory.write_experiment(
                proposal.get('policy_id', 'unknown'),
                {
                    'result': 'execution_failed',
                    'error': str(e),
                    'confidence': proposal.get('confidence', 0.5)
                }
            )
    
    def _learning_phase(self, trace_id: str):
        """Phase 5: Learning and memory updates."""
        self.logger.info("Phase 5: Learning & Memory Update")
        
        try:
            # Generate learning insights periodically
            if self.cycle_count % 10 == 0:  # Every 10 cycles
                insights = self.memory.get_learning_insights()
                self.logger.info(f"Learning insights: {insights}")
                
                # Store insights for future reference
                self.memory.write_experiment('learning_insights', {
                    'cycle': self.cycle_count,
                    'insights': insights,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            
            # Optimize exploration ratio based on recent performance
            if self.cycle_count % 5 == 0:  # Every 5 cycles
                current_performance = {}  # Could be enhanced with recent metrics
                optimized_ratio = self.memory.optimize_exploration_ratio(current_performance)
                self.logger.info(f"Optimized exploration ratio: {optimized_ratio:.3f}")
            
        except Exception as e:
            self.logger.error(f"Learning phase failed: {e}")
    
    def _sleep_phase(self, sleep_duration: int, cycle_start: float):
        """Phase 6: Sleep until next cycle."""
        cycle_duration = time.time() - cycle_start
        
        self.logger.info(f"=== CYCLE {self.cycle_count} COMPLETE === "
                        f"(duration: {cycle_duration:.2f}s, sleeping: {sleep_duration}s)")
        
        # Ensure minimum sleep time
        actual_sleep = max(30, sleep_duration)  # At least 30 seconds
        time.sleep(actual_sleep)
    
    def shutdown_gracefully(self):
        """Graceful shutdown with cleanup."""
        self.logger.info("Initiating graceful shutdown...")
        self.is_running = False
        
        try:
            # Cancel any open orders
            self.trade_client.cancel_all_orders()
            
            # Final portfolio snapshot
            ticker = self.market_client.get_ticker(self.settings.symbol)
            balance_data = self.trade_client.get_account_balance()
            self.ledger.snapshot_portfolio(str(ticker.get('last', 50000.0)), balance_data)
            
            # Log shutdown
            self.memory.write_experiment('system_event', {
                'event': 'graceful_shutdown',
                'cycle_count': self.cycle_count,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            self.logger.info("Graceful shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")


def run_forever():
    """Main entry point for autonomous trading."""
    try:
        # Load settings
        settings = load_settings(check_connectivity=False)
        
        # Create and run orchestrator
        orchestrator = TradingOrchestrator(settings)
        orchestrator.run_forever()
        
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Fatal orchestrator error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_forever()
