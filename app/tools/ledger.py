"""
Ledger tools for decision logging and portfolio tracking
"""
from typing import Dict, Any, Optional
from core.config import Settings
from core.db import DatabaseManager
from core.logging import get_logger
from core.util import str_to_decimal, decimal_to_str, calculate_notional


class LedgerManager:
    """Comprehensive ledger for audit trail and portfolio tracking."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self.db = DatabaseManager(settings.db_path)
    
    def log_decision(self, agent: str, payload: Dict[str, Any], trace_id: str,
                    plan_id: Optional[int] = None, proposal_id: Optional[int] = None) -> int:
        """Log agent decision to audit trail."""
        try:
            decision_id = self.db.log_decision(agent, payload, trace_id, plan_id, proposal_id)
            self.logger.info(f"Logged {agent} decision: ID {decision_id}")
            return decision_id
            
        except Exception as e:
            self.logger.error(f"Failed to log {agent} decision: {e}")
            return -1
    
    def log_trade(self, side: str, qty: str, price: str, fee: str,
                  idempotency_key: str, proposal_id: int, 
                  order_id: Optional[str] = None) -> int:
        """Log executed trade."""
        try:
            trade_id = self.db.log_trade(
                symbol=self.settings.symbol,
                side=side,
                qty=qty,
                price=price,
                idempotency_key=idempotency_key,
                proposal_id=proposal_id,
                fee=fee,
                order_id=order_id
            )
            
            # Calculate trade value for logging
            notional = calculate_notional(qty, price)
            self.logger.info(f"Logged trade: ID {trade_id}, {side} {qty} @ {price} "
                           f"(notional: {notional}, fee: {fee})")
            return trade_id
            
        except Exception as e:
            self.logger.error(f"Failed to log trade: {e}")
            return -1
    
    def snapshot_portfolio(self, current_price: str, balance_data: Optional[Dict[str, Any]] = None) -> int:
        """Create portfolio snapshot with mark-to-market valuation."""
        try:
            if balance_data is None:
                # Use mock balance for testing
                balance_data = {
                    'USDT': {'total': '1000.0'},
                    'BTC': {'total': '0.02'}
                }
            
            # Extract balances
            balance_usdt = balance_data.get('USDT', {}).get('total', '0.0')
            balance_btc = balance_data.get('BTC', {}).get('total', '0.0')
            
            # Calculate P&L (simplified - would need historical cost basis for real P&L)
            btc_value = calculate_notional(balance_btc, current_price)
            total_value = str_to_decimal(balance_usdt) + btc_value
            
            # For now, use simple unrealized P&L calculation
            # In production, this would track cost basis and realized vs unrealized P&L
            unrealized_pnl = "0.0"  # Placeholder
            realized_pnl = "0.0"    # Placeholder
            
            snapshot_id = self.db.snapshot_portfolio(
                balance_usdt=balance_usdt,
                balance_btc=balance_btc,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=realized_pnl
            )
            
            self.logger.info(f"Portfolio snapshot: ID {snapshot_id}, "
                           f"USDT: {balance_usdt}, BTC: {balance_btc} "
                           f"(total value: {total_value} USDT)")
            return snapshot_id
            
        except Exception as e:
            self.logger.error(f"Failed to create portfolio snapshot: {e}")
            return -1
    
    def write_experiment(self, key: str, value: Dict[str, Any]) -> int:
        """Store experiment result in memory system."""
        try:
            experiment_id = self.db.write_experiment(key, value)
            self.logger.info(f"Stored experiment: {key} -> ID {experiment_id}")
            return experiment_id
            
        except Exception as e:
            self.logger.error(f"Failed to store experiment {key}: {e}")
            return -1
    
    def read_posteriors(self) -> Dict[str, Any]:
        """Read recent experiment results for agent context."""
        try:
            posteriors = self.db.read_posteriors()
            self.logger.info(f"Retrieved {len(posteriors)} posterior experiments")
            return posteriors
            
        except Exception as e:
            self.logger.error(f"Failed to read posteriors: {e}")
            return {}
    
    def get_recent_trades(self, limit: int = 10) -> list:
        """Get recent trades for analysis."""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT ts_utc, side, qty, price, fee, order_id, idempotency_key
                    FROM trades 
                    WHERE symbol = ?
                    ORDER BY ts_utc DESC 
                    LIMIT ?
                """, (self.settings.symbol, limit))
                
                trades = []
                for row in cur.fetchall():
                    trades.append({
                        'timestamp': row['ts_utc'],
                        'side': row['side'],
                        'qty': row['qty'],
                        'price': row['price'],
                        'fee': row['fee'],
                        'order_id': row['order_id'],
                        'idempotency_key': row['idempotency_key']
                    })
                
                self.logger.info(f"Retrieved {len(trades)} recent trades")
                return trades
                
        except Exception as e:
            self.logger.error(f"Failed to get recent trades: {e}")
            return []
    
    def get_trading_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get trading statistics for the specified period."""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                # Get trades from last N days
                cur.execute("""
                    SELECT side, qty, price, fee
                    FROM trades 
                    WHERE symbol = ? 
                    AND datetime(ts_utc) >= datetime('now', '-{} days')
                """.format(days), (self.settings.symbol,))
                
                trades = cur.fetchall()
                
                if not trades:
                    return {'total_trades': 0, 'buy_count': 0, 'sell_count': 0}
                
                buy_count = sum(1 for t in trades if t['side'] == 'BUY')
                sell_count = sum(1 for t in trades if t['side'] == 'SELL')
                total_fees = sum(str_to_decimal(t['fee']) for t in trades)
                
                stats = {
                    'total_trades': len(trades),
                    'buy_count': buy_count,
                    'sell_count': sell_count,
                    'total_fees': decimal_to_str(total_fees),
                    'period_days': days
                }
                
                self.logger.info(f"Trading stats ({days}d): {stats}")
                return stats
                
        except Exception as e:
            self.logger.error(f"Failed to get trading stats: {e}")
            return {'total_trades': 0, 'buy_count': 0, 'sell_count': 0}


def create_ledger_manager(settings: Optional[Settings] = None) -> LedgerManager:
    """Factory function to create ledger manager."""
    if settings is None:
        settings = Settings()
    return LedgerManager(settings)
